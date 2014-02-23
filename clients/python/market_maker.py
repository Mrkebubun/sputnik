#!/usr/bin/env python
__author__ = 'sameer'

import sys

from twisted.python import log
from twisted.internet import reactor, ssl, task

from autobahn.websocket import connectWS
from autobahn.wamp import WampClientFactory

from client import TradingBot
import urllib2
import json
from bs4 import BeautifulSoup

class MarketMakerBot(TradingBot):
    def getUsernamePassword(self):
        return ['marketmaker', 'marketmaker']

    def startAutomation(self):
        rate = 1

        self.btcmxn_bid = None
        self.btcmxn_ask = None

        self.get_external_market = task.LoopingCall(self.getExternalMarket)
        self.get_external_market.start(1.0)

        self.monitor_orders = task.LoopingCall(self.monitorOrders)
        self.monitor_orders.start(0.5)

        return True

    def getExternalMarket(self):
        url = "https://www.bitstamp.net/api/ticker/"
        file_handle = urllib2.urlopen(url)
        json_data = json.load(file_handle)
        btcusd_bid = float(json_data['bid'])
        btcusd_ask = float(json_data['ask'])

        # Get Yahoo USD/MXN quote
        url = "http://finance.yahoo.com/q?s=USDMXN=X"
        file_handle = urllib2.urlopen(url)
        soup = BeautifulSoup(file_handle)
        usdmxn_bid = float(soup.find(id="yfs_b00_usdmxn=x").text)
        usdmxn_ask = float(soup.find(id="yfs_a00_usdmxn=x").text)

        self.btcmxn_bid = btcusd_bid * usdmxn_bid
        self.btcmxn_ask = btcusd_ask * usdmxn_ask

    def monitorOrders(self):
        # Cancel any existing orders
        for id, order in self.orders.iteritems():
            if not order['is_cancelled'] and order['quantity_left'] > 0:
                self.cancelOrder(id)

        # Place two orders for the current bid and ask
        if int(self.btcmxn_bid) == int(self.btcmxn_ask):
            self.btcmxn_bid -= 1

        self.placeOrder('BTC/MXN', 1000000000, int(self.btcmxn_bid) * 100, 'BUY')
        self.placeOrder('BTC/MXN', 1000000000, int(self.btcmxn_ask) * 100, 'SELL')


if __name__ == '__main__':

    if len(sys.argv) > 1 and sys.argv[1] == 'debug':
        log.startLogging(sys.stdout)
        debug = True
    else:
        debug = False

    log.startLogging(sys.stdout)
    factory = WampClientFactory("ws://localhost:8000", debugWamp=debug)
    factory.protocol = MarketMakerBot

    # null -> ....
    if factory.isSecure:
        contextFactory = ssl.ClientContextFactory()
    else:
        contextFactory = None

    connectWS(factory, contextFactory)
    reactor.run()
