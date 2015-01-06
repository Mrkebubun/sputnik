from sputnik.plugin import Plugin
from autobahn.twisted.wamp import ApplicationSession
from twisted.internet.defer import inlineCallbacks, returnValue
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("plugin")

def authenticated()

from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import wamp
from autobahn.wamp.types import RegisterOptions

def authenticated(func):
    @inlineCallbacks
    def wrapper(*args, **kwargs):
        # Make sure username is not passed in
        if 'username' in kwargs:
            raise Exception("'username' passed in over RPC")

        details = kwargs.pop('details')
        username = details.authid
        if username is None:
            raise Exception("details.authid is None")
        kwargs['username'] = username
        try:
            r = yield func(*args, **kwargs)
            returnValue([True, r])
        except Exception as e:
            error("Error calling %s - args=%s, kwargs=%s" % (fn_name, args, kwar
gs))
            error(e)
            returnValue([False, e.args])

    return wrapper


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

    @inlineCallbacks
    def onJoin(self, details):
        results = yield self.register(self)
        for success, result in results:
            if success:
                log("Registered %s." % self._registrations[result.id].procedure)
            else:
                error("Error registering method: %s." % result.value.args[0])

class DatabasePlugin(Plugin):
    pass

class BackendPlugin(Plugin):
    pass

class ReceiverPlugin(Plugin):
    pass
