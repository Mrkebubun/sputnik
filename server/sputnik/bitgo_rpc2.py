import treq
import json
import hmac
import hashlib
import urlparse

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue

from Crypto.Random import random
from pycoin.key.BIP32Node import BIP32Node

ENDPOINTS = {"test":"https://test.bitgo.com/api/v1/",
             "production": "https://www.bitgo.com/api/v1/"}

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
        return {"xpub":public, "xprv":private}

    def add(self, xpub, encrypted_xprv=None):
        data = {"xpub":xpub}
        if encrypted_xprv:
            data["encryptedXprv"] = encrypted_xprv
        return self._call("POST", "keychain", data)

    def createBitGo(self):
        return self._call("POST", "keychain/bitgo")

    def get(self, xpub):
        return self._call("POST", "keychain/%s" % xpub)

    def update(self, xpub, encrypted_xprv=None):
        data = None
        if encrypted_xprv:
            data = {"encryptedXprv":encrypted_xprv}
        return self._call("PUT", "keychain/%s" % xpub, data)

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
        return self._call("POST", "wallet/%s/address/%s" % (self.id, chain))

    def sendCoins(self, address, amount, passphrase, confirms=None):
        raise NotImplemented

    def sendMany(self, recipients, message=None, confirms=None):
        raise NotImplemented

    def addresses(self):
        return self._call("GET", "wallet/%s/addresses" % self.id)

    def transactions(self):
        return self._call("GET", "wallet/%s/tx" % self.id)

    def unspents(self):
        return self._call("GET", "wallet/%s/unspents" % self.id)

    def createTransaction(address, amount, keychain, fee=None, confirms=None):
        raise NotImplemented

    def sendTransaction(self, tx):
        return self._call("POST", "tx/send", {"tx":tx})

    def setPolicy(self, policy):
        return self._call("POST", "wallet/%s/policy" % self.id,
                          {"policy":policy})

    def addUser(self, email, permissions):
        return self._call("POST", "wallet/%s/policy/grant" % self.id,
                          {"email":email, "permissions":permissions})

    def removeUser(self, email):
        return self._call("POST", "wallet/%s/policy/revoke" % self.id,
                          {"email":email})

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
            return {"wallets":{k: self._decode(v) for k, v in wallets.items()}}

        return self._call("GET", "wallet").addCallback(decode)

    def add(self, label, m, n, keychains, enterprise=None):
        data = {"lavel":label, "m":m, "n":n, "keychains":keychains}
        if enterprise:
            data["enterprise"] = enterprise
        return self._call("POST", "wallet", data).addCallback(self._decode)

    def get(self, id):
        return self._call("POST", "wallet/%s" % id).addCallback(self._decode)

    @inlineCallbacks
    def createWalletWithKeychains(self, passphrase, label, backup_xpub=None):
        user_keychain = self.proxy.keychains.create()
        # TODO: encrypt with passphrase
        encrypted_xpriv = ""
        backup_keychain = {"xpub":backup_xpub}
        if not backup_keychain["xpub"]:
            backup_keychain = self.proxy.keychains.create()
        yield self.proxy.keychains.add(user_keychain["xpub"], encrypted_xpriv)
        yield self.proxy.keychains.add(backup_keychain["xpub"])
        bitgo_keychain = yield self.proxy.keychains.createBitGo()
        keychains = [{"xpub":user_keychain["xpub"]},
                     {"xpub":backup_keychain["xpub"]},
                     {"xpub":bitgo_keychain["xpub"]}]
        wallet = yield self.add(label, 2, 3, keychains)
        result = {"wallet":wallet,
                  "userKeychain":user_keychain,
                  "backupKeychain":backup_keychain,
                  "bitgoKeychain":bitgo_keychain,
                  "warning":"Be sure to backup the backup keychain -- " \
                            "it is not stored anywhere else!"
        returnValue(result)

class BitGo(object):
    def __init__(self, use_production=False, debug=False):
        self.use_production = use_production
        self.debug = debug

        self.endpoint = ENDPOINTS["test"]
        if self.use_production:
            self.endpoint = ENDPOINTS["production"]

        self.token = None

        self.keychain = Keychains(self)
        self.wallets = Wallets(self)

    @inlineCallbacks
    def _call(self, method, url, data=None):
        url = urlparse.urljoin(self.endpoint, url)
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer %s" % self.token
      
        if data:
            data = json.dumps(data) # raises TypeError
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
            content = json.loads(content)
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
        return self._call("GET", "ping")

    def authenticate(self, email, password, otp=None):
        password = hmac.HMAC(email, password, hashlib.sha256).hexdigest()

        data = {"email":email, "password":password}
        if otp:
            data["otp"] = otp

        def save_token(data):
            self.token = data["access_token"].encode("utf-8")
            return data

        return self._call("POST", "user/login", data).addCallback(save_token)

    def logout(self):
        return self._call("GET", "user/logout")

    def session(self):
        return self._call("GET", "user/session")

    def sendOTP(self, force_sms=False):
        return self._call("GET", "user/sendotp", {"forceSMS":force_sms})

    def unlock(self, otp, duation=600):
        return self._call("POST", "user/unlock",
                          {"otp":otp, "duration":duration})

    def lock(self):
        return self._call("POST", "user/lock")

    def me(self):
        return self._call("GET", "user/me")

    def get_address(self, address):
        return self._call("GET", "address/%s" % address)
    
    def get_address_transactions(self, address):
        return self._call("GET", "address/%s/tx" % address)

    def get_transaction(self, tx):
        return self._call("GET", "tx/%s" % tx)

