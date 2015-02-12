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

from collections import deque
import sys
import logging
from ConfigParser import ConfigParser
from os import path

from twisted.internet import task
from twisted.python import log
from twisted.internet import reactor
from twisted.internet.endpoints import clientFromString
from autobahn.twisted import websocket
from autobahn.wamp import types

from sputnik import SputnikSession, BotFactory, Sputnik

import random



class RandomBot(SputnikSession):
    place_all_random = False

    def startAutomationAfterMarkets(self):
        self.place_orders = task.LoopingCall(self.placeRandomOrder)
        self.place_orders.start(1 * self.factory.rate)

        self.cancel_orders = task.LoopingCall(self.cancelRandomOrder)
        self.cancel_orders.start(1 * self.factory.rate)

        return True

    def placeRandomOrder(self):
        random_markets = []
        for ticker, contract in self.markets.iteritems():
            if contract['contract_type'] != "cash" and ticker not in self.factory.ignore_contracts:
                random_markets.append(ticker)

        # Pick a market at random
        if len(random_markets) == 0:
            return

        ticker = random.choice(random_markets)
        side = random.choice(["BUY", "SELL"])
        contract = self.markets[ticker]

        # Look at best bid/ask
        try:
            # Distance is [0.95,1.05]
            distance = float(random.randint(0,10))/100 + 0.95

            # Post something close to the bid or ask, depending on the size
            if side == 'BUY':
                best_ask = min([row['price'] for row in self.markets[ticker]['book']['asks']])
                price = float(best_ask) * distance
            else:
                best_bid = max([row['price'] for row in self.markets[ticker]['book']['bids']])
                price = float(best_bid) * distance

        except (ValueError, KeyError):
            # We don't have a best bid/ask. If it's a prediction contract, pick a random price
            if contract['contract_type'] == "prediction":
                price = float(random.randint(0,1000))/1000
            elif self.place_all_random:
                if contract['contract_type'] == "cash_pair":
                    price = self.price_from_wire(ticker, random.randint(0,1000) * contract['tick_size'])
                else:
                    return
            else:
                return

        # a qty somewhere between 0.5 and 2 BTC
        if contract['contract_type'] == "prediction":
            quantity = random.randint(1, 4)
        else:
            quantity = float(random.randint(50, 200))/100

        self.placeOrder(ticker, quantity, price, side)


    def cancelRandomOrder(self):
        order_to_cancel = None
        if len(self.orders.keys()) > 0:
            while True:
                order_to_cancel = random.choice(self.orders.keys())
                if not self.orders[order_to_cancel]['is_cancelled'] and self.orders[order_to_cancel]['quantity_left'] > 0:
                    break

            self.cancelOrder(order_to_cancel)

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s', level=logging.INFO)

    if len(sys.argv) > 1 and sys.argv[1] == 'debug':
        debug = True
    else:
        debug = False

    log.startLogging(sys.stdout)
    config = ConfigParser()
    config_file = path.abspath(path.join(path.dirname(__file__),
            "./client.ini"))
    config.read(config_file)
    params = dict(config.items("sputnik"))
    params.update(dict(config.items("market_maker")))

    sputnik = Sputnik(debug=debug, bot=RandomBot, **params)

    sputnik.on("disconnect", lambda x: reactor.stop())
    sputnik.connect()

    reactor.run()

