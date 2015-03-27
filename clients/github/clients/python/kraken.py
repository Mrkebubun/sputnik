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

class Kraken():
    def __init__(self, client_id=None, api_key=None, api_secret=None, endpoint="https://api.kraken.com"):
        self.client_id = client_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.endpoint = endpoint
        self.markets = {}
        self.ticker_map = {'BTC/USD': 'XXBTZUSD',
                           'BTC/LTC': 'XXBTXLTC'}


    @inlineCallbacks
    def handle_response(self, response):
        content = yield response.content()
        result = json.loads(content)
        returnValue(result['result'])

    def post(self, url, data={}):
        return treq.post(url, data=json.dumps(data)).addCallback(self.handle_response)

    def get(self, url, params={}):
        return treq.get(url, params=params).addCallback(self.handle_response)

    @inlineCallbacks
    def getMarkets(self):
        asset_pairs = yield self.get(self.endpoint + "/0/public/AssetPairs")
        assets = yield self.get(self.endpoint + "/0/public/Assets")
        assets.update(asset_pairs)
        # TODO: Process this into standard format
        self.markets = assets
        returnValue(assets)

    @inlineCallbacks
    def getOrderBook(self, ticker):
        if ticker in self.ticker_map:
            symbol = self.ticker_map[ticker]
            url = self.endpoint + "/0/public/Depth"
            params = {'pair': symbol}
            result = yield self.get(url, params=params)
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



