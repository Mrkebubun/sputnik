#!/usr/bin/env python

import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", ".."))


from sputnik import config
from optparse import OptionParser

parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
                  help="config file")
(options, args) = parser.parse_args()

if options.filename:
    # noinspection PyUnresolvedReferences
    config.reconfigure(options.filename)

from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn.wamp import types
from sputnik.webserver.router.twisted.wamp import RouterSession, Router
from autobahn.wamp.exception import ApplicationError
from sputnik.exception import *

from sputnik import observatory
from sputnik import plugin

debug, log, warn, error, critical = observatory.get_loggers("router")

class SputnikRouter(Router):
    @inlineCallbacks
    def authorize(self, session, uri, action):
        results = []
        for plugin in self.factory.authz_plugins:
            result = yield plugin.authorize(self, session, uri, action)
            if result == None:
                continue
            results.append(result)

        # Require no False and at least one True.
        returnValue(all(results) and results)

    def validate(self, type, uri, args, kwargs):
        results = []
        for plugin in self.factory.schema_plugins:
            result = plugin.validate(self, type, uri, args, kwargs)
            if result == None:
                continue
            results.append(result)

        # Require no False
        if not all(results):
            raise ApplicationError(ApplicationError.INVALID_ARGUMENT,
                    "Invalid message payload.")

class SputnikRouterSession(RouterSession):
    @inlineCallbacks
    def onHello(self, realm, details):
        if details.authmethods == None:
            details.authmethods = []
        for plugin, flag in self.factory.plugins:
            result = types.Deny(message=u"Server error.")
            try:
                result = yield plugin.onHello(self, realm, details)
            except Exception, e:
                error("Uncaught exception in plugin %s." % plugin.plugin_path)
                error()
            if result == None:
                continue
            else:
                returnValue(result)

        returnValue(types.Deny(message="No authentication methods found."))

    @inlineCallbacks
    def onAuthenticate(self, signature, extra):
        optional_failures = []
        required_failures = []
        optional_successes = []
        required_successes = []
        for plugin, flag in self.factory.plugins:
            result = types.Deny(message=u"Server error.")
            try:
                result = yield plugin.onAuthenticate(self, signature, extra)
            except Exception, e:
                error("Uncaught exception in plugin %s." % plugin.plugin_path)
                error()
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
        
        if len(required_failures) > 0:
            returnValue(required_failures[0])
        
        if len(required_successes) > 0:
            returnValue(required_successes[0])
        elif len(optional_successes) > 0:
            returnValue(optional_successes[0])

        returnValue(types.Deny(message=u"No suitable authentication methods found."))

    @inlineCallbacks
    def onJoin(self, details):
        for plugin, flag in self.factory.plugins:
            try:
                yield plugin.onJoin(self, details)
            except Exception, e:
                error("Uncaught exception in plugin %s." % plugin.plugin_path)
                error()

from twisted.web.resource import Resource, NoResource
class Root(Resource):
    def getChild(self, name, request):
        if name == '':
            return self
        child = Resource.getChild(self, name, request)
        if isinstance(child, NoResource):
            return self

    def render(self, request):
        request.setResponseCode(403, "No Access")
        return "Forbidden".encode('utf-8')

def main(pm):
    from sputnik.webserver.router.twisted.wamp import RouterFactory
    router_factory = RouterFactory()
    router_factory.router = SputnikRouter

    router_factory.authz_plugins = \
            pm.services.get("sputnik.webserver.plugins.authz", [])
    router_factory.schema_plugins = \
            pm.services.get("sputnik.webserver.plugins.schema", [])

    from sputnik.webserver.router.twisted.wamp import RouterSessionFactory
    session_factory = RouterSessionFactory(router_factory)
    session_factory.session = SputnikRouterSession

    authn_stack = [("ip.IPFilter", "requisite"),
                   ("anonymous.AnonymousLogin", "sufficient"),
                   ("cookie.CookieLogin", "sufficient"),
                   ("wampcra.WAMPCRALogin", "requisite"),
                   ("totp.TOTPVerification", "requisite")]
    session_factory.plugins = []
    for plugin_name, flag in authn_stack:
        path = "sputnik.webserver.plugins.authn." + plugin_name
        session_factory.plugins.append((pm.plugins[path], flag))

    rpc_plugins = pm.services.get("sputnik.webserver.plugins.rpc", [])
    feeds_plugins = pm.services.get("sputnik.webserver.plugins.feeds", [])
    svc_plugins = rpc_plugins + feeds_plugins
    for plugin in svc_plugins:
        component_session = plugin
        component_session.config.realm = u"sputnik"
        session_factory.add(component_session,
                plugin.plugin_path.decode("ascii"), u"trusted")

    # IP address to listen on for all publicly visible services
    interface = config.get("webserver", "interface")

    base_uri = config.get("webserver", "base_uri")

    uri = "ws://"
    if config.getboolean("webserver", "ssl"):
        uri = "wss://"

    address = config.get("webserver", "ws_address")
    port = config.getint("webserver", "ws_port")
    uri += "%s:%s/" % (address, port)

    from autobahn.twisted.websocket import WampWebSocketServerFactory
    transport_factory = WampWebSocketServerFactory(session_factory,
            uri, debug = False, debug_wamp = False)
    transport_factory.setProtocolOptions(failByDrop = False)

    from twisted.web.server import Site
    from autobahn.twisted.resource import WebSocketResource
    from rest import RESTProxy

    root = Root()
    ws_resource = WebSocketResource(transport_factory)
    rest_resource = pm.plugins['sputnik.webserver.rest.RESTProxy']
    root.putChild("ws", ws_resource)
    root.putChild("api", rest_resource)
    site = Site(root)
    site.noisy = False
    site.log = lambda _: None

    from twisted.internet.endpoints import serverFromString, quoteStringArgument
    if config.getboolean("webserver", "ssl"):
        key = config.get("webserver", "ssl_key")
        cert = config.get("webserver", "ssl_cert")
        cert_chain = config.get("webserver", "ssl_cert_chain")
        # TODO: Add dhparameters
        # See https://twistedmatrix.com/documents/14.0.0/core/howto/endpoints.html
        server = serverFromString(reactor, b"ssl:%d:privateKey=%s:certKey=%s:extraCertChain=%s:sslmethod=TLSv1_METHOD"
                                  % (port,
                                     quoteStringArgument(key),
                                     quoteStringArgument(cert),
                                     quoteStringArgument(cert_chain)))
    else:
        server = serverFromString(reactor, b"tcp:%d" % port)

    server.listen(site)

if __name__ == "__main__":
    from autobahn.twisted.choosereactor import install_reactor
    reactor = install_reactor()

    observatory.start_logging(10)
    plugins = ["sputnik.webserver.plugins.authz.default.DefaultPermissions",
               "sputnik.webserver.plugins.authn.anonymous.AnonymousLogin",
               "sputnik.webserver.plugins.authn.ip.IPFilter",
               "sputnik.webserver.plugins.authn.cookie.CookieLogin",
               "sputnik.webserver.plugins.authn.wampcra.WAMPCRALogin",
               "sputnik.webserver.plugins.authn.totp.TOTPVerification",
               "sputnik.webserver.plugins.db.mem.InMemoryDatabase",
               "sputnik.webserver.plugins.db.postgres.PostgresDatabase",
               "sputnik.webserver.plugins.backend.administrator.AdministratorProxy",
               "sputnik.webserver.plugins.backend.accountant.AccountantProxy",
               "sputnik.webserver.plugins.backend.cashier.CashierProxy",
               "sputnik.webserver.plugins.backend.alerts.AlertsProxy",
               "sputnik.webserver.plugins.rpc.registrar.RegistrarService",
               "sputnik.webserver.plugins.rpc.token.TokenService",
               "sputnik.webserver.plugins.rpc.info.InfoService",
               "sputnik.webserver.plugins.rpc.market.MarketService",
               "sputnik.webserver.plugins.rpc.private.PrivateService",
               "sputnik.webserver.plugins.rpc.trader.TraderService",
               "sputnik.webserver.plugins.feeds.market.MarketAnnouncer",
               "sputnik.webserver.plugins.feeds.user.UserAnnouncer",
               "sputnik.webserver.plugins.receiver.accountant.AccountantReceiver",
               "sputnik.webserver.plugins.receiver.engine.EngineReceiver",
               "sputnik.webserver.rest.RESTProxy"]
    plugin.run_with_plugins(reactor, plugins, main)

