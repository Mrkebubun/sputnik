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


import treq
import json
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor
from twisted.python import log, failure
import string
import hmac
import hashlib
import time
from decimal import Decimal
from pprint import pprint
from datetime import datetime
import urllib
from pyee import EventEmitter

class Kraken(EventEmitter):
    def __init__(self, id=None, secret=None, endpoint="https://api.kraken.com"):
        self.api_key = id
        self.api_secret = secret
        self.endpoint = endpoint
        self.markets = {}
        self.api_version = 0
        self.ticker_map = {'BTC/USD': 'XXBTZUSD',
                           'BTC/LTC': 'XXBTXLTC',
                           'LTC': 'XLTC',
                           'BTC': 'XBTC',
                           'USD': 'ZUSD'}
        self.reverse_ticker_map = {v: k for k, v in self.ticker_map.iteritems()}

    @inlineCallbacks
    def connect(self):
        # Make sure we can get the time
        # TODO: make sure we can do something that requires auth
        yield self.public("Time")
        self.emit("connect", self)

    @inlineCallbacks
    def handle_response(self, response):
        content = yield response.content()
        result = json.loads(content)
        returnValue(result['result'])

    @inlineCallbacks
    def placeOrder(self, contract, quantity, price, side):
        if contract in self.ticker_map:
            pair = self.ticker_map[contract]
            info_params = {'pair': pair}
            info = yield self.public("AssetPairs", info_params)
            lot_multiplier = info[pair]['lot_multiplier']
            params = {'pairs': pair,
                      'type': "buy" if side == "BUY" else "sell",
                      'price': price,
                      'volume': quantity/lot_multiplier
            }
            result = yield self.private("AddOrder", params)
            returnValue(result['txid'][0])
        else:
            raise NotImplementedError

    @inlineCallbacks
    def getPositions(self):
        result = yield self.private("Balance")
        positions = {self.reverse_ticker_map[position['pair']]:  {'position': position['balance'] } for position in result}
        returnValue(positions)

    @inlineCallbacks
    def getCurrentAddress(self, ticker):
        if ticker in self.ticker_map:
            params = {'asset': self.ticker_map[ticker],
                      'method': '?',
                      'new': False}
            result = self.private("DepositAddresses", params)
            returnValue(result['address'])
        else:
            raise NotImplementedError

    @inlineCallbacks
    def getNewAddress(self, ticker):
        if ticker in self.ticker_map:
            params = {'asset': self.ticker_map[ticker],
                      'method': '?',
                      'new': True}
            result = yield self.private("DepositAddresses", params)
            returnValue(result['address'])
        else:
            raise NotImplementedError

    @inlineCallbacks
    def requestWithdrawal(self, ticker, amount, address):
        if ticker in self.ticker_map:
            params = {'asset': self.ticker_map[ticker],
                      'key': address,
                      'amount': amount}
            result = yield self.private("Withdraw", params)
            returnValue(result['refid'])
        else:
            raise NotImplementedError

    @inlineCallbacks
    def cancelOrder(self, id):
        result = yield self.private("CancelOrder", {'txid': id})
        returnValue(result['count'] > 0)

    @inlineCallbacks
    def getOpenOrders(self):
        result = yield self.private("OpenOrders")
        orders = {order['refid']: {
            'id': order['refid'],
            'side': "BUY" if order['descr']['type'] == "buy" else "SELL",
            'price': Decimal(order['descr']['price']),
            'quantity': Decimal(order['vol']),
            'quantity_left': Decimal(order['vol'] - order['vol_exec']),
            'contract': self.reverse_ticker_map[order['descr']['pair']],
            'timestamp': int(order['opentm'] * 1e6)
        } for order in result}
        returnValue(orders)

    @inlineCallbacks
    def getTransactionHistory(self, start_datetime, end_datetime):
        params = {
            'start': util.dt_to_timestamp(start_datetime)/1e6,
            'end': util.dt_to_timestamp(end_datetime)/1e6
        }
        result = yield self.private("Ledgers", params)
        type_map = {'deposit': "Deposit",
                    'withdrawal': "Withdrawal",
                    'trade': "Trade",
                    'margin': "Margin"}

        transactions = [{'timestamp': int(tx['time'] * 1e6),
                         'type': type_map[tx['type']],
                        'contract': self.reverse_ticker_map[tx['asset']],
                        'quantity': Decimal(abs(tx['amount'])),
                        'direction': 'credit' if tx['amount'] > 0 else 'debit',
                        'note': None}
                        for tx in result.values()]
        returnValue(transactions)

    def private(self, method, params = {}):
        urlpath = "%s/%s/private/%s" % (self.endpoint, self.api_version, method)
        nonce = int(time.time() * 1e6)
        params['nonce'] = nonce
        postdata = urllib.urlencode(params)
        message = urlpath + hashlib.sha256(str(nonce) + postdata).digest()
        signature = hmac.new(base64.base64decode(self.api_secret), message, hashlib.sha512)
        headers = {
            'API-Key': self.api_key,
            'API-Sign': base64.b64encode(signature.digest())
        }

        return treq.post(urlpath, data=params, headers=headers).addCallback(self.handle_response)

    def public(self, method, params = {}):
        urlpath = "%s/%s/public/%s" % (self.endpoint, self.api_version, method)
        return treq.get(urlpath, params=params).addCallback(self.handle_response)

    @inlineCallbacks
    def getMarkets(self):
        asset_pairs = yield self.public("AssetPairs")
        assets = yield self.public("Assets")
        assets.update(asset_pairs)
        # TODO: Process this into standard format
        self.markets = assets
        returnValue(assets)

    @inlineCallbacks
    def getOrderBook(self, ticker):
        if ticker in self.ticker_map:
            symbol = self.ticker_map[ticker]
            params = {'pair': symbol}
            result = yield self.public("Depth", params)
            book = {'contract': ticker,
                    'bids': [{'price': Decimal(r[0]), 'quantity': Decimal(r[1])} for r in result[symbol]['bids']],
                    'asks': [{'price': Decimal(r[0]), 'quantity': Decimal(r[1])} for r in result[symbol]['asks']]
            }
            returnValue(book)
        else:
            raise NotImplementedError

if __name__ == "__main__":
    kraken = Kraken()
    d = kraken.getMarkets().addCallback(pprint)
    #d = kraken.getOrderBook('BTC/LTC').addCallback(pprint).addErrback(log.err)
    reactor.run()



