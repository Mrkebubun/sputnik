from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("trader")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin
from sputnik import util
import datetime

from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import wamp
from autobahn.wamp.types import RegisterOptions


class TraderService(ServicePlugin):
    MAX_TICKER_LENGTH = 100

    def __init__(self):
        ServicePlugin.__init__(self)

    def init(self):
        self.accountant = self.require("sputnik.webserver.plugins.backend.accountant.AccountantProxy")

    @wamp.register(u"rpc.trader.place_order")
    @inlineCallbacks
    def place_order(self, order, details):
        order['contract'] = order['contract'][:self.MAX_TICKER_LENGTH]
        order["timestamp"] = util.dt_to_timestamp(datetime.datetime.utcnow())
        order['username'] = details.authid
        order["price"] = int(order["price"])
        order["quantity"] = int(order["quantity"])

        # Check for zero price or quantity
        if order["price"] == 0 or order["quantity"] == 0:
            returnValue([False, "exceptions/webserver/invalid_price_quantity"])

        # check tick size and lot size in the accountant, not here


        try:
            result = yield self.accountant.proxy.place_order(details.authid, order)
            returnValue([True, result])
        except Exception as e:
            returnValue([False, e.args])


    @inlineCallbacks
    def onJoin(self, details):
        results = yield self.register(self, options=RegisterOptions(details_arg="details", discloseCaller=True))
        for success, result in results:
            if success:
                log("Registered %s." % self._registrations[result.id].procedure)
            else:
                error("Error registering method: %s." % result.value.args[0])

