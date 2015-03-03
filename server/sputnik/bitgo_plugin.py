from sputnik.plugin import Plugin
from sputnik.bitgo_rpc import BitGo
from Crypto.Random import random
from bip32utils import BIP32Key
from twisted.internet.defer import inlineCallbacks

class BitgoPlugin(Plugin):
    def __init__(self):
        self.bitgo = BitGo(test=True, async=True)
        # TODO: lose this
        self.bitgo.login()

    def oauth_callback(self, token):
        self.bitgo.token = token

    @inlineCallbacks
    def create_wallet(self, backup_key):
        # check for existing wallet
        result = yield self.bitgo.wallet()
        for wallet in result["wallets"]:
            if result["wallets"][wallet]["label"] == "sputnik":
                raise MultiSigException("Wallet already exists.")

        # create a new key
        # TODO: allow testnet
        key = BIP32Key.fromEntropy("".join(map(chr,
                [random.getrandbits(8) for i in range(32)])), public=False)
        # TODO: save private key
        private = key.ExtendedKey(private=True, encoded=True)
        user_key = key.ExtendedKey(private=False, encoded=True)

        # create a new bitgo key
        result = yield self.bitgo.keychain("bitgo")
        bitgo_key = result["xpub"]

        # create the wallet
        keychains = [{"xpub":user_key}, {"xpub":backup_key}, {"xpub":bitgo_key}]
        yield self.bitgo.wallet(label="sputnik", m=2, n=3, keychains=keychains)

    @inlineCallbacks
    def send_coins(self, address, amount, auth):
        pass

