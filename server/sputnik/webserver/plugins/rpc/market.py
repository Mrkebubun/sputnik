from sputnik import config
from sputnik import observatory
from sputnik import util

debug, log, warn, error, critical = observatory.get_loggers("rpc_market")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin, schema, error_handler, WebserverException
from datetime import datetime

from twisted.internet.defer import inlineCallbacks, returnValue, gatherResults, succeed
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
    def init(self):
        yield ServicePlugin.init(self)

        self.db = self.require("sputnik.webserver.plugins.db.postgres.PostgresDatabase")
        self.administrator = self.require("sputnik.webserver.plugins.backend.administrator.AdministratorProxy")

        self.markets = yield self.db.get_markets()
        dl = []

        def get_ohlcv(trade_history, ticker):
            self.trade_history[ticker] = trade_history

            # Clear ohlcv history
            self.ohlcv_history[ticker] = {}
            for period in ["minute", "hour", "day"]:
                for trade in self.trade_history[ticker]:
                    self.update_ohlcv(trade, period=period)

        for ticker in self.markets.iterkeys():
            dl.append(self.db.get_trade_history(ticker).addCallback(get_ohlcv, ticker))

        yield gatherResults(dl)

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
                self.emit("ohlcv", ticker, prior_ohlcv)

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

    @wamp.register(u"rpc.market.get_markets")
    @error_handler
    @schema("public/market.json#get_markets")
    def get_markets(self):
        result = yield succeed(self.markets)
        returnValue(result)

    @wamp.register(u"rpc.market.get_ohlcv_history")
    @error_handler
    @schema("public/market.json#get_ohlcv_history")
    def get_ohlcv_history(self, ticker, period=None, start_timestamp=None,
            end_timestamp=None):
        if ticker not in self.markets:
            raise WebserverException("exceptions/webserver/no-such-ticker", ticker)

        now = util.dt_to_timestamp(datetime.utcnow())
        start = start_timestamp or int(now - 5.184e12) # delta 60 days
        end = end_timestamp or now
        period = period or "day"
       
        data = self.ohlcv_history.get(ticker, {}).get(period, {})
        ohlcv = yield succeed({key: value for key, value in data.iteritems() \
                if value["open_timestamp"] <= end and \
                start <= value["close_timestamp"]})

        returnValue(ohlcv)

    @wamp.register(u"rpc.market.get_trade_history")
    @error_handler
    @schema("public/market.json#get_trade_history")
    def get_trade_history(self, ticker, from_timestamp=None, to_timestamp=None):
        if ticker not in self.markets:
            raise WebserverException("exceptions/webserver/no-such-ticker", ticker)

        now = util.dt_to_timestamp(datetime.utcnow())
        start = from_timestamp or int(now - 3.6e9) # delta 1 hour
        end = to_timestamp or now
        
        history = yield succeed([entry for entry in self.trade_history.get(ticker, []) \
                if start <= entry["timestamp"] <= end])
        returnValue([True, history])

    @wamp.register(u"rpc.market.get_order_book")
    @error_handler
    @schema("public/market.json#get_order_book")
    def get_order_book(self, ticker):
        if ticker not in self.markets:
            raise WebserverException("exceptions/webserver/no-such-ticker", ticker)

        if ticker not in self.books:
            log("Warning: %s not in books" % ticker)
            # TODO: Get book from engine
            self.books[ticker] = {'contract': ticker, 'bids': [], 'asks': []}

        result = yield succeed(self.books[ticker])
        returnValue(result)

    @wamp.register(u'rpc.market.get_safe_prices')
    @error_handler
    @schema("public/market.json#get_safe_prices")
    def get_safe_prices(self, array_of_tickers=None):
        if array_of_tickers is not None:
            result = {ticker: self.safe_prices[ticker] for ticker in array_of_tickers}
        else:
            result = self.safe_prices

        r = yield succeed(result)
        returnValue(r)


