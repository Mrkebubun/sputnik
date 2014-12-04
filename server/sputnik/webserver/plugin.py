from sputnik.plugin import Plugin
from autobahn.twisted.wamp import ApplicationSession
from twisted.internet.defer import inlineCallbacks, returnValue

class AuthenticationPlugin(Plugin):
    def onHello(self, router_session, realm, details):
        pass

    def onAuthenticate(self, router_session, signature, extra):
        pass

    def onJoin(self, router_session, details):
        pass

class AuthorizationPlugin(Plugin):
    def authorize(self, session, uri, action):
        pass

class SchemaPlugin(Plugin):
    def validate(self, type, uri, args, kwargs):
        pass

class ServicePlugin(Plugin, ApplicationSession):
    def __init__(self):
        ApplicationSession.__init__(self)

class DatabasePlugin(Plugin):
    pass

class BackendPlugin(Plugin):
    pass

