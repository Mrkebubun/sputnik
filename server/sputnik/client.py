import sys

from twisted.python import log
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet.endpoints import clientFromString

from autobahn.twisted import wamp, websocket
from autobahn.wamp import types
from autobahn.wamp import auth

class MyFrontendComponent(wamp.ApplicationSession):

   def onConnect(self):
      self.join(self.config.realm, [u"wampcra"], u"yury")


   def onChallenge(self, challenge):
      print challenge
      if challenge.method == u"wampcra":
         if u'salt' in challenge.extra:
            key = auth.derive_key(u"foobar".encode('utf8'),
               challenge.extra['salt'].encode('utf8'),
               challenge.extra.get('iterations', None),
               challenge.extra.get('keylen', None))
         else:
            key = u"foobar".encode('utf8')
         signature = auth.compute_wcs(key, challenge.extra['challenge'].encode('utf8'))
         return signature.decode('ascii')
      else:
         raise Exception("don't know how to compute challenge for authmethod {}".format(challenge.method))


   def onJoin(self, details):

      ## call a remote procedure
      ##
      print "joined"

      self.leave()


   def onLeave(self, details):
      print("onLeave: {}".format(details))
      self.disconnect()


   def onDisconnect(self):
      reactor.stop()



if __name__ == '__main__':

   ## 0) start logging to console
   log.startLogging(sys.stdout)

   ## 1) create a WAMP application session factory
   component_config = types.ComponentConfig(realm = "realm1")
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

