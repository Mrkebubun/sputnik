import sys
from pprint import pprint

from twisted.python import log
from twisted.internet import reactor, ssl

from autobahn.websocket import connectWS
from autobahn.wamp import WampClientFactory, WampCraClientProtocol

import database as db
from pepsiClient import TradingBot


import json
import time
import random_trader
import numpy as np

class TickerBot(TradingBot):
    def __init__(self):
        self.asks = []
        self.bids = []
        self.volumeWeightedPrice = 0
        self.volume = 0
        TradingBot.__init__(self)

    def collectBook(self, book):
        for order in  book:
            if order['order_side'] == 1:
                self.asks.append(order['price'])
            else:
                self.bids.append(order['price'])
        self.fillBook()

    def randomCancel(self,openOrders):
        print "random cancel"
        for order in openOrders:
            test = random_trader.randint(0,10)
            print test
            if test == 0:
                oid = order['order_id']
                print 'cancelling order', oid
                self.cancelOrder(oid)
        self.action()

    def fillBook(self):
        print 'asks', self.asks
        print 'smallest ask:', min(self.asks)
        print 'bids', self.bids
        print 'largest bid:', min(self.bids)

    def collectTrades(self, trades):
        for trade in trades:
            self.volumeWeightedPrice += trade[1] * trade[2]
            self.volume += trade[2]
            print trade
        vwap = float(self.volumeWeightedPrice / self.volume)
        ask = int(1.025*vwap*np.exp(np.random.randn()/50-0.5/2500))
        bid = int(.975*vwap*np.exp(np.random.randn()/50-0.5/2500))

        print vwap
        print 'selling at:',  ask
        self.placeOrder('USD.13.7.31',np.random.poisson(5), ask, 1)

        print 'buying at:',  bid
        self.placeOrder('USD.13.7.31',np.random.poisson(5), bid, 0)
        self.action()


    def action(self):
        print 'sleeping'
        time.sleep(np.random.poisson(900))
        path = random_trader.randint(0,2)
        print path
        if path == 0:
            print 'sleeping'
            time.sleep(10)
            self.action()
        elif path == 1:
            self.getTradeHistory('USD.13.7.31', self.collectTrades)
        else:
            self.getOpenOrders(self.randomCancel)

        #self.getOrderBook('USD.13.7.31',self.collectBook)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'debug':
        log.startLogging(sys.stdout)
        debug = True
    else:
        debug = False

    log.startLogging(sys.stdout)
    # ws -> wss
    factory = WampClientFactory("ws://localhost:9000", debugWamp=debug)
    factory.protocol = TickerBot

    # null -> ....
    #if factory.isSecure:
     #   contextFactory = ssl.ClientContextFactory()

    #else:
    #    contextFactory = None
        # (factory) -> (factory, contextFActory)

    connectWS(factory )#, contextFactory)
    reactor.run()
