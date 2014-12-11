from sputnik import config
from sputnik import observatory
from sputnik import util

debug, log, warn, error, critical = observatory.get_loggers("svc_market")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin
from datetime import datetime

from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import wamp


class MarketService(ServicePlugin):
    def __init__(self):
        ServicePlugin.__init__(self)

    def init(self):
        self.receiver = self.require("sputnik.webserver.plugins.receiver.accountant.AccountantReceiver")
        self.receiver.listeners.append(self)
        self.markets = {}
        self.books = {}
        self.trades = {}
        self.ohlcv = {}

    def shutdown(self):
        self.receiver.listeners.remove(self)

    def reload(self):
        pass

    @wamp.register(u"service.market.get_markets")
    def get_markets(self):
        return [True, self.markets]

    @wamp.register(u"service.market.get_ohlcv_history")
    def get_ohlcv_history(self, ticker, period=None, start_timestamp=None,
            end_timestamp=None):
        if ticker not in self.markets:
            return [False, "No such ticker %s." % ticker]

        now = util.dt_to_timestamp(datetime.datetime.utcnow())
        start = start_timestamp or int(now - 5.184e12) # delta 60 days
        end = end_timestamp or now
        period = period or "day"
       
        data = self.ohlcv.get(ticker, {}).get(period, {})
        ohlcv = {key: value for key, value in data \
                if value["open_timestamp"] <= end and \
                start <= value["close_timestamp"]}

        return [True, ohlcv]

    @wamp.register(u"service.market.get_trade_history")
    def get_trade_history(self, ticker, from_timestamp=None, to_timestamp=None):
        if ticker not in self.markets:
            return [False, "No such ticker %s." % ticker]

        now = util.dt_to_timestamp(datetime.datetime.utcnow())
        start = from_timestamp or int(now - 3.6e9) # delta 1 hour
        end = to_timestamp or now
        
        history = [entry for entry in self.trades.get(ticker, []) \
                if start <= entry["timestamp"]<= end]
        return [True, history]

    @wamp.register(u"service.market.get_order_book")
    def get_order_book(self, ticker):
        if ticker not in self.markets:
            return [False, "No such ticker %s." % ticker]

        if ticker not in self.books:
            return [False, "No book for %s" % ticker]

        return [True, self.books[ticker]]

    @inlineCallbacks
    def onJoin(self, details):
        results = yield self.register(self)
        for success, result in results:
            if success:
                log("Registered %s." % self._registrations[result.id].procedure)
            else:
                error("Error registering method: %s." % result.value.args[0])

