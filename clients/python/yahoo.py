__author__ = 'sameer'
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor
from twisted.python import log
from pprint import pprint
import treq
from decimal import Decimal
from bs4 import BeautifulSoup

class Yahoo():
    @inlineCallbacks
    def getOrderBook(self, ticker):
        payout, denominated = ticker.split('/')
        url = "http://finance.yahoo.com/q?s=%s%s=X" % (payout, denominated)
        response = yield treq.get(url.encode('utf-8'))
        content = yield response.content()
        soup = BeautifulSoup(content)
        bid = Decimal(soup.find(id="yfs_b00_%s%s=x" % (payout.lower(), denominated.lower())).text.replace(',', ''))
        ask = Decimal(soup.find(id="yfs_a00_%s%s=x" % (payout.lower(), denominated.lower())).text.replace(',', ''))
        book = {'contract': ticker,
                'bids': [{'price': bid, 'quantity': 0}],
                'asks': [{'price': ask, 'quantity': 0}]}
        returnValue(book)

if __name__ == "__main__":
    yahoo = Yahoo()
    d = yahoo.getOrderBook('USD/MXN')
    d.addCallback(pprint).addErrback(log.err)

    reactor.run()