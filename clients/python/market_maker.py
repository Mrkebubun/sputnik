#!/usr/bin/env python
# Copyright (c) 2014, Mimetic Markets, Inc.
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
        self.monitor_orders.start(rate * 0.1)

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
        try:
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
        except Exception as e:
            # Unable to get markets, just exit
            print "unable to get external market data: %s" % e

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

        self.placeOrder('BTC/MXN', 25000000, int(new_ba) * 100, side)

    def monitorOrders(self):
        # Make sure we have orders open for both bid and ask
        if self.btcmxn_bid is None or self.btcmxn_ask is None:
            return

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
