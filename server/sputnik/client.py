import sys

from twisted.python import log
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.endpoints import clientFromString

from autobahn.twisted import wamp, websocket
from autobahn.wamp import types
from autobahn.wamp import auth

class MyFrontendComponent(wamp.ApplicationSession):
    auth = False

    def onConnect(self):
        print "connect"
        self.join(self.config.realm, [u"anonymous"])

    def onChallenge(self, challenge):
        print "got challenge: %s" % challenge
        if challenge.method == u"wampcra":
            if u'salt' in challenge.extra:
                key = auth.derive_key(u"marketmaker".encode('utf8'),
                    challenge.extra['salt'].encode('utf8'),
                    challenge.extra.get('iterations', None),
                    challenge.extra.get('keylen', None))
            else:
                key = u"a".encode('utf8')
            signature = auth.compute_wcs(key, challenge.extra['challenge'].encode('utf8'))
            return signature.decode('ascii')
        else:
            raise Exception("don't know how to compute challenge for authmethod {}".format(challenge.method))


    @inlineCallbacks
    def onJoin(self, details):
        if details.authrole == u"anonymous":
            returnValue(self.leave())

        auth = True
        result = yield self.call(u"rpc.private.foobar")
        print result



    def onLeave(self, details):
        if not self.auth:
            self.join(self.config.realm, [u"wampcra"], u"marketmaker")


    def onDisconnect(self):
        print "disconnected"
        reactor.stop()



if __name__ == '__main__':

    ## 0) start logging to console
    log.startLogging(sys.stdout)

    ## 1) create a WAMP application session factory
    component_config = types.ComponentConfig(realm = "sputnik")
    session_factory = wamp.ApplicationSessionFactory(config = component_config)
    session_factory.session = MyFrontendComponent

    ## 2) create a WAMP-over-WebSocket transport client factory
    transport_factory = websocket.WampWebSocketClientFactory(session_factory,
        url = "ws://127.0.0.1:8080/ws", debug = False, debug_wamp = False)

    ## 3) start the client from a Twisted endpoint
    client = clientFromString(reactor, "tcp:127.0.0.1:8080")
    client.connect(transport_factory)

    ## 4) now enter the Twisted reactor loop
    reactor.run()

