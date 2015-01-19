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

class BitStamp():
    def __init__(self, client_id=None, api_key=None, api_secret=None, endpoint="https://www.bitstamp.net/api/"):
        self.client_id = client_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.endpoint = endpoint

    def generate_auth(self):
        nonce = str(int(time.time() * 1e6))
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

    def post(self, url, data={}):
        return treq.post(url, data=json.dumps(data)).addCallback(self.handle_response)

    def get(self, url, params={}):
        return treq.get(url, params=params).addCallback(self.handle_response)

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

    @inlineCallbacks
    def getTransactionHistory(self, start_datetime, end_datetime):
        url = self.endpoint + "user_transactions/"
        transaction_history = []

        params = self.generate_auth()
        offset = 0
        limit = 100
        finished = False
        type_map = {0: 'Deposit',
                    1: 'Withdrawal',
                    2: 'Trade'}

        try:
            while not finished:
                params.update({'offset': offset, 'limit': limit, 'sort': 'desc'})
                history = yield self.post(url, data=params)
                count = 0
                for transaction in history:
                    count += 1
                    timestamp = datetime.fromtimestamp(transaction['datetime'])
                    if timestamp > end_datetime:
                        finished = True
                        break
                    if timestamp >= start_datetime:
                        transaction_usd = { 'timestamp': int(transaction['datetime'] * 1e6),
                                            'type': type_map[transaction['type']],
                                            'contract': 'USD',
                                            'quantity': Decimal(transaction['usd']),
                                            'direction': 'debit',
                                            'note': transaction['order_id'] }
                        transaction_btc = { 'timestamp': int(timestamp * 1e6),
                                            'type': type_map[transaction['type']],
                                            'contract': 'BTC',
                                            'quantity': Decimal(transaction['btc']),
                                            'direction': 'debit',
                                            'note': transaction['order_id'] }

                        transaction_history.append(transaction_usd)
                        transaction_history.append(transaction_btc)

                if count < limit:
                    finished = True
                else:
                    offset += limit

            returnValue(transaction_history)
        except Exception as e:
            self.onError(failure.Failure(), "getTransactionHistory")


if __name__ == "__main__":
    bitstamp = BitStamp()
    d = bitstamp.getOrderBook('BTC/USD').addCallback(pprint)
    reactor.run()



