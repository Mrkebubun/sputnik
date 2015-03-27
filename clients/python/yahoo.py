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
#

__author__ = 'sameer'
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor
from twisted.python import log
from pprint import pprint
import treq
from decimal import Decimal
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json

class Yahoo():
    def __init__(self, **kwargs):
        self.yahoo_uri = "http://finance.yahoo.com/"
        self.oanda_uri = "http://www.oanda.com/currency/"

    @inlineCallbacks
    def getOrderBook(self, ticker):
        payout, denominated = ticker.split('/')
        url =  self.yahoo_uri + "q"
        params = {'s': "%s%s=X" % (payout, denominated)}
        response = yield treq.get(url, params=params)
        content = yield response.content()
        soup = BeautifulSoup(content)
        bid = Decimal(soup.find(id="yfs_b00_%s%s=x" % (payout.lower(), denominated.lower())).text.replace(',', ''))
        ask = Decimal(soup.find(id="yfs_a00_%s%s=x" % (payout.lower(), denominated.lower())).text.replace(',', ''))
        book = {'contract': ticker,
                'bids': [{'price': bid, 'quantity': 0}],
                'asks': [{'price': ask, 'quantity': 0}]}
        returnValue(book)

    @inlineCallbacks
    def getOHLCVHistory(self, ticker, period="day", start_datetime=None, end_datetime=None):
        payout, denominated = ticker.split('/')

        url = self.oanda_uri + "historical-rates/update"
        params = {'date_fmt': 'us',
                  'start_date': start_datetime.strftime('%Y-%m-%d'),
                  'end_date': end_datetime.strftime('%Y-%m-%d'),
                  'period': "daily",
                  'quote_currency': payout,
                  'base_currency_0': denominated,
                  'rate': 0,
                  'view': 'table',
                  'display': 'absolute',
                  'price': 'bid',
                  'data_range': 'd90'}
        headers = {'X-Requested-With': 'XMLHttpRequest',
                   'X-Prototype-Version': '1.7',
                   'Referer': 'http://www.oanda.com/currency/historical-rates/'}
        try:
            response = yield treq.get(url, params=params, headers=headers)
        except Exception as e:
            pass
        content = yield response.content()
        parsed = json.loads(content)
        data = parsed['widget'][0]['data']
        ohlcv_history = {}

        for row in data:
            date = datetime.fromtimestamp(row[0]/1e3)
            price = float(row[1])
            epoch = datetime.utcfromtimestamp(0)
            open_timestamp = int((date - epoch).total_seconds() * 1e6)
            tomorrow_date = date + timedelta(days=1)
            close_timestamp = int((tomorrow_date - epoch).total_seconds() * 1e6) - 1

            ohlcv = {
                'contract': ticker,
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': 0,
                'vwap': price,
                'open_timestamp': open_timestamp,
                'close_timestamp': close_timestamp,
                'period': period
            }
            ohlcv_history[open_timestamp] = ohlcv

        returnValue(ohlcv_history)




if __name__ == "__main__":
    yahoo = Yahoo()
    #d = yahoo.getOrderBook('USD/MXN')
    #d.addCallback(pprint).addErrback(log.err)
    now = datetime.utcnow()
    d2 = yahoo.getOHLCVHistory('USD/HUF', start_datetime=now-timedelta(days=30), end_datetime=now)
    d2.addCallback(pprint).addErrback(log.err)

    reactor.run()