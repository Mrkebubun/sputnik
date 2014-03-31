import sys
from twisted.python import log
from twisted.internet.endpoints import serverFromString

log.startLogging(sys.stdout)

from autobahn.twisted.choosereactor import install_reactor
reactor = install_reactor()
print("Running on reactor {}".format(reactor))

from autobahn.wamp.router import RouterFactory
router_factory = RouterFactory()

from autobahn.twisted.wamp import RouterSessionFactory
session_factory = RouterSessionFactory(router_factory)

from autobahn.twisted.websocket import WampWebSocketServerFactory
transport_factory = WampWebSocketServerFactory(session_factory, debug=True)
transport_factory.setProtocolOptions(failByDrop=False)

server = serverFromString(reactor, sys.argv[1])
server.listen(transport_factory)

reactor.run()

