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
import random
import numpy as np

class TickerBot(TradingBot):
    def __init__(self):
        self.user = 'b'
        self.psswd = 'b'
        self.asks = []
        self.bids = []
        TradingBot.__init__(self)

    def collectBook(self, book):
        for order in  book:
            if order['order_side'] == 1:
                self.asks.append(order['price'])
            else:
                self.bids.append(order['price'])

        direction = random.randint(0,1)

        if len(self.asks) >0:
            ask = int(np.exp(np.random.randn()/50-0.5/2500)*min(self.asks))
            self.placeOrder('USD.13.7.31',np.random.poisson(5), ask, direction)

        if len(self.bids) >0:
            bid = int(np.exp(np.random.randn()/50-0.5/2500)*max(self.bids))
            self.placeOrder('USD.13.7.31',np.random.poisson(5), bid, direction)

        self.action()

    def randomCancel(self,openOrders):
        print "random cancel"
        for order in openOrders:
            test = random.randint(0,10)
            print test
            if test == 0:
                oid = order['order_id']
                print 'cancelling order', oid
                self.cancelOrder(oid)
        self.action()

    def action(self):
        self.getNewAddress()

#        print 'sleeping'
#        time.sleep(np.random.poisson(450))
#        path = random.randint(0, 2)
#        print path
#        if path == 0:
#            print 'sleeping'
#            time.sleep(10)
#            self.action()
#        elif path == 1:
#            self.getOrderBook('USD.13.7.31', self.collectBook)
#        else:
#            self.getOpenOrders(self.randomCancel)


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
    if factory.isSecure:
        contextFactory = ssl.ClientContextFactory()
    else:
        contextFactory = None
        # (factory) -> (factory, contextFActory)
    connectWS(factory, contextFactory)
    reactor.run()
