from sputnik.plugin import Plugin

class AuthenticationPlugin(Plugin):
    def __init__(self, name):
        Plugin.__init__(name, "webserver.authentication")

    def onHello(self, router_session, realm, details):
        pass

    def onAuthenticate(self, router_session, signature, extra):
        pass

    def onJoin(self, router_session, details):
        pass

class AuthorizationPlugin(Plugin):
    def __init__(self, name):
        Plugin.__init__(name, "webserver.authorization")

    def authorize(self, session, uri, action):
        pass

class ServicePlugin(Plugin):
    def __init__(self, name):
        Plugin.__init__(name, "webserver.service")

class DatabasePlugin(Plugin):
    def __init__(self, name):
        Plugin.__init__(name, "webserver.database")

