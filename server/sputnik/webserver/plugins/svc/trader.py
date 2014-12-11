from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("trader")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin

from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import wamp
from autobahn.wamp.types import RegisterOptions


class TraderService(ServicePlugin):
    def __init__(self):
        ServicePlugin.__init__(self)

    def init(self):
        self.accountant = self.require("sputnik.webserver.plugins.backend.accountant.AccountantProxy")

    def place_order(self, ticker, price, quantity, details):
        log(details)

    @inlineCallbacks
    def onJoin(self, details):
        results = yield self.register(self, options=RegisterOptions(details_arg="details", discloseCaller=True))
        for success, result in results:
            if success:
                log("Registered %s." % self._registrations[result.id].procedure)
            else:
                error("Error registering method: %s." % result.value.args[0])

