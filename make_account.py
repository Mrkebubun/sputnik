import sys
from pprint import pprint

from twisted.python import log
from twisted.internet import reactor

from autobahn.websocket import connectWS
from autobahn.wamp import WampClientFactory, WampCraClientProtocol


class MyClientProtocol(WampCraClientProtocol):
   """
   Authenticated WAMP client using WAMP-Challenge-Response-Authentication ("WAMP-CRA").
   """

   def onSessionOpen(self):
      ## "authenticate" as anonymous
      ##
      #d = self.authenticate()

      ## authenticate as "foobar" with password "secret"
      ##

      d = self.authenticate(authKey = "foobar",
                            authExtra = None,
                            authSecret = "secret")

      d.addCallbacks(self.onAuthSuccess, self.onAuthError)


   def onClose(self, wasClean, code, reason):
      reactor.stop()


   def onAuthSuccess(self, permissions):
      print "Authentication Success!"

      d = self.call("http://example.com/procedures/make_account", "steve", "wget")
      d.addBoth(pprint)

      print "end of fake break point"
      self.publish("http://example.com/topics/mytopic1", "Hello, world!")
      d = self.call("http://example.com/procedures/hello", "Foobar")
      d.addBoth(pprint)
      print "break point"

      d.addBoth(self.sendClose)


   def onAuthError(self, e):
      uri, desc, details = e.value.args
      print "Authentication Error!", uri, desc, details



if __name__ == '__main__':

   if len(sys.argv) > 1 and sys.argv[1] == 'debug':
      log.startLogging(sys.stdout)
      debug = True
   else:
      debug = False

   log.startLogging(sys.stdout)
   factory = WampClientFactory("ws://localhost:9000", debugWamp = debug)
   factory.protocol = MyClientProtocol
   connectWS(factory)
   reactor.run()

