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
        self.markets = {}
        self.books = {}
        self.trade_history = {}
        self.ohlcv_history = {}
        self.safe_prices = {}

    @inlineCallbacks
    def init(self, receiver_plugins=[]):
        ServicePlugin.init(self, receiver_plugins=["sputnik.webserver.plugins.receiver.accountant.AccountantReceiver",
                                                   "sputnik.webserver.plugins.receiver.engine.EngineReceiver"])

        self.db = self.require("sputnik.webserver.plugins.db.postgres.PostgresDatabase")
        self.markets = yield self.db.get_markets()
        for ticker in self.markets.iterkeys():
            self.trade_history[ticker] = yield self.db.get_trade_history(ticker)

            # Clear ohlcv history
            self.ohlcv_history[ticker] = {}
            for period in ["minute", "hour", "day"]:
                for trade in self.trade_history[ticker]:
                    self.update_ohlcv(trade, period=period)

    def on_trade(self, ticker, trade):
        self.trade_history[ticker].append(trade)
        for period in ["day", "hour", "minute"]:
            self.update_ohlcv(trade, period=period, update_feed=True)

    def on_book(self, ticker, book):
        self.books[ticker] = book

    def on_safe_prices(self, ticker, price):
        self.safe_prices[ticker] = price

    def update_ohlcv(self, trade, period="day", update_feed=False):
        """

        :param trade:
        :param period:
        """
        period_map = {'minute': 60,
                      'hour': 3600,
                      'day': 3600 * 24}
        period_seconds = int(period_map[period])
        period_micros = int(period_seconds * 1000000)
        ticker = trade['contract']
        if period not in self.ohlcv_history[ticker]:
            self.ohlcv_history[ticker][period] = {}

        start_period = int(trade['timestamp'] / period_micros) * period_micros
        if start_period not in self.ohlcv_history[ticker][period]:
            # This is a new period, so send out the prior period
            prior_period = start_period - period_micros
            if update_feed and prior_period in self.ohlcv_history[ticker][period]:
                prior_ohlcv = self.ohlcv_history[ticker][period][prior_period]
                # TODO: Fix this publish bit
                # self.dispatch(self.base_uri + "/feeds/ohlcv#%s" % ticker, prior_ohlcv)

            self.ohlcv_history[ticker][period][start_period] = {'period': period,
                                       'contract': ticker,
                                       'open': trade['price'],
                                       'low': trade['price'],
                                       'high': trade['price'],
                                       'close': trade['price'],
                                       'volume': trade['quantity'],
                                       'vwap': trade['price'],
                                       'open_timestamp': start_period,
                                       'close_timestamp': start_period + period_micros - 1}
        else:
            self.ohlcv_history[ticker][period][start_period]['low'] = min(trade['price'], self.ohlcv_history[ticker][period][start_period]['low'])
            self.ohlcv_history[ticker][period][start_period]['high'] = max(trade['price'], self.ohlcv_history[ticker][period][start_period]['high'])
            self.ohlcv_history[ticker][period][start_period]['close'] = trade['price']
            self.ohlcv_history[ticker][period][start_period]['vwap'] = ( self.ohlcv_history[ticker][period][start_period]['vwap'] * \
                                            self.ohlcv_history[ticker][period][start_period]['volume'] + trade['quantity'] * trade['price'] ) / \
                                          ( self.ohlcv_history[ticker][period][start_period]['volume'] + trade['quantity'] )
            self.ohlcv_history[ticker][period][start_period]['volume'] += trade['quantity']


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
       
        data = self.ohlcv_history.get(ticker, {}).get(period, {})
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
        
        history = [entry for entry in self.trade_history.get(ticker, []) \
                if start <= entry["timestamp"] <= end]
        return [True, history]

    @wamp.register(u"service.market.get_order_book")
    def get_order_book(self, ticker):
        if ticker not in self.markets:
            return [False, "No such ticker %s." % ticker]

        if ticker not in self.books:
            return [False, "No book for %s" % ticker]

        return [True, self.books[ticker]]

    @wamp.register(u'service.market.get_safe_prices')
    def get_safe_prices(self, array_of_tickers=None):
        if array_of_tickers is not None:
            return {ticker: self.safe_prices[ticker] for ticker in array_of_tickers}

        return self.safe_prices

    @inlineCallbacks
    def onJoin(self, details):
        results = yield self.register(self)
        for success, result in results:
            if success:
                log("Registered %s." % self._registrations[result.id].procedure)
            else:
                error("Error registering method: %s." % result.value.args[0])

