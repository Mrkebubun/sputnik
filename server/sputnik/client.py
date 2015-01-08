import sys

from twisted.python import log
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.endpoints import clientFromString

from autobahn.twisted import wamp, websocket
from autobahn.wamp import types
from autobahn.wamp import auth
import util

class MyFrontendComponent(wamp.ApplicationSession):
    methods = [u"anonymous", u"wampcra", u"cookie"]
    index = 0

    def onConnect(self):
        self.join(self.config.realm, [u"anonymous"])

    def onChallenge(self, challenge):
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
        elif challenge.method == u"cookie":
            return self.cookie
        else:
            raise Exception("don't know how to compute challenge for authmethod {}".format(challenge.method))


    @inlineCallbacks
    def onJoin(self, details):
        self.index += 1

        if details.authmethod == u"anonymous":
            print "Connected anonymously."
            try:
                result = yield self.call(u"rpc.info.get_exchange_info")
                print "Exchange info: %s" % str(result)
                def on_event(event):
                    pass
                result = yield self.subscribe(on_event,
                        u'feeds.market.ohlcv.nets2014')
                print "Subscribed to a ohlcv feed."
            except Exception as e:
                print e
            returnValue(self.leave())

        if details.authmethod == u"wampcra":
            print "Logged in using WAMP-CRA."
            try:
                self.cookie = (yield self.call(u"rpc.token.get_cookie"))[1]
                print "Got a cookie: %s" % self.cookie
                def on_event(event):
                    pass
                result = yield self.subscribe(on_event,
                        u'feeds.user.orders.%s' % \
                                util.encode_username(u'marketmaker'))
                print "Subscribed to a feed."
            except Exception as e:
                print e
            returnValue(self.leave())

        if details.authmethod == u"cookie":
            print "Logged in using a cookie."
            try:
                result = yield self.call(u"rpc.token.logout")
                print "Logged out."
            except Exception as e:
                print e
            returnValue(self.leave())

    def onLeave(self, details):
        print "Left realm."
        self.join(self.config.realm, [self.methods[self.index]], u"marketmaker")

    def onDisconnect(self):
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
            url = "ws://127.0.0.1:8080/ws", debug = False, debug_wamp = False, headers={"X-Forwarded-For":"10.0.0.1"})

    ## 3) start the client from a Twisted endpoint
    client = clientFromString(reactor, "tcp:127.0.0.1:8080")
    client.connect(transport_factory)

    ## 4) now enter the Twisted reactor loop
    reactor.run()

