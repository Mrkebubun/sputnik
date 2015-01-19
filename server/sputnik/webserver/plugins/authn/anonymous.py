from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("authn_anonymous")

from sputnik.webserver.plugin import AuthenticationPlugin
from autobahn.wamp import types

class AnonymousLogin(AuthenticationPlugin):
    def __init__(self):
        AuthenticationPlugin.__init__(self)

    def onHello(self, router_session, realm, details):
        for authmethod in details.authmethods:
            if authmethod == u"anonymous":
                log("Successful anonymous login (ID: %s)." % \
                        details.pending_session)
                return types.Accept(authid=u"anonymous",
                                    authrole=u"anonymous",
                                    authmethod=u"anonymous",
                                    authprovider=u"anonymous")

