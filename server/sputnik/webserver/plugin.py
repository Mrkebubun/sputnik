from sputnik.plugin import Plugin
from autobahn.twisted.wamp import ApplicationSession

class AuthenticationPlugin(Plugin):
    def __init__(self, name):
        Plugin.__init__(self, name, "webserver.authentication")

    def onHello(self, router_session, realm, details):
        pass

    def onAuthenticate(self, router_session, signature, extra):
        pass

    def onJoin(self, router_session, details):
        pass

class AuthorizationPlugin(Plugin):
    def __init__(self, name):
        Plugin.__init__(self, name, "webserver.authorization")

    def authorize(self, session, uri, action):
        pass

class SchemaPlugin(Plugin):
    def __init__(self, name):
        Plugin.__init__(self, name, "webserver.schema")

    def validate(self, type, uri, args, kwargs):
        pass

class ServicePlugin(Plugin, ApplicationSession):
    def __init__(self, name):
        Plugin.__init__(self, name, "webserver.service")
        ApplicationSession.__init__(self)

class DatabasePlugin(Plugin):
    def __init__(self, name):
        Plugin.__init__(self, name, "webserver.database")

class BackendPlugin(Plugin):
    def __init__(self, name):
        Plugin.__init__(self, name, "webserver.backend")

