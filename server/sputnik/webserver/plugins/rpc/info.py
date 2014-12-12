from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("rpc_info")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin

from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import wamp


class InfoService(ServicePlugin):
    def __init__(self):
        ServicePlugin.__init__(self)

    def init(self):
        self.exchange_info = dict(config.items("exchange_info"))

    @wamp.register(u"rpc.info.get_exchange_info")
    def get_exchange_info(self):
        return [True, self.exchange_info]

    @inlineCallbacks
    def onJoin(self, details):
        results = yield self.register(self)
        for success, result in results:
            if success:
                log("Registered %s." % self._registrations[result.id].procedure)
            else:
                error("Error registering method: %s." % result.value.args[0])

