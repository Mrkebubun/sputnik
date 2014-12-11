from sputnik.plugin import Plugin
from autobahn.twisted.wamp import ApplicationSession
from twisted.internet.defer import inlineCallbacks, returnValue
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("plugin")

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
    def validate(self, router, type, uri, args, kwargs):
        pass

class ServicePlugin(Plugin, ApplicationSession):
    def __init__(self):
        ApplicationSession.__init__(self)
        Plugin.__init__(self)
        self.receivers = []
        self.receiver_plugins = []

    @inlineCallbacks
    def init(self):
        for receiver_plugin in self.receiver_plugins:
            receiver = self.require(receiver_plugin)
            receiver.listeners.append(self)
            self.receivers.append(receiver)

    def shutdown(self):
        for receiver in self.receivers:
            receiver.listeners.remove(self)


class DatabasePlugin(Plugin):
    pass

class BackendPlugin(Plugin):
    pass

class ReceiverPlugin(Plugin):
    def __init__(self):
        self.listeners = []
        Plugin.__init__(self)

    def send_to_listeners(self, event, *args, **kwargs):
        for listener in self.listeners:
            try:
                listener.event(event, *args, **kwargs)
            except Exception, e:
                error("Error handling %s in %s." % (event, listener))
                error(e)
