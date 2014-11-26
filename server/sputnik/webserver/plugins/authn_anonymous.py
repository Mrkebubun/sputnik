from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("auth_cookie")

from sputnik.webserver.plugin import AuthenticationPlugin
from autobahn.wamp import types

class AnonymousLogin(AuthenticationPlugin):
    def __init__(self):
        AuthenticationPlugin.__init__(self, u"anonymous")

    def onHello(self, router_session, realm, details):
        for authmethod in details.authmethods:
            if authmethod == u"anonymous":
                peer = router_session._transport.getPeer()
                log("Successful anonymous login from %s." % peer)
                return types.Accept(authid=u"anonymous",
                                    authrole=u"anonymous",
                                    authmethod=u"anonymous",
                                    authprovider=u"anonymous")

