#!/usr/bin/env python
# Copyright (c) 2014, Mimetic Markets, Inc.
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

import sys
from pprint import pprint
import logging
from datetime import datetime, timedelta
import random
import string
from ConfigParser import ConfigParser
from os import path
from decimal import Decimal

from twisted.python import log
from twisted.internet import reactor, defer
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.endpoints import clientFromString
from twisted.internet.task import deferLater
from autobahn.twisted import wamp, websocket
from autobahn.wamp import types
from autobahn.wamp import auth
import hashlib
import hmac
import treq
import json
import time

import Crypto.Random.random
from copy import copy

class SputnikMixin():
    """
    Utility functions
    """

    def price_to_wire(self, contract, price):
        if self.markets[contract]['contract_type'] == "prediction":
            price = price * self.markets[contract]['denominator']
        else:
            price = price * self.markets[self.markets[contract]['denominated_contract_ticker']]['denominator'] * \
                    self.markets[contract]['denominator']

        return int(price - price % self.markets[contract]['tick_size'])

    def price_from_wire(self, contract, price):
        if self.markets[contract]['contract_type'] == "prediction":
            return Decimal(price) / self.markets[contract]['denominator']
        else:
            return Decimal(price) / (self.markets[self.markets[contract]['denominated_contract_ticker']]['denominator'] *
                            self.markets[contract]['denominator'])

    def quantity_from_wire(self, contract, quantity):
        if self.markets[contract]['contract_type'] == "prediction":
            return quantity
        elif self.markets[contract]['contract_type'] == "cash":
            return Decimal(quantity) / self.markets[contract]['denominator']
        else:
            return Decimal(quantity) / self.markets[self.markets[contract]['payout_contract_ticker']]['denominator']

    def quantity_to_wire(self, contract, quantity):
        if self.markets[contract]['contract_type'] == "prediction":
            return int(quantity)
        elif self.markets[contract]['contract_type'] == "cash":
            return int(quantity * self.markets[contract]['denominator'])
        else:
            quantity = quantity * self.markets[self.markets[contract]['payout_contract_ticker']]['denominator']
            return int(quantity - quantity % self.markets[contract]['lot_size'])

    def ohlcv_from_wire(self, wire_ohlcv):
        contract = wire_ohlcv['contract']
        ohlcv = {
            'contract': contract,
            'open': self.price_from_wire(contract, wire_ohlcv['open']),
            'high': self.price_from_wire(contract, wire_ohlcv['high']),
            'low': self.price_from_wire(contract, wire_ohlcv['low']),
            'close': self.price_from_wire(contract, wire_ohlcv['close']),
            'volume': self.quantity_from_wire(contract, wire_ohlcv['volume']),
            'vwap': self.price_from_wire(contract, wire_ohlcv['vwap']),
            'open_timestamp': wire_ohlcv['open_timestamp'],
            'close_timestamp': wire_ohlcv['close_timestamp'],
            'period': wire_ohlcv['period']
        }
        return ohlcv

    def ohlcv_history_from_wire(self, wire_ohlcv_history):
        return {timestamp: self.ohlcv_from_wire(wire_ohlcv)
                           for timestamp, wire_ohlcv in wire_ohlcv_history.iteritems()}

    def position_from_wire(self, wire_position):
        contract = wire_position['contract']
        position = copy(wire_position)
        position['position'] = self.quantity_from_wire(contract, wire_position['position'])
        if self.markets[contract]['contract_type'] == "futures":
            position['reference_price'] = self.price_from_wire(contract, wire_position['reference_price'])
        return position

    def order_to_wire(self, order):
        contract = order['contract']
        wire_order = copy(order)
        wire_order['price'] = self.price_to_wire(contract, order['price'])
        wire_order['quantity'] = self.quantity_to_wire(contract, order['quantity'])
        if 'quantity_left' in order:
            wire_order['quantity_left'] = self.quantity_to_wire(contract, order['quantity_left'])

        return wire_order

    def order_from_wire(self, wire_order):
        contract = wire_order['contract']
        order = copy(wire_order)
        order['price'] = self.price_from_wire(contract, wire_order['price'])
        order['quantity'] = self.quantity_from_wire(contract, wire_order['quantity'])
        order['quantity_left'] = self.quantity_from_wire(contract, wire_order['quantity_left'])
        return order

    def book_row_from_wire(self, contract, wire_book_row):
        book_row = copy(wire_book_row)
        book_row['price'] = self.price_from_wire(contract, wire_book_row['price'])
        book_row['quantity'] = self.price_from_wire(contract, wire_book_row['quantity'])
        return book_row

    def trade_from_wire(self, wire_trade):
        contract = wire_trade['contract']
        trade = copy(wire_trade)
        trade['price'] = self.price_from_wire(contract, wire_trade['price'])
        trade['quantity'] = self.quantity_from_wire(contract, wire_trade['quantity'])
        return trade

    def fill_from_wire(self, wire_fill):
        contract = wire_fill['contract']
        fill = copy(wire_fill)
        fill['fees'] = copy(wire_fill['fees'])
        fill['price'] = self.price_from_wire(contract, wire_fill['price'])
        fill['quantity'] = self.quantity_from_wire(contract, wire_fill['quantity'])
        for fee_contract, fee in wire_fill['fees'].iteritems():
            fill['fees'][fee_contract] = self.quantity_from_wire(fee_contract, fee)

        return fill

    def transaction_from_wire(self, wire_transaction):
        transaction = copy(wire_transaction)
        contract = wire_transaction['contract']
        transaction['quantity'] = self.quantity_from_wire(contract, wire_transaction['quantity'])
        if 'balance' in wire_transaction:
            transaction['balance'] = self.quantity_from_wire(contract, wire_transaction['balance'])

        return transaction

    def transaction_history_from_wire(self, wire_transaction_history):
        return [self.transaction_from_wire(wire_transaction)
                                              for wire_transaction in wire_transaction_history]

    def book_from_wire(self, wire_book):
        contract = wire_book['contract']
        book = copy(wire_book)
        book['bids'] = [self.book_row_from_wire(contract, row) for row in wire_book['bids']]
        book['asks'] = [self.book_row_from_wire(contract, row) for row in wire_book['asks']]
        return book

    def safe_prices_from_wire(self, wire_safe_prices):
        return {contract: self.price_from_wire(contract, price)
                        for contract, price in wire_safe_prices.iteritems()}

    def orders_from_wire(self, wire_orders):
        return {id: self.order_from_wire(wire_order) for id, wire_order in wire_orders.iteritems()}

    def positions_from_wire(self, wire_positions):
        return {contract: self.position_from_wire(wire_position) for contract, wire_position in self.wire_positions.iteritems()}

class SputnikSession(wamp.ApplicationSession, SputnikMixin):
    """
   Authenticated WAMP client using WAMP-Challenge-Response-Authentication ("WAMP-CRA").

   """
    auth = False

    def __init__(self, *args, **kwargs):
        wamp.ApplicationSession.__init__(self, *args, **kwargs)
        self.markets = {}
        self.wire_orders = {}
        self.wire_positions = {}
        self.last_internal_id = 0
        self.chats = []
        self.username = None

    """
    Login / connect functions
    """
    def onConnect(self):
        log.msg("connect")
        if self.factory.username is not None:
            log.msg("logging in as %s" % self.factory.username)
            self.join(self.config.realm, [u'wampcra'], unicode(self.factory.username))
        else:
            self.join(self.config.realm, [u'anonymous'])

        self.factory.onConnect(self)

    def onJoin(self, details):

        log.msg("Joined as %s" % details.authrole)
        d = self.getMarkets()
        d.addCallback(lambda x: self.startAutomationAfterMarkets())

        self.startAutomation()

        if details.authrole != u'anonymous':
            log.msg("Authenticated")
            self.auth = True
            self.username = details.authid
            self.subOrders()
            self.subFills()
            self.subTransactions()
            self.getOpenOrders()
            self.getPositions()

            self.startAutomationAfterAuth()

    def onChallenge(self, challenge):
        log.msg("got challenge: %s" % challenge)
        if challenge.method == u"wampcra":
            if u'salt' in challenge.extra:
                key = auth.derive_key(self.factory.password.encode('utf-8'),
                    challenge.extra['salt'].encode('utf-8'),
                    challenge.extra.get('iterations', None),
                    challenge.extra.get('keylen', None))
            else:
                key = self.factory.password.encode('utf-8')

            signature = auth.compute_wcs(key, challenge.extra['challenge'].encode('utf-8'))
            return signature.decode('ascii')
        else:
            raise Exception("don't know how to compute challenge for authmethod {}".format(challenge.method))


    def onDisconnect(self):
        log.msg("Disconnected")
        reactor.stop()


    def action(self):
        '''
        overwrite me
        '''
        return True

    def startAutomation(self):
        pass

    def startAutomationAfterAuth(self):
        pass

    def startAutomationAfterMarkets(self):
        pass

    def call(self, method_name, *args):
        log.msg("Calling %s with args=%s" % (method_name, args), logLevel=logging.DEBUG)
        d = wamp.ApplicationSession.call(self, unicode(method_name), *args)
        def onSuccess(result):
            if 'success' not in result:
                log.msg("RPC Protocol error in %s" % method_name)
                return result
            if result['success']:
                return result['result']
            else:
                return defer.fail(result['error'])

        d.addCallbacks(onSuccess, self.onRpcFailure)
        return d

    def subscribe(self, handler, topic, **kwargs):
        log.msg("subscribing to %s" % topic, logLevel=logging.DEBUG)

        # Wampv2 doesn't pass the topic to the handler, so wrap the topic here
        def wrapped_handler(*args, **kwargs):
            handler(topic, *args, **kwargs)

        wamp.ApplicationSession.subscribe(self, wrapped_handler, unicode(topic), **kwargs)

    @property
    def orders(self):
        return self.orders_from_wire(self.wire_orders)

    @property
    def positions(self):
        return self.positions_from_wire(self.wire_positions)

    """
    reactive events - on* 
    """

    # RPC Results
    def onMarkets(self, markets):
        pprint(["onMarkets", markets])
        return markets

    def onOpenOrders(self, orders):
        pprint(["onOpenOrders", orders])
        return orders

    def onPlaceOrder(self, id):
        """
        overwrite me
        """
        pprint(["onPlaceOrder", id])
        return id

    def onCancelOrder(self, success):
        pprint(["onCancelOrder", success])
        return success

    def onOHLCVHistory(self, ohlcv_history):
        pprint(["onOHLCVHistory", ohlcv_history])
        return ohlcv_history

    def onError(self, message, call=None):
        pprint(["Error", message.value, call])

    def onRpcFailure(self, event):
        pprint(["RpcFailure", event.value.args])

    def onAudit(self, audit):
        pprint(["onAudit", audit])
        return audit

    def onMakeAccount(self, event):
        pprint(["onMakeAccount", event])
        return event

    def onSupportNonce(self, event):
        pprint(["onSupportNonce", event])
        return event

    def onTransactionHistory(self, transaction_history):
        pprint(["onTransactionHistory", transaction_history])
        return transaction_history

    def onTradeHistory(self, trade_history):
        pprint(["onTradeHistory", trade_history])
        return trade_history

    def onNewAPICredentials(self, credentials):
        pprint(["onNewAPICredentials", credentials])
        return credentials

    def onPositions(self, positions):
        pprint(["onPositions", positions])
        return positions

    def onRequestWithdrawal(self, result):
        pprint(["onRequestWithdrawal", result])
        return result

    """
    Feed handlers
    """
    def onBook(self, topicUri, book):
        """
        overwrite me
        """
        pprint(["onBook", topicUri, book])
        return (topicUri, book)


    def onTrade(self, topicUri, trade):
        """
        overwrite me
        """
        pprint(["onTrade", topicUri, trade])
        return topicUri, trade

    def onSafePrice(self, topicUri, safe_price):
        """
        overwrite me
        """
        pprint(["onSafePrice", topicUri, safe_price])
        return topicUri, safe_price

    def onOrder(self, topicUri, order):
        """
        overwrite me
        """


        pprint(["onOrder", topicUri, order])
        return topicUri, order

    def onFill(self, topicUri, fill):
        """
        overwrite me
        """
        pprint(["onFill", topicUri, fill])
        return topicUri, fill

    def onTransaction(self, topicUri, transaction):
        """
        overwrite me
        """
        pprint(["onTransaction", topicUri, transaction])
        return topicUri, transaction

    def onOHLCV(self, topicUri, ohlcv):
        pprint(["onOHLCV", topicUri, ohlcv])
        return topicUri, ohlcv

    """
    Public Subscriptions
    """
    def encode_ticker(self, ticker):
        return ticker.replace("/", "_").lower()

    def subOHLCV(self, contract):
        uri = u"feeds.market.ohlcv.%s" % self.encode_ticker(contract)
        def _onOHLCV(uri, wire_ohlcv):
            return self.onOHLCV(uri, self.ohlcv_from_wire(wire_ohlcv))

        self.subscribe(_onOHLCV, uri)
        print "subscribed to: ", uri

    def _onBook(self, uri, wire_book):
        contract = wire_book['contract']
        self.markets[contract]['wire_book'] = wire_book

        book = self.book_from_wire(wire_book)

        self.markets[contract]['book'] = book
        return self.onBook(uri, book)

    def subBook(self, contract):
        uri = u"feeds.market.book.%s" % self.encode_ticker(contract)

        self.subscribe(self._onBook, uri)
        print 'subscribed to: ', uri

    def subTrades(self, contract):
        uri = u"feeds.market.trades.%s" % self.encode_ticker(contract)
        def _onTrade(uri, wire_trade):
            return self.onTrade(uri, self.trade_from_wire(wire_trade))

        self.subscribe(_onTrade, uri)
        print 'subscribed to: ', uri

    def subSafePrices(self, contract):
        uri = u"feeds.market.safe_prices.%s" % self.encode_ticker(contract)
        def _onSafePrice(uri, wire_safe_prices):
            return self.onSafePrice(uri, self.safe_prices_from_wire(wire_safe_prices))

        self.subscribe(_onSafePrice, uri)
        print 'subscribed to: ', uri

    """
    Private Subscriptions
    """
    def encode_username(self, username):
        return hashlib.sha256(username).hexdigest()

    def subOrders(self):
        uri = u"feeds.user.orders.%s" % self.encode_username(self.username)

        def _onOrder(uri, wire_order):
            id = wire_order['id']
            if id in self.wire_orders and (wire_order['is_cancelled'] or wire_order['quantity_left'] == 0):
                del self.wire_orders[id]
            else:
                # onPlaceOrder will delete the internal order so we don't need to find it here
                # and delete it

                # Add or update, if not cancelled and quantity_left > 0
                if not wire_order['is_cancelled'] and wire_order['quantity_left'] > 0:
                    self.wire_orders[id] = wire_order

            return self.onOrder(uri, self.order_from_wire(wire_order))

        self.subscribe(_onOrder, uri)
        print 'subscribed to: ', uri

    def subFills(self):
        uri = u"feeds.user.fills.%s" % self.encode_username(self.username)

        def _onFill(topicUri, fill):
            return self.onFill(topicUri, self.fill_from_wire(fill))

        self.subscribe(_onFill, uri)
        print 'subscribed to: ', uri

    def subTransactions(self):
        uri = u"feeds.user.transactions.%s" % self.encode_username(self.username)
        def _onTransaction(uri, wire_transaction):
            contract = wire_transaction['contract']

            if wire_transaction['direction'] == 'credit':
                sign = 1
            else:
                sign = -1

            if contract in self.wire_positions:
                self.wire_positions[contract]['position'] += sign * transaction['quantity']
            else:
                self.wire_positions[contract] = { 'position': sign * transaction['quantity'],
                                                'contract': contract }

            return self.onTransaction(uri, self.transaction_from_wire(wire_transaction))

        self.subscribe(_onTransaction, uri)
        print 'subscribed to: ', uri

    """
    Public RPC Calls
    """

    def getTradeHistory(self, contract):
        d = self.call(u"rpc.market.get_trade_history", contract)
        def _onTradeHistory(wire_trade_history):
            return self.onTradeHistory([self.trade_from_wire(wire_trade) for wire_trade in wire_trade_history])

        return d.addCallback(_onTradeHistory).addErrback(self.onError, "getTradeHistory")

    def getMarkets(self):
        d = self.call(u"rpc.market.get_markets")
        def _onMarkets(event):
            self.markets = event
            if self.markets is not None:
                for contract, details in self.markets.iteritems():
                    if details['contract_type'] != "cash":
                        self.getOrderBook(contract)
                        self.subBook(contract)
                        self.subTrades(contract)
                        self.subSafePrices(contract)
                        self.subOHLCV(contract)

            return self.onMarkets(event)

        return d.addCallback(_onMarkets).addErrback(self.onError, "getMarkets")

    def getOrderBook(self, contract):
        d = self.call(u"rpc.market.get_order_book", contract)
        return d.addCallback(lambda x: self._onBook(u"rpc.market.get_order_book", x)).addErrback(self.onError, "getOrderBook")

    def getAudit(self):
        d = self.call(u"rpc.info.get_audit")
        return d.addCallback(self.onAudit).addErrback(self.onError, "getAudit")

    def getOHLCVHistory(self, contract, period="day", start_datetime=None, end_datetime=None):
        epoch = datetime.utcfromtimestamp(0)
        if start_datetime is not None:
            start_timestamp = int((start_datetime - epoch).total_seconds() * 1e6)
        else:
            start_timestamp = None

        if end_datetime is not None:
            end_timestamp = int((end_datetime - epoch).total_seconds() * 1e6)
        else:
            end_timestamp = None

        def _onOHLCVHistory(wire_ohlcv_history):
            return self.onOHLCVHistory(self.ohlcv_history_from_wire(wire_ohlcv_history))

        d = self.call(u"rpc.market.get_ohlcv_history", contract, period, start_timestamp, end_timestamp)
        return d.addCallback(_onOHLCVHistory).addErrback(self.onError, "getOHLCVHistory")

    def makeAccount(self, username, password, email, nickname):
        alphabet = string.digits + string.lowercase
        num = Crypto.Random.random.getrandbits(64)
        salt = ""
        while num != 0:
            num, i = divmod(num, len(alphabet))
            salt = alphabet[i] + salt
        extra = {"salt":salt, "keylen":32, "iterations":1000}
        password_hash = auth.derive_key(password.encode('utf-8'),
                                        extra['salt'].encode('utf-8'),
                                        extra['iterations'],
                                        extra['keylen'])
        d = self.call(u"rpc.registrar.make_account", username, "%s:%s" % (salt, password_hash), email, nickname)
        return d.addCallback(self.onMakeAccount).addErrback(self.onError, "makeAccount")

    def getResetToken(self, username):
        d = self.call(u"rpc.registrar.get_reset_token", username)
        return d.addCallback(pprint).addErrback(self.onError, "getResetToken")

    def getExchangeInfo(self):
        d = self.call(u"rpc.info.get_exchange_info")
        return d.addCallback(pprint).addErrback(self.onError, "getExchangeInfo")

    """
    Private RPC Calls
    """
    def getNewAPICredentials(self):
        d = self.call(u"rpc.token.get_new_api_credentials")
        return d.addCallback(self.onNewAPICredentials).addErrback(self.onError, "getNewAPICredentials")

    def getPositions(self):
        d = self.call(u"rpc.trader.get_positions")
        def _onPositions(wire_positions):
            self.wire_positions = wire_positions
            return self.onPositions(self.positions)

        return d.addCallback(_onPositions).addErrback(self.onError, "getPositions")

    def getCurrentAddress(self):
        d = self.call(u"rpc.trader.get_current_address")
        return d.addCallback(self.onGetCurrentAddress).addErrback(self.onError, "getCurrentAddress")

    def getNewAddress(self):
        d = self.call(u"rpc.trader.get_new_address")
        return d.addCallback(self.onGetNewAddress).addErrback(self.onError, "getNewAddress")

    def getOpenOrders(self):
        d = self.call(u"rpc.trader.get_open_orders")
        def _onOpenOrders(wire_orders):
            self.wire_orders = wire_orders
            return self.onOpenOrders(self.orders)

        return d.addCallback(_onOpenOrders).addErrback(self.onError, "getOpenOrders")

    def getTransactionHistory(self, start_datetime=None, end_datetime=None):
        if start_datetime is None:
            start_datetime = datetime.utcnow()-timedelta(days=2)
        if end_datetime is None:
            end_datetime = datetime.utcnow()

        epoch = datetime.utcfromtimestamp(0)
        start_timestamp = int((start_datetime - epoch).total_seconds() * 1e6)
        end_timestamp = int((end_datetime - epoch).total_seconds() * 1e6)

        def _onTransactionHistory(wire_transaction_history):
            return self.onTransactionHistory(self.transaction_history_from_wire(wire_transaction_history))

        d = self.call("rpc.trader.get_transaction_history", start_timestamp, end_timestamp)
        return d.addCallback(_onTransactionHistory).addErrback(self.onError, "getTransactionHistory")

    def requestSupportNonce(self, type='Compliance'):
        d = self.call(u"rpc.trader.request_support_nonce", type)
        return d.addCallback(self.onSupportNonce).addErrback(self.onError, "requestSupportNonce")

    def placeOrder(self, contract, quantity, price, side):
        ord = {}
        ord['contract'] = contract
        ord['quantity'] = self.quantity_to_wire(contract, quantity)
        ord['price'] = self.price_to_wire(contract, price)
        ord['side'] = side
        d = self.call(u"rpc.trader.place_order", ord)

        self.last_internal_id += 1
        ord['quantity_left'] = ord['quantity']
        ord['is_cancelled'] = False
        order_id = 'internal_%d' % self.last_internal_id
        self.wire_orders[order_id] = ord

        def onError(error):
            logging.info("removing internal order %s" % order_id)
            try:
                del self.wire_orders[order_id]
            except KeyError as e:
                logging.error("Unable to remove order: %s" % e)

            self.onError(error, "placeOrder")

        def _onPlaceOrder(new_id):
            if order_id in self.wire_orders:
                del self.wire_orders[order_id]

        return d.addCallbacks(_onPlaceOrder, onError)

    def requestWithdrawal(self, contract, amount, address):
        amount_wire = self.quantity_to_wire(contract, amount)
        d = self.call(u"rpc.trader.request_withdrawal", contract, amount_wire, address)
        return d.addCallback(self.onRequestWithdrawal).addErrback(self.onError, "requestWithdrawal")

    def cancelOrder(self, id):
        """
        cancels an order by its id.
        :param id: order id
        """
        if isinstance(id, basestring) and id.startswith('internal_'):
            logging.error("can't cancel internal order: %s" % id)
            return

        print "cancel order: %s" % id
        d = self.call(u"rpc.trader.cancel_order", int(id))
        def _onCancelOrder(success):
            if success and id in self.wire_orders:
                del self.wire_orders[id]

            return self.onCancelOrder(success)

        return d.addCallback(_onCancelOrder).addErrback(self.onError, "cancelOrder")


class BasicBot(SputnikSession):
    def onMakeAccount(self, event):
        SputnikSession.onMakeAccount(self, event)
        #self.authenticate()

    def startAutomation(self):
        # Test the audit
        # self.getAudit()
        #
        # # Test exchange info
        # self.getExchangeInfo()
        #
        # # Test some OHLCV history fns
        # self.getOHLCVHistory('BTC/HUF', 'day')
        # self.getOHLCVHistory('BTC/HUF', 'minute')
        #
        # # Now make an account
        # self.username = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        # self.password = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        # self.makeAccount(self.username, self.password, "test@m2.io", "Test User")
        self.getResetToken('marketmaker')
        pass

    def startAutomationAfterAuth(self):
        # self.getNewAPICredentials()
        # self.getTransactionHistory()
        # self.requestSupportNonce()
        pass

    def startAutomationAfterMarkets(self):
        self.placeOrder('BTC/HUF', 1, 5000, 'BUY')

class BotFactory(wamp.ApplicationSessionFactory):
    def __init__(self, **kwargs):
        self.username = kwargs.get('username')
        self.password = kwargs.get('password')
        self.ignore_contracts = kwargs.get('ignore_contracts')
        self.rate = kwargs.get('rate')
        self.onConnect = kwargs.get('onConnect')

        component_config = types.ComponentConfig(realm = u"sputnik")
        wamp.ApplicationSessionFactory.__init__(self, config=component_config)

def wait_for_session(f):
    def wrapped(self, *args, **kwargs):
        if self.session is None:
            return deferLater(reactor, 5, wrapped, self, *args, **kwargs)
        else:
            return f(self, *args, **kwargs)

    return wrapped

class Sputnik():
    def __init__(self, connection, bot_params, debug, bot=SputnikSession):
        self.debug = debug
        self.session_factory = BotFactory(onConnect=self.onConnect, **bot_params)
        self.session_factory.session = bot

        if connection['ssl']:
            self.base_uri = "wss://%s:%d/ws" % (connection['hostname'], connection['port'])
            self.connection_string = "ssl:host=%s:port=%d:caCertsDir=%s" % (connection['hostname'],
                                                                       connection['port'],
                                                                       connection['ca_certs_dir'])
        else:
            self.base_uri = "ws://%s:%d/ws" % (connection['hostname'], connection['port'])
            self.connection_string = "tcp:%s:%d" % (connection['hostname'], connection['port'])

        self.session = None
        self.transport_factory = websocket.WampWebSocketClientFactory(self.session_factory,
                                                                 url = self.base_uri, debug=self.debug,
                                                                 debug_wamp=self.debug)

    def connect(self):
        client = clientFromString(reactor, self.connection_string)
        def _connectError(failure):
            log.err(failure)
            reactor.stop()

        return client.connect(self.transport_factory).addErrback(_connectError)

    def onConnect(self, session):
        self.session = session

    @wait_for_session
    def getPositions(self):
        return defer.succeed(self.session.positions)

    @wait_for_session
    def getCurrentAddress(self, contract):
        return self.session.getCurrentAddress(contract)

    @wait_for_session
    def requestWithdrawal(self, contract, amount, address):
        return self.session.requestWithdrawal(contract, amount, address)

    @wait_for_session
    def placeOrder(self, contract, quantity, price, side):
        return self.session.placeOrder(contract, quantity, price, side)

    @wait_for_session
    def cancelOrder(self, id):
        return self.session.cancelOrder(id)

    @wait_for_session
    def getOpenOrders(self):
        return defer.succeed(self.session.orders)

    @wait_for_session
    def getOrderBook(self, contract):
        if 'book' not in self.session.markets[contract]:
            return deferLater(reactor, 5, self.getOrderBook, contract)
        else:
            return defer.succeed(self.session.markets[contract]['book'])

    @wait_for_session
    def getTransactionHistory(self, start_datetime, end_datetime):
        return self.session.getTransactionHistory(start_datetime, end_datetime)

class SputnikRest(SputnikMixin):
    def __init__(self, username=None, api_key=None, api_secret=None, endpoint=None, onInit=None):
        self.username = username
        self.api_key = api_key
        self.api_secret = api_secret
        self.endpoint = endpoint
        def _cb(markets):
            self.markets = markets
            if onInit is not None:
                onInit(self)

        self.getMarkets().addCallback(_cb)

    def generate_auth_json(self, params):
        nonce = int(time.time() * 1e6)
        params['auth'] = {'nonce': nonce,
                          'key': self.api_key
        }
        message = json.dumps(params)
        signature = hmac.new(self.api_secret.encode('utf-8'), msg=message.encode('utf-8'), digestmod=hashlib.sha256)
        signature = signature.hexdigest().upper()
        return (signature, message)

    def onError(self, failure, call):
        log.err([call, failure.value.args])
        log.err(failure)
        return failure

    @inlineCallbacks
    def handle_response(self, response):
        content = yield response.content()
        result = json.loads(content)
        if result['success']:
            returnValue(result['result'])
        else:
            raise Exception(*result['error'])

    def post(self, url, payload={}, auth=False):
        headers = {"content-type": "application/json"}
        params = {'payload': payload}
        if auth:
            (auth, message) = self.generate_auth_json(params)
            headers['authorization'] = auth
        else:
            message = json.dumps(params)

        return treq.post(url, data=message, headers=headers).addCallback(self.handle_response)

    def getMarkets(self):
        url = self.endpoint + "/rpc/market/get_markets"
        return self.post(url).addErrback(self.onError, "getMarkets")

    def getPositions(self):
        url = self.endpoint + "/rpc/trader/get_positions"
        return self.post(url, auth=True).addCallback(self.positions_from_wire).addErrback(self.onError, "getPositions")

    def getCurrentAddress(self, contract):
        url = self.endpoint + "/rpc/trader/get_current_address"
        payload = {'contract': contract}
        return self.post(url, payload=payload, auth=True).addErrback(self.onError, "getCurrentAddress")

    def requestWithdrawal(self, contract, amount, address):
        url = self.endpoint + "/rpc/trader/request_withdrawal"
        payload = {'contract': contract,
                  'amount': self.quantity_to_wire(contract, amount),
                  'address': address}
        return self.post(url, payload=payload, auth=True).addErrback(self.onError, "requestWithdrawal")

    def placeOrder(self, contract, quantity, price, side):
        url = self.endpoint + "/rpc/trader/place_order"
        payload = {'order': {'contract': contract,
                  'quantity': self.quantity_to_wire(contract, quantity),
                  'price': self.price_to_wire(contract, price),
                  'side': side }}
        return self.post(url, payload=payload, auth=True).addErrback(self.onError, "placeOrder")

    def cancelOrder(self, id):
        url = self.endpoint + "/rpc/trader/cancel_order"
        payload = {'id': id}
        return self.post(url, payload=payload, auth=True).addErrback(self.onError, "cancelOrder")

    def getOpenOrders(self):
        url = self.endpoint + "/rpc/trader/get_open_orders"
        return self.post(url, auth=True).addCallback(self.orders_from_wire).addErrback(self.onError, "getOpenOrders")

    def getOrderBook(self, contract):
        url = self.endpoint + "/rpc/market/get_order_book"
        payload = {'contract': contract}
        return self.post(url, payload=payload).addCallback(self.book_from_wire).addErrback(self.onError, "getOrderBook")

    def getTransactionHistory(self, start_datetime, end_datetime):
        url = self.endpoint + "/rpc/trader/get_transaction_history"
        epoch = datetime.utcfromtimestamp(0)
        start_timestamp = int((start_datetime - epoch).total_seconds() * 1e6)
        end_timestamp = int((end_datetime - epoch).total_seconds() * 1e6)
        payload = {'start_timestamp': start_timestamp,
                   'end_timestamp': end_timestamp}
        return self.post(url, payload=payload, auth=True).addCallback(self.transaction_history_from_wire).addErrback(self.onError, "getTransactionHistory")

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s',
                        level=logging.INFO)

    if len(sys.argv) > 1 and sys.argv[1] == 'debug':
        debug = True
    else:
        debug = False

    log.startLogging(sys.stdout)
    config = ConfigParser()
    config_file = path.abspath(path.join(path.dirname(__file__),
            "./sputnik.ini"))
    config.read(config_file)

    bot_params = { 'username': config.get("client", "username"),
                   'password': config.get("client", "password") }

    connection = { 'ssl': config.getboolean("client", "ssl"),
                   'port': config.getint("client", "port"),
                   'hostname': config.get("client", "hostname"),
                   'ca_certs_dir': config.get("client", "ca_certs_dir") }

    sputnik_wamp = Sputnik(connection, bot_params, debug, bot=BasicBot)
    sputnik_wamp.connect()

    if connection['ssl']:
        rest_endpoint = "https://%s:%d/api" % (connection['hostname'], connection['port'])
    else:
        rest_endpoint = "http://%s:%d/api" % (connection['hostname'], connection['port'])

    def onInit(sputnik):
        # sputnik.getOpenOrders().addCallback(pprint)
        # sputnik.getOrderBook('BTC/MXN').addCallback(pprint)
        sputnik.placeOrder('BTC/MXN', 1, 3403, 'BUY').addCallback(pprint).addErrback(log.err)

    # sputnik_rest = SputnikRest(username=u'marketmaker', api_key=u'M865pzFPoLNdWr7RoXbwupVmbWhQ2/JF4zMh7U4vm94=',
    #                            api_secret= u'nYbXz3pFGGHaRVAsvAamUQKfmeFOETXwbqIj1EJb8hk=', endpoint=rest_endpoint,
    #                            onInit=onInit)


    reactor.run()

