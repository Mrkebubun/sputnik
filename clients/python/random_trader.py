#!/usr/bin/env python
__author__ = 'sameer'

import sys

from twisted.python import log
from twisted.internet import reactor, ssl, task

from autobahn.websocket import connectWS
from autobahn.wamp import WampClientFactory

from client import TradingBot
import random, string

uri = 'wss://sputnikmkt.com:8000'
class RandomBot(TradingBot):
    def getUsernamePassword(self):
        return ['randomtrader', 'randomtrader']

    def getUri(self):
        return uri

    def startAutomation(self):
        rate = 1

        self.place_orders = task.LoopingCall(self.placeRandomOrder)
        self.place_orders.start(1.0 * rate)

        self.chatter = task.LoopingCall(self.saySomethingRandom)
        self.chatter.start(30.0 * rate)

        self.cancel_orders = task.LoopingCall(self.cancelRandomOrder)
        self.cancel_orders.start(2.5 * rate)

        return True

    def placeRandomOrder(self):
        random_markets = []
        for ticker, contract in self.markets.iteritems():
            if contract['contract_type'] != "cash":
                random_markets.append(ticker)

        # Pick a market at random
        ticker = 'BTC/MXN'
        side = random.choice(["BUY", "SELL"])
        contract = self.markets[ticker]

        # Set a price/quantity that is reasonable for the market
        tick_size = contract['tick_size']
        lot_size = contract['lot_size']
        denominator = contract['denominator']


        # Look at best bid/ask
        try:
            best_bid = max([order['price'] for order in self.markets[ticker]['bids']])
            best_ask = min([order['price'] for order in self.markets[ticker]['asks']])

            # Pick a price somewhere deep in the book
            if side is 'BUY':
                price = random.randint(best_ask, best_ask * 1.1)
            else:
                price = random.randint(best_bid * 0.9, best_bid)

            price = int(price / (tick_size * denominator)) * tick_size * denominator
        except (ValueError, KeyError):
            # We don't have a best bid/ask, just pick a price randomly
            price = random.randint(7000,8000) * (tick_size * denominator)

        # a qty somewhere between 0.5 and 2 BTC
        quantity = random.randint(50,200) * lot_size

        self.placeOrder(ticker, quantity, price, side)

    def saySomethingRandom(self):
        random_saying = ''.join(random.choice(string.ascii_uppercase + string.digits) for x in range(8))
        self.chat(random_saying)

    def cancelRandomOrder(self):
        if len(self.orders.keys()) > 0:
            while True:
                order_to_cancel = random.choice(self.orders.keys())
                if not self.orders[order_to_cancel]['is_cancelled'] and self.orders[order_to_cancel]['quantity_left'] > 0:
                    break
            self.cancelOrder(order_to_cancel)

if __name__ == '__main__':

    if len(sys.argv) > 1 and sys.argv[1] == 'debug':
        log.startLogging(sys.stdout)
        debug = True
    else:
        debug = False

    log.startLogging(sys.stdout)
    factory = WampClientFactory(uri, debugWamp=debug)
    factory.protocol = RandomBot

    # null -> ....
    if factory.isSecure:
        contextFactory = ssl.ClientContextFactory()
    else:
        contextFactory = None

    connectWS(factory, contextFactory)
    reactor.run()
