import treq
import json
import hmac
import hashlib
import urlparse
import os
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
import util
from twisted.python import log
from pprint import pprint
import string

from Crypto.Random import random
from pycoin.key.BIP32Node import BIP32Node
from pycoin.tx.Spendable import Spendable
from pycoin.tx import tx_utils
from pycoin.tx.pay_to import build_hash160_lookup, build_p2sh_lookup
from pycoin.serialize import h2b, h2b_rev, b2h, h2b_rev

# pycoin does not produce scripts like we want it to
# to be honest, there is no standard for partially signed transactions
from pycoin.tx.pay_to.ScriptMultisig import ScriptMultisig
from pycoin.tx.pay_to import SolvingError
from pycoin.tx.script import tools
from pycoin.tx.script.vm import parse_signature_blob
from pycoin import ecdsa
from pycoin import encoding

def solve(self, **kwargs):
    """
    The kwargs required depend upon the script type.
    hash160_lookup:
        dict-like structure that returns a secret exponent for a hash160
    existing_script:
        existing solution to improve upon (optional)
    sign_value:
        the integer value to sign (derived from the transaction hash)
    signature_type:
        usually SIGHASH_ALL (1)
    """
    # we need a hash160 => secret_exponent lookup
    db = kwargs.get("hash160_lookup")
    if db is None:
        raise SolvingError("missing hash160_lookup parameter")

    sign_value = kwargs.get("sign_value")
    signature_type = kwargs.get("signature_type")

    secs_solved = set()
    existing_signatures = []
    existing_script = kwargs.get("existing_script")
    if existing_script:
        pc = 0
        opcode, data, pc = tools.get_opcode(existing_script, pc)
        # ignore the first opcode
        while pc < len(existing_script):
            opcode, data, pc = tools.get_opcode(existing_script, pc)
            sig_pair, actual_signature_type = parse_signature_blob(data)
            for sec_key in self.sec_keys:
                try:
                    public_pair = encoding.sec_to_public_pair(sec_key)
                    sig_pair, signature_type = parse_signature_blob(data)
                    v = ecdsa.verify(ecdsa.generator_secp256k1, public_pair, sign_value, sig_pair)
                    if v:
                        existing_signatures.append(data)
                        secs_solved.add(sec_key)
                        break
                except encoding.EncodingError:
                    # if public_pair is invalid, we just ignore it
                    pass

    for sec_key in self.sec_keys:
        if sec_key in secs_solved:
            continue
        if len(existing_signatures) >= self.n:
            break
        hash160 = encoding.hash160(sec_key)
        result = db.get(hash160)
        if result is None:
            continue
        secret_exponent, public_pair, compressed = result
        binary_signature = self._create_script_signature(secret_exponent, sign_value, signature_type)
        existing_signatures.append(b2h(binary_signature))
    DUMMY_SIGNATURE = "OP_0"
    while len(existing_signatures) < self.n:
        existing_signatures.append(DUMMY_SIGNATURE)

    script = "OP_0 %s" % " ".join(s for s in existing_signatures)
    solution = tools.compile(script)
    return solution

ScriptMultisig.solve = solve

import binascii

from datetime import datetime


class BitGoException(Exception):
    pass


class BadRequest(BitGoException):
    pass


class Unauthorized(BitGoException):
    pass


class MethodNotFound(BitGoException):
    pass


class NotAcceptable(BitGoException):
    pass

def create_keychain(network):
    entropy = "".join([chr(random.getrandbits(8)) for i in range(32)])
    key = BIP32Node.from_master_secret(entropy, network)
    private = key.wallet_key(as_private=True).encode("utf-8")
    public = key.wallet_key(as_private=False).encode("utf-8")
    return {"xpub": public, "xprv": private}

class Keychains(object):
    def __init__(self, proxy):
        self.proxy = proxy

    def _call(self, method, url, data=None):
        return self.proxy._call(method, url, data)

    def list(self):
        return self._call("GET", "keychain")

    def create(self):
        network = "BTC"
        if not self.proxy.use_production:
            network = "XTN"
        return create_keychain(network)

    def add(self, xpub, encrypted_xprv=None):
        data = {"xpub": xpub}
        if encrypted_xprv:
            data["encryptedXprv"] = encrypted_xprv
        return self._call("POST", "api/v1/keychain", data)

    def createBitGo(self):
        return self._call("POST", "api/v1/keychain/bitgo")

    def get(self, xpub):
        return self._call("POST", "api/v1/keychain/%s" % xpub)

    def update(self, xpub, encrypted_xprv=None):
        data = None
        if encrypted_xprv:
            data = {"encryptedXprv": encrypted_xprv}
        return self._call("PUT", "api/v1/keychain/%s" % xpub, data)


class Wallet(object):
    def __init__(self, proxy, data):
        self.proxy = proxy
        for key, value in data.iteritems():
            setattr(self, key, value)

    def __str__(self):
        return "Wallet: %s" % self.id

    def _call(self, method, url, data=None):
        return self.proxy._call(method, url, data)

    def createAddress(self, chain):
        return self._call("POST", "api/v1/wallet/%s/address/%s" % (self.id, chain))

    def sendCoins(self, address, amount, passphrase, otp='000000', confirms=None, encrypted_xpriv=None):
        xprv = self.proxy.decrypt(encrypted_xpriv, passphrase)
        # The first keychain is the userkeychain, so we add the decrypted key to that one
        self.keychains[0]['xprv'] = xprv
        tx = yield self.createTransaction(address, amount, self.keychains[0], fee="standard")
        result = yield self.sendTransaction(tx=tx['tx'], otp=otp)
        returnvalue = {'tx': result['tx'],
                       'hash': result['transactionHash'],
                       'fee': tx['fee']}
        returnValue(returnvalue)

    def sendMany(self, recipients, message=None, confirms=None):
        raise NotImplemented

    def addresses(self):
        return self._call("GET", "api/v1/wallet/%s/addresses" % self.id)

    def transactions(self):
        return self._call("GET", "api/v1/wallet/%s/tx" % self.id)

    def unspents(self):
        return self._call("GET", "api/v1/wallet/%s/unspents" % self.id)

    @inlineCallbacks
    def createTransaction(self, address, amount, keychain, fee="standard",
                          confirms=0):
        result = yield self.unspents()
        spendables = []
        p2sh = []
        for unspent in result["unspents"]:
            if unspent["confirmations"] < confirms:
                continue
            p2sh.append(h2b(unspent["redeemScript"]))
            spendable = Spendable(unspent["value"],
                                  h2b(unspent["script"]),
                                  h2b_rev(unspent["tx_hash"]),
                                  unspent["tx_output_n"])
            spendables.append(spendable)
        p2sh_lookup = build_p2sh_lookup(p2sh)
        result = yield self.createAddress(1)
        change = result["address"]
        tx = tx_utils.create_tx(spendables, [(address, amount), change], fee)

        key = BIP32Node.from_hwif(keychain["xprv"]).subkey_for_path("0/0/0/0")
        hash160_lookup = build_hash160_lookup([key.secret_exponent()])

        tx.sign(hash160_lookup=hash160_lookup, p2sh_lookup=p2sh_lookup)
        returnValue({'tx': tx.as_hex(),
                     'fee': tx.fee()})

    def sendTransaction(self, tx):
        return self._call("POST", "api/v1/tx/send", {"tx": tx})

    def setPolicy(self, policy):
        return self._call("POST", "api/v1/wallet/%s/policy" % self.id,
                          {"policy": policy})

    def addUser(self, email, permissions):
        return self._call("POST", "api/v1/wallet/%s/policy/grant" % self.id,
                          {"email": email, "permissions": permissions})

    def removeUser(self, email):
        return self._call("POST", "api/v1/wallet/%s/policy/revoke" % self.id,
                          {"email": email})


class Wallets(object):
    def __init__(self, proxy):
        self.proxy = proxy

    def _call(self, method, url, data=None):
        return self.proxy._call(method, url, data)

    def _decode(self, data):
        return Wallet(self.proxy, data)

    def list(self):
        def decode(result):
            wallets = result["wallets"]
            return {"wallets": {k: self._decode(v) for k, v in wallets.items()}}

        return self._call("GET", "api/v1/wallet").addCallback(decode)

    def add(self, label, m, n, keychains, enterprise=None):
        data = {"label": label, "m": m, "n": n, "keychains": keychains}
        if enterprise:
            data["enterprise"] = enterprise
        return self._call("POST", "api/v1/wallet", data).addCallback(self._decode)

    def get(self, id):
        return self._call("GET", "api/v1/wallet/%s" % id).addCallback(self._decode)

    @inlineCallbacks
    def createWalletWithKeychains(self, passphrase, label, backup_xpub=None):
        user_keychain = self.proxy.keychains.create()
        encrypted_xprv = self.proxy.encrypt(user_keychain['xprv'], passphrase)
        backup_keychain = {"xpub": backup_xpub}
        if not backup_keychain["xpub"]:
            backup_keychain = self.proxy.keychains.create()

        yield self.proxy.keychains.add(user_keychain["xpub"], encrypted_xprv)
        user_keychain["encryptedXprv"] = encrypted_xprv

        yield self.proxy.keychains.add(backup_keychain["xpub"])
        bitgo_keychain = yield self.proxy.keychains.createBitGo()
        keychains = [{"xpub": user_keychain["xpub"]},
                     {"xpub": backup_keychain["xpub"]},
                     {"xpub": bitgo_keychain["xpub"]}]
        wallet = yield self.add(label, 2, 3, keychains)
        result = {"wallet": wallet,
                  "userKeychain": user_keychain,
                  "backupKeychain": backup_keychain,
                  "bitgoKeychain": bitgo_keychain,
                  "warning": "Be sure to backup the backup keychain -- " \
                             "it is not stored anywhere else!"}
        returnValue(result)


class BitGo(object):
    def __init__(self, bitgo_config, debug=False):
        self.use_production = bitgo_config['production'] == "true"
        self.endpoint = bitgo_config['endpoint']
        self.client_id = bitgo_config['client_id']
        self.client_secret = bitgo_config['client_secret']
        self.debug = debug

        self.token = None

        self.keychains = Keychains(self)
        self.wallets = Wallets(self)

    def encrypt(self, message, passphrase):
        # TODO: Actually encrypt
        return message

    def decrypt(self, encrypted, passphrase):
        # TODO: Actually decrypt
        return encrypted

    @inlineCallbacks
    def _call(self, method, url, data=None):
        url = urlparse.urljoin(self.endpoint, url).encode('utf-8')
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = ("Bearer %s" % self.token).encode('utf-8')

        if data:
            data = json.dumps(data)  # raises TypeError
        if self.debug:
            print "%s %s" % (method, url)
            print "Headers: %s" % str(headers)
            print "Data: %s" % data

        response = yield treq.request(method, url, headers=headers, data=data)
        code = response.code
        content = yield treq.content(response)
        if self.debug:
            print "Got: %s" % content

        try:
            def encode(data):
                encoded = {}
                for key, value in data.iteritems():
                    if isinstance(key, unicode):
                        key = key.encode("utf-8")
                    if isinstance(value, unicode):
                        value = value.encode("utf-8")
                    encoded[key] = value
                return encoded

            content = json.loads(content, object_hook=encode)
        except ValueError as e:
            pass

        if code == 200:
            returnValue(content)
        elif code == 400:
            raise BadRequest(content)
        elif code == 401:
            raise Unauthorized(content)
        elif code == 404:
            raise MethodNotFound(content)
        elif code == 406:
            raise NotAcceptable(content)
        else:
            raise BitGoException(content)

    def ping(self):
        return self._call("GET", "api/v1/ping")

    def authenticate(self, email, password, otp=None):
        password = hmac.HMAC(email, password, hashlib.sha256).hexdigest()

        data = {"email": email, "password": password}
        if otp:
            data["otp"] = otp

        def save_token(data):
            self.token = data["access_token"].encode("utf-8")
            return data

        return self._call("POST", "api/v1/user/login", data).addCallback(save_token)

    def logout(self):
        return self._call("GET", "api/v1/user/logout")

    def session(self):
        return self._call("GET", "api/v1/user/session")

    def sendOTP(self, force_sms=False):
        return self._call("GET", "api/v1/user/sendotp", {"forceSMS": force_sms})

    def unlock(self, otp, duration=600):
        return self._call("POST", "api/v1/user/unlock",
                          {"otp": otp, "duration": duration})

    def lock(self):
        return self._call("POST", "api/v1/user/lock")

    def me(self):
        return self._call("GET", "api/v1/user/me")

    def get_address(self, address):
        return self._call("GET", "api/v1/address/%s" % address)

    def get_address_transactions(self, address):
        return self._call("GET", "api/v1/address/%s/tx" % address)

    def get_transaction(self, tx):
        return self._call("GET", "api/v1/tx/%s" % tx)

    @inlineCallbacks
    def oauth_token(self, code):
        token_result = yield self._call("POST", "oauth/token",
                                        {'code': code,
                                         'client_id': self.client_id,
                                         'client_secret': self.client_secret,
                                         'grant_type': 'authorization_code'})
        self.token = token_result['access_token'].encode('utf-8')
        self.token_expiration = datetime.fromtimestamp(token_result['expires_at'])
        returnValue({'token': self.token,
                     'expiration': util.dt_to_timestamp(self.token_expiration)})


if __name__ == "__main__":
    bitgo_config = {'production': False,
                    'endpoint': "https://test.bitgo.com",
                    'client_id': 'XXX',
                    'client_secret': 'YYY',
    }
    bitgo = BitGo(bitgo_config, debug=True)
    from sys import argv

    @inlineCallbacks
    def main():
        otp = '0000000'
        if argv[1] == 'sameer':
            auth = yield bitgo.authenticate('sameer@m2.io', 'i6M:wpF4', otp=otp)
            pprint(auth)
            label = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))

            wallet = yield bitgo.wallets.createWalletWithKeychains('none', label=label,
                                                                   backup_xpub='tpubD6NzVbkrYhZ4WtoseA5DYXuz6TpukQxDaLdvBa1MawByoeVUvCJ7N6qhZCeLrSbbcBpmsKas9VSvZ7KwJYEc9hi1s566sWwafZUpjPqaGqT')
            pprint(wallet)
            encrypted_xprv = wallet['userKeychain']['encryptedXprv']

            wallet_list = yield bitgo.wallets.list()
            pprint(wallet_list)

            full_wallet = yield bitgo.wallets.get(wallet['wallet'].id)
            pprint(full_wallet)

            keychain = bitgo.keychains.create()
            result = yield full_wallet.createTransaction("msj42CCGruhRsFrGATiUuh25dtxYtnpbTx", 1000000, keychain)

            # Get an address
            address = yield full_wallet.createAddress(0)
            pprint(address)

            # Send coins to myself
            tx = yield full_wallet.sendCoins(address['address'], 10000, 'none', otp=otp, encrypted_xprv=encrypted_xprv)
            pprint(tx)

        else:
            auth = yield bitgo.authenticate('yury@m2.io', '9R73IxQpYX%%(', otp=otp)
            yield bitgo.unlock("0000000")
            result = yield bitgo.wallets.list()
            wallet = result["wallets"]["2Mv2sk6aMXxT7AQU3pjiWFLPpjasAgq5TKG"]
            keychain = {"xprv":"xprv9s21ZrQH143K2yYdt9sNVB8MG8ZqDpfYbt722oWoVPvScEGy1YzAi6etQR7DJZCBnMDatjiXUxs9aeG7pSWkohUy5mbQneShd5sq7ay7KyN", "xpub":"xpub661MyMwAqRbcFTd6zBQNrK55pAQKdHPPy72cqBvR3jTRV2c7Z6JRFtyNFiMcJRPw8UVbNWorx9AUDbENSbs3mJaFDmDokZDhtGEK4rpQgVJ"}
            result = yield wallet.createTransaction("2Mz7sBSNftUd5Ntwcyvb4tENr2kjWhQpNGN", 1e8, keychain, 100000)
            result = yield wallet.sendTransaction(result["tx"])
            pprint(result)

    main().addErrback(log.err)

    reactor.run()

