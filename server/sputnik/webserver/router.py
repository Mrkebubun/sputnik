import json
import hashlib
import datetime

from twisted.internet import threads
from twisted.internet.defer import inlineCallbacks, returnValue
import twisted.enterprise.adbapi as adbapi
from autobahn import util
from autobahn.wamp import types, auth
from autobahn.wamp.interfaces import IRouter
from autobahn.twisted.wamp import ApplicationSession, RouterSession, Router

import sys
print sys.path

from sputnik import config
from sputnik import observatory

class SputnikRouter(Router):
    @inlineCallbacks
    def authorize(self, session, uri, action):
        for plugin in self.factory.plugins:
            result = yield plugin.authorize(self, session, uri, action)
            if result == None:
                continue
            else:
                returnValue(result)

        returnValue(False)

class SputnikRouterSession(RouterSession):
    @inlineCallbacks
    def onHello(self, realm, details):
        # TODO: add support for PAM style control flags
        for plugin in self.factory.plugins:
            result = yield plugin.onHello(realm, details)
            if result == None:
                continue
            else:
                returnValue(result)

        returnValue(types.Deny("No authentication methods found."))

    @inlineCallbacks
    def onAuthenticate(self, signature, extra):
        # TODO: add support for PAM style control flags
        for plugin in self.factory.plugins:
            result = yield plugin.onAuthenticate(signature, extra)
            if result == None:
                continue
            else:
                returnValue(result)

        returnValue(types.Deny(u"Server error."))

    @inlineCallbacks
    def onJoin(self, details):
        for plugin in self.factory.plugins:
            yield plugin.onJoin(details)

class TimeService(ApplicationSession):
    def onJoin(self, details):

        def utcnow():
            now = datetime.datetime.utcnow()
            return now.strftime("%Y-%m-%dT%H:%M:%SZ")

        self.register(utcnow, 'com.timeservice.now')

def main():
    observatory.start_logging(0)

    from autobahn.twisted.choosereactor import install_reactor
    reactor = install_reactor()

    from autobahn.twisted.wamp import RouterFactory
    router_factory = RouterFactory()
    router_factory.router = SputnikRouter
    router_factory.plugins = []

    from autobahn.twisted.wamp import RouterSessionFactory
    session_factory = RouterSessionFactory(router_factory)
    session_factory.session = SputnikRouterSession
    session_factory.plugins = []

    component_config = types.ComponentConfig(realm = "realm1")
    component_session = TimeService(component_config)
    session_factory.add(component_session, u"time_service", u"trusted")

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

