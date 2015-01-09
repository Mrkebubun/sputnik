from sputnik import config
from sputnik import observatory
from sputnik import util

debug, log, warn, error, critical = observatory.get_loggers("feeds_market")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin
from datetime import datetime

from twisted.internet.defer import inlineCallbacks, returnValue, gatherResults
from autobahn import wamp


class MarketAnnouncer(ServicePlugin):
    def init(self):
        self.db = self.require("sputnik.webserver.plugins.db.postgres.PostgresDatabase")

    @inlineCallbacks
    def onJoin(self, session):
        for market in (yield self.db.get_markets()):
            for feed in ["trade", "book", "safe_prices", "ohlcv"]:
                yield self.subscribe(lambda x: None, u"feeds.market.%s.%s" % \
                        (feed, self.encode_ticker(market)))

    def encode_ticker(self, ticker):
        return ticker.replace("/", "_").lower()

    def on_trade(self, ticker, trade):
        ticker = self.encode_ticker(ticker)
        self.publish(u"feeds.market.trade.%s" % ticker, trade)

    def on_book(self, ticker, book):
        ticker = self.encode_ticker(ticker)
        self.publish(u"feeds.market.book.%s" % ticker, book)

    def on_safe_prices(self, ticker, price):
        ticker = self.encode_ticker(ticker)
        self.publish(u"feeds.market.safe_prices.%s" % ticker, price)

    def on_ohlcv(self, ticker, ohlcv):
        ticker = self.encode_ticker(ticker)
        self.publish(u"feeds.market.ohlcv.%s" % ticker, ohlcv)

