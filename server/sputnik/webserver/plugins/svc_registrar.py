from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("svc_registrar")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin

from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import wamp


class RegistrarService(ServicePlugin):
    def __init__(self):
        ServicePlugin.__init__(self, "registrar")

    def init(self):
        self.administrator = self.manager.plugins.get("webserver.backend.administrator")
        if not self.administrator:
            raise PluginException("Missing dependency %s." % "webserver.backend.administrator")
    
    @wamp.register(u"service.registrar.create_account")
    @inlineCallbacks
    def make_account(self, username, password, email, locale=None):
        try:
            result = yield self.administrator.make_account(username, password)
            if result:
                profile = {"email": email, "nickname": nickname,
                           "locale": locale}
                yield self.administrator.change_profile(username, profile)
                returnValue(True, username)
        except Exception, e:
            returnValue(False, e.args)

    @inlineCallbacks
    def onJoin(self, details):
        results = yield self.register(self)
        for success, result in results:
            if success:
                log("Registered %s." % self._registrations[result.id].procedure)
            else:
                error("Error registering method: %s." % result.value.args[0])

