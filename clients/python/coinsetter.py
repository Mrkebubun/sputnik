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

import treq
import json
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor, task
from twisted.python import log, failure
import string
import hmac
import hashlib
import time
from decimal import Decimal
from pprint import pprint
from datetime import datetime

class CoinSetter():
    def __init__(self, username, password, ip, endpoint="https://api.coinsetter.com/v1/"):
        self.username = username
        self.password = password
        self.ip = ip
        self.endpoint = endpoint
        self.session_id = None

        self.notifyConnect = None
        self.notifyDisconnect = None
        self.json = json.JSONDecoder(parse_float=Decimal)

    @inlineCallbacks
    def connect(self):
        data = {'username': self.username,
                'password': self.password,
                'ipAddress': self.ip
                }
        session = yield self.post("clientSession", data=data)
        self.session_id = session['uuid']
        self.customer_id = session['customerUuid']

        result = yield self.get("customer/account")
        account_list = result['accountList']
        self.account_uuids = [account['accountUuid'] for account in account_list]
        self.default_account = self.account_uuids[0]
        self.heartbeat = task.LoopingCall(self.call_heartbeat)
        self.heartbeat.start(60)
        if self.notifyConnect is not None:
            self.notifyConnect(self)

    @inlineCallbacks
    def call_heartbeat(self):
        try:
            result = yield self.put("clientSession/%s" % self.session_id, params={'action': 'HEARTBEAT'})
            if result['message'] != "OK":
                raise Exception("Heartbeat not OK")
        except Exception as e:
            log.err(e)
            if self.notifyDisconnect is not None:
                self.notifyDisconnect(self)
            raise e

    @inlineCallbacks
    def placeOrder(self, contract, quantity, price, side):
        data = {'accountUuid': self.default_account,
                'customerUuid': self.customer_id,
                'orderType': "LIMIT",
                'requestedQuantity': quantity,
                'requestedPrice': price,
                'side': side,
                'symbol': contract.replace('/', ''),
                'routingMethod': 2
        }
        result = yield self.post("order", data=data)
        returnValue(result['uuid'])

    @inlineCallbacks
    def getPositions(self):
        result = yield self.get("customer/account/%s" % self.default_account)
        processed = {'BTC': {'position': result['btcBalance']},
                     'USD': {'position': result['usdBalance']}}
        returnValue(processed)

    @inlineCallbacks
    def getCurrentAddress(self, ticker):
        raise NotImplementedError

    @inlineCallbacks
    def getNewAddress(self, ticker):
        raise NotImplementedError

    @inlineCallbacks
    def requestWithdrawal(self, ticker, amount, address):
        raise NotImplementedError

    @inlineCallbacks
    def cancelOrder(self, id):
        result = yield self.delete("order/%s" % id)
        returnValue(result)

    @inlineCallbacks
    def getOpenOrders(self):
        result = yield self.get("customer/account/%s/order" % self.default_account, params={'view': "OPEN"})
        orders = {order['uuid']: {
                'id': order['uuid'],
                'side': order['side'],
                'price': order['requestedPrice'],
                'quantity': order['requestedQuantity'],
                'quantity_left': order['openQuantity'],
                'contract': 'BTC/USD',
                'timestamp': int(order['createDate'] * 1e3)
            } for order in result['orderList']}

        returnValue(orders)

    @inlineCallbacks
    def getOrderBook(self, ticker):
        result = yield self.get("marketdata/full_depth")
        book = {'contract': ticker,
                'bids': [{'price': bid[0], 'quantity': bid[1]} for bid in result['bids']],
                'asks': [{'price': ask[0], 'quantity': ask[1]} for ask in result['asks']],
                'timestamp': None}
        returnValue(book)

    @inlineCallbacks
    def getTransactionHistory(self, start_datetime, end_datetime):
        params = {'dateStart': start_datetime.strftime("%d%m%Y"),
                  'dateEnd': end_datetime.strftime("%d%m%Y")}
        result = yield self.get("customer/account/%s/financialTransaction" % self.default_account, params=params)
        transactions = []
        epoch = datetime.utcfromtimestamp(0)

        for transaction in result['financialTransactionList']:
            timestamp = datetime.strptime(transaction['createDate'] + "000", "%d/%m/%Y %H:%M:%S.%f")
            if timestamp < start_datetime or timestamp > end_datetime:
                continue
            transactions.append({
                'timestamp': int((timestamp - epoch).total_seconds() * 1e6),
                'type': transaction['transactionCategoryName'],
                'contract': transaction['amountDenomination'],
                'quantity': abs(transaction['amount']),
                'direction': 'credit' if transaction['amount'] > 0 else 'debit',
                'note': transaction['referenceNumber']
            })

        returnValue(transactions)

    @inlineCallbacks
    def post(self, call, data={}):
        url = self.endpoint + call
        headers = {'content-type': 'application/json',
                   'accept': 'application/json'}
        if self.session_id is not None:
            headers['coinsetter-client-session-id'] = self.session_id.encode('utf-8')

        result = yield treq.post(url, data=json.dumps(data), headers=headers)
        content = yield result.content()
        parsed = self.json.decode(content)
        returnValue(parsed)

    @inlineCallbacks
    def get(self, call, params={}):
        url = self.endpoint + call
        headers = {'content-type': 'application/json',
                   'accept': 'application/json'}
        if self.session_id is not None:
            headers['coinsetter-client-session-id'] = self.session_id.encode('utf-8')

        result = yield treq.get(url.encode('utf-8'), params=params, headers=headers)
        content = yield result.content()
        parsed = self.json.decode(content)
        returnValue(parsed)

    @inlineCallbacks
    def delete(self, call, params={}):
        url = self.endpoint + call
        headers = {'content-type': 'application/json',
                   'accept': 'application/json'}
        if self.session_id is not None:
            headers['coinsetter-client-session-id'] = self.session_id.encode('utf-8')

        result = yield treq.delete(url.encode('utf-8'), params=params, headers=headers)
        content = yield result.content()
        parsed = self.json.decode(content)
        returnValue(parsed)

    @inlineCallbacks
    def put(self, call, params={}):
        url = self.endpoint + call
        headers = {'content-type': 'application/json',
                   'accept': 'application/json'}
        if self.session_id is not None:
            headers['coinsetter-client-session-id'] = self.session_id.encode('utf-8')

        result = yield treq.put(url.encode('utf-8'), params=params, headers=headers)
        content = yield result.content()
        parsed = self.json.decode(content)
        returnValue(parsed)

if __name__ == "__main__":
    username = "uisp8279hdwjmgwmwnsrzd324f6dk8x"
    password = "7132d0bf-37c0-4b57-ab6d-a27fbef56c0f"
    url = "https://staging-api.coinsetter.com/v1/"
    ip = "67.190.85.163"


    coinsetter = CoinSetter(username, password, ip, endpoint=url)

    @inlineCallbacks
    def main(coinsetter):
        yield coinsetter.connect()
        book = yield coinsetter.getOrderBook('BTC/USD')
        pprint(book)

        start = datetime.utcnow()

        positions = yield coinsetter.getPositions()
        pprint(positions)

        order = yield coinsetter.placeOrder('BTC/USD', 1, 200, 'BUY')
        pprint(order)

        orders = yield coinsetter.getOpenOrders()
        pprint(orders)

        result = yield coinsetter.cancelOrder(order)
        pprint(result)

        order = yield coinsetter.placeOrder('BTC/USD', 1, 1000, 'BUY')
        pprint(order)

        end = datetime.utcnow()

        transactions = yield coinsetter.getTransactionHistory(start, end)
        pprint(transactions)


        positions = yield coinsetter.getPositions()
        pprint(positions)

    main(coinsetter).addCallback(pprint).addErrback(log.err)
    reactor.run()


