__author__ = 'sameer'

import treq
import hmac
import hashlib
import json
import time
import base64
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor
from decimal import Decimal
import util

class BitFinex():
    def __init__(self, api_key, api_secret, endpoint="https://api.bitfinex.com"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.endpoint = endpoint

    def get_auth(self, call, params):
        nonce = str(int(time.time() * 1e6))
        params.update({'nonce': nonce,
                       'request': call})
        payload = base64.b64encode(json.dumps(params))
        signature = hmac.new(self.api_secret, msg=payload, digestmod=hashlib.sha384).hexdigest().upper()
        headers = {'x-bfx-apikey': self.api_key,
                   'x-bfx-payload': payload,
                   'x-bfx-signature': signature}
        return headers

    @inlineCallbacks
    def get(self, call, params={}):
        url = self.endpoint + call
        response = yield treq.get(url, params=params)
        content = yield response.content()
        result = json.loads(content)
        returnValue(result)

    @inlineCallbacks
    def post(self, call, data={}):
        url = self.endpoint + call
        headers = self.get_auth(call, data)
        response = yield treq.post(url)
        content = yield response.content()
        result = json.loads(content)
        returnValue(result)

    def ticker_to_symbol(self, ticker):
        symbol = ticker.lower().replace('/', '')
        return symbol

    def symbol_to_ticker(self, symbol):
        upper = symbol.upper()
        ticker = upper[:3] + "/" + upper[4:]
        return ticker

    @inlineCallbacks
    def getOrderBook(self, ticker):
        symbol = self.ticker_to_symbol(ticker)
        call = "/v1/book/%s" % symbol
        result = yield self.get(call)
        book = {'contract': ticker,
                'bids': [{'price': Decimal(bid['price']), 'quantity': Decimal(bid['amount'])} for bid in result['bids']],
                'asks': [{'price': Decimal(ask['price']), 'quantity': Decimal(ask['amount'])} for ask in result['asks']],
                'timestamp': None}

    @inlineCallbacks
    def getNewAddress(self, ticker):
        if ticker == "BTC":
            call = "/v1/deposit/new"
            data = {'currency': ticker,
                    'method': 'bitcoin',
                    'wallet_name': 'trading'}
            result = yield self.post(call, data=data)
            if result['result'] != 'success':
                raise Exception(result['address'])
            else:
                returnValue(result['address'])
        else:
            raise NotImplementedError

    def getCurrentAddress(self, ticker):
        return self.getNewAddress(ticker)

    def requestWithdrawal(self, ticker):
        raise NotImplementedError

    @inlineCallbacks
    def placeOrder(self, ticker, quantity, price, side):
        symbol = self.ticker_to_symbol(ticker)
        call = "/v1/order/new"
        data = {'symbol': symbol,
                'amount': str(quantity),
                'price': str(price),
                'side': side.lower(),
                'type': 'limit'}
        result = yield self.post(call, data=data)
        returnValue(result['order_id'])

    @inlineCallbacks
    def cancelOrder(self, order_id):
        call = "/v1/order/cancel"
        data = {'order_id': order_id}
        result = yield self.post(call, data=data)
        returnValue(result)

    @inlineCallbacks
    def getOpenOrders(self):
        call = "/v1/orders"
        result = yield self.post(call)
        orders = {order['order_id']: {'contract': self.symbol_to_ticker(order['symbol']),
                       'price': Decimal(order['price']),
                       'timestamp': int(order['timestamp'] * 1e6),
                       'quantity': Decimal(order['original_amount']),
                       'quantity_left': Decimal(order['remaining_amount']),
                       'is_cancelled': order['is_cancelled'],
                       'id': order['order_id']}
        for order in result}
        returnValue(orders)

    @inlineCallbacks
    def getPositions(self):
        call = "/v1/balances"
        result = yield self.post(call)
        positions = {balance['currency']: {'position': Decimal(balance['amount'])} for balance in result}
        returnValue(positions)

        # We need this call for swaps and stuff?
        # call = "/v1/positions"
        # result = yield self.post(call)
        # positions = {}
        # raise NotImplementedError

    @inlineCallbacks
    def getTransactionHistory(self, start_datetime, end_datetime):
        start_timestamp = int(util.dt_to_timestamp(start_datetime)/1e6)
        end_timestamp = int(util.dt_to_timestamp(end_datetime)/1e6)
        call = "/v1/history"
        result = []
        for currency in ['USD', 'BTC']:
            data = {'currency': currency,
                    'since': start_timestamp,
                    'until': end_timestamp}
            result += yield self.post(call, data=data)
        transactions = [{'timestamp': int(transaction['timestamp'] * 1e6),
                         'contract': transaction['currency'],
                         'quantity': abs(Decimal(transaction['amount'])),
                         'direction': 'credit' if transaction['amount'] > 0 else 'debit',
                         'balance': Decimal(transaction['balance']),
                         'note': transaction['description']}
                        for transaction in result]
        returnValue(transactions)






if __name__ == "__main__":
    bitfinex = BitFinex("BLAH", "BLAH")
    bitfinex.getOrderBook('BTC/USD')

    reactor.run()



        

