from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("svc_registrar")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin

from twisted.internet.defer import inlineCallbacks
from autobahn import wamp


class RegistrarService(ServicePlugin):
    def __init__(self):
        ServicePlugin.__init__(self, "registrar")

    def init(self):
        self.administrator = self.manager.plugins.get("webserver.backend.administrator")
        if not self.administrator:
            raise PluginException("Missing dependency %s." % "webserver.backend.administrator")
    
    @wamp.register(u"service.registrar.create_account")
    def make_account(self, username, password, salt, email, locale=None):
        self.administrator.make_account(username, password, salt, email, locale)

    @inlineCallbacks
    def onJoin(self, details):
        results = yield self.register(self)
        for success, result in results:
            if success:
                log("Registered %s." % self._registrations[result.id].procedure)
            else:
                error("Error registering method: %s." % result.value.args[0])

