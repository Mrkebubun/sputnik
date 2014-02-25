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
import time

uri = 'wss://sputnikmkt.com:8000'
class MarketMakerBot(TradingBot):
    def getUsernamePassword(self):
        return ['marketmaker', 'marketmaker']

    def getUri(self):
        return uri

    def startAutomation(self):
        rate = 1

        self.btcmxn_bid = None
        self.btcmxn_ask = None

        self.get_external_market = task.LoopingCall(self.getExternalMarket)
        self.get_external_market.start(rate * 1.0)

        self.monitor_orders = task.LoopingCall(self.monitorOrders)
        self.monitor_orders.start(rate * 1.0)

        return True

    # See if we have any orders on a given side
    def cancelOrders(self, side):
        for id, order in self.orders.iteritems():
            if order['is_cancelled'] or order['quantity_left'] <= 0:
                continue

            if order['side'] == side:
                self.cancelOrder(id)

    def checkOrders(self, side):
        for id, order in self.orders.iteritems():
            if order['is_cancelled'] or order['quantity_left'] <= 0:
                continue

            if order['side'] == side:
                return True

        return False

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

        btcmxn_bid = int(btcusd_bid * usdmxn_bid)
        btcmxn_ask = int(btcusd_ask * usdmxn_ask)
        if btcmxn_bid != self.btcmxn_bid:
            self.btcmxn_bid = btcmxn_bid
            self.replaceBidAsk(btcmxn_bid, 'BUY')
        if btcmxn_ask != self.btcmxn_ask:
            self.btcmxn_ask = btcmxn_ask
            self.replaceBidAsk(btcmxn_ask, 'SELL')

    def replaceBidAsk(self, new_ba, side):
        self.cancelOrders(side)
        self.btcmxn_bid = new_ba

        # Wait until cancel
        while self.checkOrders(side):
            time.sleep(0.5)

        self.placeOrder('BTC/MXN', 25000000, int(new_ba) * 100, side)

    def monitorOrders(self):
        # Make sure we have orders open for both bid and ask
        for side in ['BUY', 'SELL']:
            total_qty = 0
            for id, order in self.orders.iteritems():
                if order['side'] == side and order['is_cancelled'] is False:
                    total_qty += order['quantity_left']
            qty_to_add = 25000000 - total_qty
            if qty_to_add > 0:
                if side == 'BUY':
                    price = int(self.btcmxn_bid) * 100
                else:
                    price = int(self.btcmxn_ask) * 100

                self.placeOrder('BTC/MXN', qty_to_add, price, side)

if __name__ == '__main__':

    if len(sys.argv) > 1 and sys.argv[1] == 'debug':
        log.startLogging(sys.stdout)
        debug = True
    else:
        debug = False

    log.startLogging(sys.stdout)
    factory = WampClientFactory(uri, debugWamp=debug)
    factory.protocol = MarketMakerBot

    # null -> ....
    if factory.isSecure:
        contextFactory = ssl.ClientContextFactory()
    else:
        contextFactory = None

    connectWS(factory, contextFactory)
    reactor.run()
