import json

from twisted.internet import threads
from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import util
from autobahn.wamp import types, auth
from autobahn.twisted.wamp import ApplicationSession, RouterSession

import config



class AuthHandler(RouterSession):
    challenge = None

    @inlineCallbacks
    def getUserSecret(self, authid):
        try:
            dbpool = self.factory.dbpool
            result = yield dbpool.runQuery('SELECT password, totp FROM users WHERE username=%s LIMIT 1', (authid,))
            salt, secret = result[0][0].split(":")
            returnValue((secret, salt))
        except Exception, e:
            returnValue(u":", unicode(random.random())[2:])

    @inlineCallbacks
    def onHello(self, realm, details):
        if details.authmethods:
            if u"wampcra" in details.authmethods:
                authid = details.authid
                key, salt = self.getUserSecret(authid)

                self.challenge = {"authid": authid,
                                  "session": details.pending_session,
                                  "nonce": util.utcnow(),
                                  "timestamp": util.newid()}
                key_bytes = key.encode("utf8")
                challenge_str = json.dumps(self.challenge, ensure_ascii=False)
                challenge_bytes = challenge_str.encode("utf8")
                self.signature = (yield threads.deferToThread(auth.compute_wcs,
                        key_bytes, challenge_bytes)).decode("ascii")

                extra = {u"challenge": challenge_str,
                         u"salt": salt,
                         u"iterations": 1000,
                         u"keylen": 32}

                returnValue(types.Challenge(u"wampcra", extra))

        returnValue(types.Deny())

    def onAuthenticate(self, signature, extra):
        if not self.challenge:
            return types.Deny(message=u"No pending authentication.")
      
        if len(signature) != len(self.signature):
            return types.Deny(message=u"Invalid signature.")

        success = True
        for i in range(len(self.signature)):
            if signature[i] != self.signature[i]:
                success = False

        if success:
            return types.Accept(authid=self.challenge["authid"],
                    authrole=u"user",
                    authmethod=u"wampcra",
                    authprovider=u"database")

        return types.Deny(message=u"Invalid signature.")


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

    from autobahn.twisted.websocket import WampWebSocketServerFactory
    transport_factory = WampWebSocketServerFactory(session_factory,
            "ws://localhost:8080", debug = False, debug_wamp = False)
    transport_factory.setProtocolOptions(failByDrop = False)

    from twisted.web.server import Site
    from twisted.web.static import File
    from autobahn.twisted.resource import WebSocketResource

    root = File(".")
    resour e = WebSocketResource(transport_factory)
    root.putChild("ws", resource)
    site = Site(root)
    site.noisy = False
    site.log = lambda _: None

    from twisted.internet.endpoints import serverFromString
    server = serverFromString(reactor, "tcp:8080")
    server.listen(site)

    reactor.run()

