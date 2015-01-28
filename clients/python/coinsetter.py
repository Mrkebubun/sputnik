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

    @inlineCallbacks
    def connect(self):
        data = {'username': self.username,
                'password': self.password,
                'ipAddress': self.ip
                }
        session = yield self.post("clientSession", data=data)
        self.session_id = session['uuid']
        self.customer_id = session['customerUuid']

        account_list = yield self.post("customer/account")['accountList']
        self.account_uuids = [account['accountUuid'] for account in account_list]
        self.default_account = self.account_uuids[0]
        self.heartbeat = task.LoopingCall(self.call_heartbeat)
        self.heartbeat.start(60)

    def call_heartbeat(self):
        return self.get("clientSession/%s" % self.session_id, params={'action': 'HEARTBEAT'})

    @inlineCallbacks
    def placeOrder(self, contract, quantity, price, side):
        data = {'accountUuid': self.default_account,
                'customerUuid': self.customer_id,
                'orderType': "LIMIT",
                'requestedQuantity': quantity,
                'requestedPrice': price,
                'side': side,
                'symbol': contract.replace('/', '')
        }
        result = yield self.post("order", data=data)
        returnValue(result['uuid'])

    @inlineCallbacks
    def getPositions(self):
        result = yield self.get("customer/account/%s" % self.default_account)
        processed = {'BTC': {'position': Decimal(result['btcBalance'])},
                     'USD': {'position': Decimal(result['usdBalance'])}}
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
        result = yield self.get("customer/account/%s/order" % self.default_account, params={'view', "OPEN"})
        orders = {order['uuid']: {
                'id': order['uuid'],
                'side': order['side'],
                'price': Decimal(order['requestedPrice']),
                'quantity': Decimal(order['requestedQuantity']),
                'quantity_left': Decimal(order['openQuantity']),
                'timestamp': order['createDate']
            } for order in result}

        returnValue(orders)

    @inlineCallbacks
    def getOrderBook(self, ticker):
        result = yield self.get("marketdata/full_depth")
        book = {'contract': ticker,
                'bids': [{'price': Decimal(bid[0]), 'quantity': Decimal(bid[1])} for bid in result['bids']],
                'asks': [{'price': Decimal(ask[0]), 'quantity': Decimal(ask[1])} for ask in result['asks']],
                'timestamp': result['timeStamp']}
        returnValue(book)

    @inlineCallbacks
    def getTransactionHistory(self, start_datetime, end_datetime):
        params = {'dateStart': start_datetime.strftime("%d%m%Y"),
                  'dateEnd': end_datetime.strftime("%d%m%Y")}
        result = yield self.get("customer/account/%s/financialTransaction" % self.default_account, params=params)
        transactions = []
        epoch = datetime.utcfromtimestamp(0)

        for transaction in result['financialTransactionList']:
            timestamp = datetime.strptime(transaction['createDate'] + "000", "%m/%d/%Y %H:%M:%S.%f")
            if timestamp < start_datetime or timestamp > end_datetime:
                continue
            transactions.append({
                'timestamp': int((timestamp - epoch).total_seconds() * 1e6),
                'type': transaction['transactionCategoryName'],
                'contract': transaction['amountDenomination'],
                'quantity': Decimal(amount),
                'direction': 'debit',
                'note': transaction['referenceNumber']
            })

        returnValue(transactions)

    @inlineCallbacks
    def post(self, call, data):
        url = self.endpoint + call
        headers = {'content-type': 'application/json'}
        if self.session_id is not None:
            headers['coinsetter-client-session-id'] = self.session_id

        result = yield treq.post(url, data=json.dumps(data), headers=headers)
        content = yield result.content()
        parsed = json.loads(content)
        returnValue(parsed)

    @inlineCallbacks
    def get(self, call, params={}):
        url = self.endpoint + call
        headers = {'content-type': 'application/json'}
        if self.session_id is not None:
            headers['coinsetter-client-session-id'] = self.session_id

        result = yield treq.get(url, params=params, headers=headers)
        content = yield result.content()
        parsed = json.loads(content)
        returnValue(parsed)

    @inlineCallbacks
    def delete(self, call, params={}):
        url = self.endpoint + call
        headers = {'content-type': 'application/json'}
        if self.session_id is not None:
            headers['coinsetter-client-session-id'] = self.session_id

        result = yield treq.delete(url, params=params, headers=headers)
        content = yield result.content()
        parsed = json.loads(content)
        returnValue(parsed)