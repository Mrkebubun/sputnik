__author__ = 'sameer'


import treq
import json
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor
from twisted.python import log
import string
import hmac
import hashlib
import time
from decimal import Decimal
from pprint import pprint

class BitStamp():
    def __init__(self, client_id, api_key, api_secret, endpoint="https://www.bitstamp.net/api/"):
        self.client_id = client_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.endpoint = endpoint

    def generate_auth(self):
        nonce = str(time.time())
        message = nonce + self.client_id + self.api_key
        signature = hmac.new(
            self.api_secret, msg=message, digestmod=hashlib.sha256)
        signature = signature.hexdigest().upper()
        return {
            'key': self.api_key, 'signature': signature, 'nonce': nonce
        }

    def onError(self, failure, call):
        log.err([call, failure.value.args])
        log.err(failure)

    @inlineCallbacks
    def handle_response(self, response):
        content = yield response.content()
        result = json.loads(content)
        returnValue(result)

    def post(self, *args, **kwargs):
        return treq.post(*args, **kwargs).addCallback(self.handle_response)

    def get(self, *args, **kwargs):
        return treq.get(*args, **kwargs).addCallback(self.handle_response)

    def getPositions(self):
        url = self.endpoint + "balance/"
        params = self.generate_auth()
        d = self.post(url, data=params)
        def _onPositions(result):
            processed = { 'BTC': {'position': Decimal(result['btc_balance'])},
                          'USD': {'position': Decimal(result['usd_balance'])} }
            return processed

        return d.addCallback(_onPositions).addErrback(self.onError, "getPositions")

    def getCurrentAddress(self, ticker):
        if ticker == 'BTC':
            params = self.generate_auth()
            url = self.endpoint + "bitcoin_deposit_address/"
            d = self.post(url, data=params)
        else:
            raise NotImplementedError

        return d.addErrback(self.onError, "getCurrentAddress")

    def requestWithdrawal(self, ticker, amount, address):
        if ticker == 'BTC':
            params = {'amount': amount,
                      'address': address}
            params.update(self.generate_auth())
            url = self.endpoint + "bitcoin_withdrawal/"
            d = self.post(url, data=params)
        else:
            raise NotImplementedError

        return d.addErrback(self.onError, "requestWithdrawal")

    def placeOrder(self, ticker, quantity, price, side):
        if ticker == 'BTC/USD':
            params = {'amount': quantity,
                      'price': price}
            params.update(self.generate_auth())
            if side == 'BUY':
                url = self.endpoint + "buy/"
            elif side == 'SELL':
                url = self.endpoint + "sell/"
            else:
                raise NotImplementedError

            d = self.post(url, data=params)
            def _onPlaceOrder(result):
                return result['id']

            return d.addCallback(_onPlaceOrder).addErrback(self.onError, "placeOrder")
        else:
            raise NotImplementedError

    def cancelOrder(self, id):
        params = {'id': id}
        params.update(self.generate_auth())
        url = self.endpoint + "cancel_order/"
        d = self.post(url, data=params)
        return d.addErrback(self.onError, "cancelOrder")

    def getOpenOrders(self):
        params = self.generate_auth()
        url = self.endpoint + "open_orders/"
        d = self.post(url, data=params)
        def _onOpenOrders(orders):
            return {order['id']: {'id': order['id'],
                           'side': "BUY" if order['side'] == 0 else "SELL",
                           'price': Decimal(order['price']),
                           'quantity': Decimal(order['amount']),
                           'quantity_left': Decimal(order['amount']),
                           'timestamp': int(order['datetime'] * 1e6)}
                    for order in orders}

        return d.addCallBack(_onOpenOrders).addErrback(self.onError, "getOpenOrders")

    def getOrderBook(self, ticker):
        if ticker == 'BTC/USD':
            url = self.endpoint + "order_book/"
            d = self.get(url)
            def _onBook(book):
                result = {'contract': ticker,
                        'bids': [{'price': Decimal(row[0]), 'quantity': Decimal(row[1])} for row in book['bids']],
                        'asks': [{'price': Decimal(row[0]), 'quantity': Decimal(row[1])} for row in book['asks']]}
                return result

            return d.addCallback(_onBook).addErrback(self.onError, "getOrderBook")
        else:
            raise NotImplementedError


if __name__ == "__main__":
    bitstamp = BitStamp('BLANK', 'BLANK', 'BLANK')
    d = bitstamp.getOrderBook('BTC/USD').addCallback(pprint)
    reactor.run()



