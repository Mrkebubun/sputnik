__author__ = 'sameer'
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor
from twisted.python import log
from pprint import pprint
import treq
from decimal import Decimal
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

class Yahoo():
    def __init__(self):
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

        url = self.oanda_uri + "historical-rates-classic"
        params = {'date_fmt': 'us',
                  'date1': start_datetime.strftime('%m/%d/%y'),
                  'date': end_datetime.strftime('%m/%d/%y'),
                  'exch': payout,
                  'expr': denominated,
                  'format': 'CSV',
                  'margin_fixed': '0',
                  'redirected': 1}
        try:
            response = yield treq.get(url, params=params)
        except Exception as e:
            pass
        content = yield response.content()
        soup = BeautifulSoup(content)
        content_section = soup.find(id="converter_table").find(id="content_section")
        pre = content_section.find('pre')
        rows = pre.text.split('\n')
        ohlcv_history = {}
        for row in rows:
            if not row:
                continue

            date_str, price_str = row.split(',')
            date = datetime.strptime(date_str, '%m/%d/%Y')
            price = Decimal(price_str)
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
    d2 = yahoo.getOHLCVHistory('HUF/USD', start_datetime=now-timedelta(days=30), end_datetime=now)
    d2.addCallback(pprint).addErrback(log.err)

    reactor.run()