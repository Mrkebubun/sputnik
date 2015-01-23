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
from pycoin.serialize import h2b_rev

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

KEY_FILE_EXISTS = BitGoException("exceptions/bitgo/key_file_exists")
NO_KEY_FILE = BitGoException("exceptions/bitgo/no_key_file")



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
        entropy = "".join([chr(random.getrandbits(8)) for i in range(32)])
        key = BIP32Node.from_master_secret(entropy, network)
        private = key.wallet_key(as_private=True).encode("utf-8")
        public = key.wallet_key(as_private=False).encode("utf-8")
        return {"xpub": public, "xprv": private}

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

    def sendCoins(self, address, amount, passphrase, otp='000000', confirms=None):
        if not os.path.exists(self.proxy.private_key_file):
            raise NO_KEY_FILE
        else:
            with open(self.proxy.private_key_file, "rb") as f:
                encrypted_xpriv = f.read()

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
            p2sh.append(unspent["redeemScript"])
            spendable = Spendable(unspent["value"],
                                  binascii.unhexlify(unspent["redeemScript"]),
                                  h2b_rev(unspent["tx_hash"]),
                                  unspent["tx_output_n"])
            spendables.append(spendable)
        available = sum([spendable.coin_value for spendable in spendables])
        result = yield self.createAddress(1)
        change = result["address"]
        tx = tx_utils.create_tx(spendables, [(address, amount), change], fee)

        key = BIP32Node.from_hwif(keychain["xprv"])
        tx_utils.sign_tx(tx, [key.wif()])
        returnValue({'tx': tx.as_hex(),
                     'fee': tx.fee()})

    def sendTransaction(self, tx, otp):
        return self._call("POST", "api/v1/tx/send", {"tx": tx, "otp": otp})

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
    def createWalletWithKeychains(self, passphrase, label, backup_xpub=None, token=None):
        user_keychain = self.proxy.keychains.create()
        encrypted_xprv = self.proxy.encrypt(user_keychain['xprv'], passphrase)
        backup_keychain = {"xpub": backup_xpub}
        if not backup_keychain["xpub"]:
            backup_keychain = self.proxy.keychains.create()
        yield self.proxy.keychains.add(user_keychain["xpub"], encrypted_xprv)
        # Save the encrypted xpriv to the local storage
        if os.path.exists(self.proxy.private_key_file):
            raise KEY_FILE_EXISTS
        else:
            with open(self.proxy.private_key_file, "wb") as f:
                f.write(encrypted_xprv)

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
        self.private_key_file = bitgo_config['private_key_file']
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
        url = urlparse.urljoin(self.endpoint, url)
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer %s" % self.token

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
                    'private_key_file': './bitgo.key'}
    bitgo = BitGo(bitgo_config, debug=True)

    @inlineCallbacks
    def main():
        otp = '0000000'
        auth = yield bitgo.authenticate('yury@m2.io', '9R73IxQpYX%%(', otp=otp)
        result = yield bitgo.wallets.list()
        wallet = result["wallets"]["2Mv2sk6aMXxT7AQU3pjiWFLPpjasAgq5TKG"]
        keychain = {"xprv":"xprv9s21ZrQH143K2yYdt9sNVB8MG8ZqDpfYbt722oWoVPvScEGy1YzAi6etQR7DJZCBnMDatjiXUxs9aeG7pSWkohUy5mbQneShd5sq7ay7KyN", "xpub":"xpub661MyMwAqRbcFTd6zBQNrK55pAQKdHPPy72cqBvR3jTRV2c7Z6JRFtyNFiMcJRPw8UVbNWorx9AUDbENSbs3mJaFDmDokZDhtGEK4rpQgVJ"}
        result = yield wallet.createTransaction("msj42CCGruhRsFrGATiUuh25dtxYtnpbTx", 1, keychain, 100000)
        pprint(result)

    main().addErrback(log.err)

    reactor.run()

