from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn.wamp import types
from autobahn.twisted.wamp import ApplicationSession, RouterSession, Router

import sys
sys.path.append("/home/yury/sputnik/server")

from sputnik import config
from sputnik import observatory
from sputnik import plugin

debug, log, warn, error, critical = observatory.get_loggers("router")

class SputnikRouter(Router):
    @inlineCallbacks
    def authorize(self, session, uri, action):
        results = []
        for plugin in self.factory.plugins:
            result = yield plugin.authorize(self, session, uri, action)
            if result == None:
                continue
            results.append(result)

        # Require no False and at least one True.
        returnValue(all(results) and results)

class SputnikRouterSession(RouterSession):
    @inlineCallbacks
    def onHello(self, realm, details):
        for plugin, flag in self.factory.plugins:
            result = yield plugin.onHello(realm, details)
            if result == None:
                continue
            else:
                returnValue(result)

        returnValue(types.Deny("No authentication methods found."))

    @inlineCallbacks
    def onAuthenticate(self, signature, extra):
        optional_failures = []
        required_failures = []
        optional_successes = []
        required_successes = []
        for plugin, flag in self.factory.plugins:
            result = yield plugin.onAuthenticate(signature, extra)
            if isinstance(result, types.Accept):
                if flag == "binding":
                    if len(required_failures) == 0:
                        returnValue(result)
                elif flag == "optional":
                    optional_successes.append(result)
                elif flag == "required":
                    required_successes.append(result)
                elif flag == "requisite":
                    required_successes.append(result)
                elif flag == "sufficient":
                    returnValue(result)
                else:
                    critical("Invalid control flag %s." % flag)
                    raise Exception("Invalid control flag %s." % flag)
            elif isinstance(result, types.Deny):
                if flag == "binding":
                    required_failures.append(result)
                elif flag == "optional":
                    optional_failures.append(result)
                elif flag == "required":
                    required_failures.append(result)
                elif flag == "requisite":
                    required_failures.append(result)
                    returnValue(required_failures[0])
                elif flag == "sufficient":
                    optional_failures.append(result)
                else:
                    critical("Invalid control flag %s." % flag)
                    raise Exception("Invalid control flag %s." % flag)
        
        if len(required_failed) > 0:
            returnValue(required_failed[0])
        
        if len(required_successes) > 0:
            returnValue(required_successes[0])
        elif len(optional_successes) > 0:
            returnValue(optional_successes[0])

        returnValue(types.Deny(u"No suitable authentication methods found."))

    @inlineCallbacks
    def onJoin(self, details):
        for plugin, flag in self.factory.plugins:
            yield plugin.onJoin(details)

class TimeService(ApplicationSession):
    def onJoin(self, details):
        import datetime

        def utcnow():
            now = datetime.datetime.utcnow()
            return now.strftime("%Y-%m-%dT%H:%M:%SZ")

        self.register(utcnow, 'com.timeservice.now')

def main(pm):
    from autobahn.twisted.choosereactor import install_reactor
    reactor = install_reactor()

    from autobahn.twisted.wamp import RouterFactory
    router_factory = RouterFactory()
    router_factory.router = SputnikRouter

    authz_plugins = ["webserver.authorization.basic"]
    router_factory.plugins = []
    for plugin_name in authz_plugins:
        router_factory.plugins.append(pm.plugins[plugin_name])

    from autobahn.twisted.wamp import RouterSessionFactory
    session_factory = RouterSessionFactory(router_factory)
    session_factory.session = SputnikRouterSession

    authn_plugins = [("webserver.authentication.anonymous", "sufficient"),
                     ("webserver.authentication.cookie", "sufficient"),
                     ("webserver.authentication.wampcra", "requisite"),
                     ("webserver.authentication.totp", "requisite")]
    session_factory.plugins = []
    for plugin_name, flag in authn_plugins:
        session_factory.plugins.append((pm.plugins[plugin_name], flag))

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

if __name__ == "__main__":
    observatory.start_logging(0)
    plugins = ["sputnik.webserver.plugins.authz_basic.BasicPermissions",
               "sputnik.webserver.plugins.authn_anonymous.AnonymousLogin",
               "sputnik.webserver.plugins.authn_cookie.CookieLogin",
               "sputnik.webserver.plugins.authn_wampcra.WAMPCRALogin",
               "sputnik.webserver.plugins.authn_totp.TOTPVerification"]
    plugin.run_with_plugins(plugins, main)

