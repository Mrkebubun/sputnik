#!/usr/bin/env python
# Copyright (c) 2014, 2015 Mimetic Markets, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# 1. Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
# IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
# TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
# TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

__author__ = 'sameer'

import sys
from ConfigParser import ConfigParser
import logging

from twisted.internet import task
from twisted.python import log
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks

from sputnik import SputnikSession, Sputnik
from yahoo import Yahoo
from bitstamp import BitStamp
from kraken import Kraken

from decimal import Decimal

class MarketMakerBot(SputnikSession):
    external_markets = {}
    yahoo = Yahoo()
    bitstamp = BitStamp()
    kraken = Kraken()

    def startAutomationAfterMarkets(self):
        self.get_external_market = task.LoopingCall(self.getExternalMarket)
        self.get_external_market.start(float(self.factory.rate) * 6)

        self.monitor_orders = task.LoopingCall(self.monitorOrders)
        self.monitor_orders.start(float(self.factory.rate) * 1)

        return True

    # See if we have any orders on a given side
    def cancelOrders(self, ticker, side):
        for id, order in self.orders.items():
            if order['is_cancelled'] or order['quantity_left'] <= 0:
                continue

            if order['side'] == side and order['contract'] == ticker:
                self.cancelOrder(id)

    def checkOrders(self, side):
        for id, order in self.orders.items():
            if order['is_cancelled'] or order['quantity_left'] <= 0:
                continue

            if order['side'] == side:
                return True

        return False

    @inlineCallbacks
    def getExternalMarket(self):
        try:
            bitstamp_book = yield self.bitstamp.getOrderBook('BTC/USD')
            btcusd_bid = bitstamp_book['bids'][0]['price']
            btcusd_ask = bitstamp_book['asks'][0]['price']
        except Exception as e:
            # Unable to get markets, just exit
            print "unable to get external market data from bitstamp: %s" % e
            raise e

        for ticker, market in self.markets.iteritems():
            new_ask = None
            new_bid = None

            if ticker not in self.factory.ignore_contracts:
                if market['contract_type'] == "cash_pair":
                    if ticker == "BTC/USD":
                        new_bid = btcusd_bid
                        new_ask = btcusd_ask
                    else:
                        currency = market['denominated_contract_ticker']

                        try:
                        # Get Yahoo quote
                            yahoo_book = yield self.yahoo.getOrderBook('USD/%s' % currency)
                            bid = yahoo_book['bids'][0]['price']
                            ask = yahoo_book['asks'][0]['price']
                        except Exception as e:
                            # Unable to get markets, just exit
                            print "unable to get external market data from Yahoo: %s" % e
                            continue

                        new_bid = btcusd_bid * bid
                        new_ask = btcusd_ask * ask
                elif market['contract_type'] == "futures":
                    got_spot = False
                    if ticker.startswith("USDBTC"):
                        # Ignore BTC and USD interest rates
                        new_bid_spot = 10000/btcusd_ask
                        new_ask_spot = 10000/btcusd_bid
                        # Assume 10bps USD risk-free rate
                        base_rate = 0.0010
                        got_spot = True
                    elif ticker.startswith("LTCBTC"):
                        kraken_book = yield self.kraken.getOrderBook('BTC/LTC')
                        btcltc_bid = kraken_book['bids'][0]['price']
                        btcltc_ask = kraken_book['asks'][0]['price']
                        new_bid_spot = 10000/btcltc_ask
                        new_ask_spot = 10000/btcltc_bid
                        # Assume 10% LTC risk-free rate
                        base_rate = 0.10
                        got_spot = True

                    if got_spot:
                        from datetime import datetime
                        import util
                        timedelta_to_expiry = util.timestamp_to_dt(market['expiration']) - datetime.utcnow()
                        time_to_expiry = timedelta_to_expiry.total_seconds() / (365.25*24*60*60)
                        # Assume 5% BTC risk-free rate
                        btc_rate = 0.0500
                        import math
                        forward_factor = Decimal(math.exp((base_rate - btc_rate) * time_to_expiry))
                        new_bid = new_bid_spot * forward_factor
                        new_ask = new_ask_spot * forward_factor

                if new_ask is not None and new_bid is not None:
                    logging.info("%s: %f/%f" % (ticker, new_bid, new_ask))

                    # Make sure that the marketwe are making isn't crossed
                    if new_bid > new_ask:
                        tmp = new_bid
                        new_bid = new_ask
                        new_ask = tmp

                    # If it's matched or crossed make a spread just because
                    if self.price_to_wire(ticker, new_bid) >= self.price_to_wire(ticker, new_ask):
                        new_bid = min(new_bid, new_ask) - self.price_from_wire(ticker, self.markets[ticker]['tick_size'])
                        new_ask = max(new_bid, new_ask) + self.price_from_wire(ticker, self.markets[ticker]['tick_size'])

                    if ticker in self.external_markets:
                        if new_bid != self.external_markets[ticker]['bid']:
                            self.external_markets[ticker]['bid'] = new_bid
                            self.replaceBidAsk(ticker, new_bid, 'BUY')
                        if new_ask != self.external_markets[ticker]['ask']:
                            self.external_markets[ticker]['ask'] = new_ask
                            self.replaceBidAsk(ticker, new_ask, 'SELL')
                    else:
                        self.external_markets[ticker] = {'bid': new_bid, 'ask': new_ask}
                        self.replaceBidAsk(ticker, new_ask, 'SELL')
                        self.replaceBidAsk(ticker, new_bid, 'BUY')

    def replaceBidAsk(self, ticker, new_ba, side):
        self.cancelOrders(ticker, side)
        if self.markets[ticker]['contract_type'] == "futures":
            quantity = 10
        else:
            quantity = 2.5

        self.placeOrder(ticker, quantity, new_ba, side)

    def monitorOrders(self):
        for ticker, market in self.external_markets.iteritems():
            # Make sure we have orders open for both bid and ask
            for side in ['BUY', 'SELL']:
                total_qty = 0
                for id, order in self.orders.items():
                    if order['side'] == side and order['is_cancelled'] is False and order['contract'] == ticker:
                        total_qty += order['quantity_left']

                if self.markets[ticker]['contract_type'] == "futures":
                    qty_to_add = Decimal(10)
                else:
                    qty_to_add = Decimal(2.5)

                if qty_to_add > total_qty:
                    if side == 'BUY':
                        price = market['bid']
                    else:
                        price = market['ask']

                    self.placeOrder(ticker, qty_to_add - total_qty, price, side)

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s', level=logging.INFO)
    log.startLogging(sys.stdout)

    import argparse
    parser = argparse.ArgumentParser(description="Run sputnik sample marketmaker client")
    parser.add_argument("-c", "--config", dest="config", action="store",
                        help="Configuration file", default="client.ini")
    parser.add_argument("--debug", dest="debug", action="store_true",
                        help="Enable debugging output", default=False)
    args = parser.parse_args()
    config = ConfigParser()
    config.read(args.config)

    params = dict(config.items("sputnik"))
    params.update(dict(config.items("market_maker")))

    sputnik = Sputnik(debug=args.debug, bot=MarketMakerBot, **params)
    sputnik.on("disconnect", lambda x: reactor.stop())
    sputnik.connect()

    reactor.run()