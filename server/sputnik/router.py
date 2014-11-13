import json
import hashlib

from twisted.internet import threads
from twisted.internet.defer import inlineCallbacks, returnValue
import twisted.enterprise.adbapi as adbapi
from autobahn import util
from autobahn.wamp import types, auth
from autobahn.twisted.wamp import ApplicationSession, RouterSession

import config

class AuthHandler(RouterSession):
    challenge = None # challenge object
    signature = None # signature of challange
    totp = None # totp secret
    exists = False # user was found in database

    @inlineCallbacks
    def generateChallenge(self, details):
       
        # Create and store a one time challenge.
        self.challenge = {"authid": details.authid,
                          "authrole": u"user",
                          "authmethod": u"wampcra",
                          "authprovider": u"database",
                          "session": details.pending_session,
                          "nonce": util.utcnow(),
                          "timestamp": util.newid()}

        # We can accept unicode usernames, but convert them before anything
        #   hits the database
        username = self.challenge["authid"].encode("utf8")

        # If the user does not exist, we should still return a consistent
        #   salt. This prevents the auth system from becoming a usename
        #   oracle.
        noise = hashlib.md5("super secret" + username + "even more secret")
        salt, secret = noise.hexdigest()[:8], "!"
        
        # The client expects a unicode challenge string.
        challenge = json.dumps(self.challenge, ensure_ascii = False)
         
        query = "SELECT password, totp FROM users WHERE username=%s LIMIT 1"
        try:
            dbpool = self.factory.dbpool

            # A hit and a miss both take approximately the same amount of time.
            #   We can probably not worry about timing attacks here.
            result = yield dbpool.runQuery(query, (username,))

            if result:
                salt, secret = result[0][0].split(":")
                self.totp = result[0][1]
                self.exists = True

            # We compute the signature even if there is no such user to
            #   prevent timing attacks.
            self.signature = (yield threads.deferToThread(auth.compute_wcs,
                        key_bytes, challenge.encode("utf8"))).decode("ascii")

            # TODO: log success
        except Exception, e:
            # TODO: log attempt
            pass

        # Client expects a unicode salt string.
        salt = salt.decode("ascii")

        returnValue((challenge, salt))

    def generateCookieChallenge(self, details):
       
        # This is not a real challenge. It is used for bookkeeping, however.
        #   We require to cookie owner to also know the correct authid, so
        #   we store what they think it is here.

        # Create and store a one time challenge.
        self.challenge = {"authid": details.authid,
                          "authrole": u"user",
                          "authmethod": u"cookie",
                          "authprovider": u"cookie jar",
                          "session": details.pending_session,
                          "nonce": util.utcnow(),
                          "timestamp": util.newid()}

        # The client expects a unicode challenge string.
        return json.dumps(self.challenge, ensure_ascii = False)


    def verifySignature(self, signature, extra):
        if not self.challenge or not self.signature:
            return types.Deny(message=u"No pending authentication.")
      
        if len(signature) != len(self.signature):
            return types.Deny(message=u"Invalid signature.")

        success = True

        # Check each character to prevent HMAC timing attacks. This is really
        #   not an issue since each challenge gets a new nonce, but better
        #   safe than sorry.
        for i in range(len(self.signature)):
            if signature[i] != self.signature[i]:
                success = False

        # Reject the user if we did not actually find them in the database.
        if not self.found:
            success = False

        # Check the TOTP
        if self.totp:
            codes = [auth.compute_totp(self.totp, i) for i in range(-1, 2)]
            if extra["totp"].encode("utf8") not in codes:
                success = False

        if success:
            return types.Accept(authid=self.challenge["authid"],
                    authrole=self.challenge["authrole"],
                    authmethod=self.challenge["authmethod"],
                    authprovider=self.challenge["authprovider"])

        return types.Deny(message=u"Invalid signature.")

    def verifyCookie(self, signature, extra):
        authid = self.factory.cookies.get(signature, None)
        if authid != None and authid == self.challenge["authid"]:
            return types.Accept(authid=self.challenge["authid"],
                    authrole=self.challenge["authrole"],
                    authmethod=self.challenge["authmethod"],
                    authprovider=self.challenge["authprovider"])

        return types.Deny(message=u"Invalid signature.")

    @inlineCallbacks
    def onHello(self, realm, details):
        if details.authmethods:
            for authmethod in details.authmethods:
                self.authmethod = authmethod

                if authmethod == u"wampcra":
                    challenge, salt = yield self.generateChallenge(details)
                    extra = {u"challenge": challenge,
                             u"salt": salt,
                             u"iterations": 1000,
                             u"keylen": 32}
                    returnValue(types.Challenge(u"wampcra", extra))
                elif authmethod == u"cookie":
                    challenge = self.generateCookieChallenge(details) 
                    extra = {u"challenge": challenge}
                    returnValue(types.Challenge(u"cookie"), extra)

        returnValue(types.Deny("No authentication methods found."))

    def onAuthenticate(self, signature, extra):
        if self.authmethod == u"wampcra":
            return self.verifySignature(signature, extra)
        elif self.authmethod == u"cookie":
            return self.verifyCookie(signature, extra)

        return types.Deny(message=u"Server error.")



if __name__ == "__main__":
    from twisted.python import log
    import sys
    log.startLogging(sys.stdout)

    from autobahn.twisted.choosereactor import install_reactor
    reactor = install_reactor()

    from autobahn.twisted.wamp import RouterFactory
    router_factory = RouterFactory()

    from autobahn.twisted.wamp import RouterSessionFactory
    session_factory = RouterSessionFactory(router_factory)
    session_factory.session = AuthHandler
    dbpassword = config.get("database", "password")
    if dbpassword:
        dbpool = adbapi.ConnectionPool(config.get("database", "adapter"),
                               user=config.get("database", "username"),
                               password=dbpassword,
                               host=config.get("database", "host"),
                               port=config.get("database", "port"),
                               database=config.get("database", "dbname"))
    else:
        dbpool = adbapi.ConnectionPool(config.get("database", "adapter"),
                               user=config.get("database", "username"),
                               database=config.get("database", "dbname"))
    session_factory.dbpool = dbpool
    session_factory.cookies = {}

    from autobahn.twisted.websocket import WampWebSocketServerFactory
    transport_factory = WampWebSocketServerFactory(session_factory,
            "ws://localhost:8080", debug = False, debug_wamp = False)
    transport_factory.setProtocolOptions(failByDrop = False)

    from twisted.web.server import Site
    from twisted.web.static import File
    from autobahn.twisted.resource import WebSocketResource

    root = File(".")
    resource = WebSocketResource(transport_factory)
    root.putChild("ws", resource)
    site = Site(root)
    site.noisy = False
    site.log = lambda _: None

    from twisted.internet.endpoints import serverFromString
    server = serverFromString(reactor, "tcp:8080")
    server.listen(site)

    reactor.run()

