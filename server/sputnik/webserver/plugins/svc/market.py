from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("svc_market")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin

from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import wamp


class MarketService(ServicePlugin):
    def __init__(self):
        ServicePlugin.__init__(self)

    def reload(self):
        pass

    @wamp.register(u"service.market.get_markets")
    def get_markets(self):
        return [True, self.markets]

    @wamp.register(u"service.market.get_ohlcv_history")
    def get_ohlcv_history(self, ticker, period=None, start_timestamp=None,
            end_timestamp=None):
        pass

    @wamp.register(u"service.market.get_trade_history")
    def get_trade_history(self, ticker, start_timestamp=None,
            end_timestamp=None):
        pass

    @wamp.register(u"service.market.get_order_book")
    def get_trade_history(self, ticker):
        pass

    @inlineCallbacks
    def onJoin(self, details):
        results = yield self.register(self)
        for success, result in results:
            if success:
                log("Registered %s." % self._registrations[result.id].procedure)
            else:
                error("Error registering method: %s." % result.value.args[0])

