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
from autobahn.twisted import wamp, websocket
from autobahn.wamp import types
from autobahn.wamp import auth
import hashlib

import Crypto.Random.random
from copy import copy


class SputnikSession(wamp.ApplicationSession):
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

    """
    Utility functions
    """

    def price_to_wire(self, ticker, price):
        if self.markets[ticker]['contract_type'] == "prediction":
            price = price * self.markets[ticker]['denominator']
        else:
            price = price * self.markets[self.markets[ticker]['denominated_contract_ticker']]['denominator'] * \
                    self.markets[ticker]['denominator']

        return int(price - price % self.markets[ticker]['tick_size'])

    def price_from_wire(self, ticker, price):
        if self.markets[ticker]['contract_type'] == "prediction":
            return Decimal(price) / self.markets[ticker]['denominator']
        else:
            return Decimal(price) / (self.markets[self.markets[ticker]['denominated_contract_ticker']]['denominator'] *
                            self.markets[ticker]['denominator'])

    def quantity_from_wire(self, ticker, quantity):
        if self.markets[ticker]['contract_type'] == "prediction":
            return quantity
        elif self.markets[ticker]['contract_type'] == "cash":
            return Decimal(quantity) / self.markets[ticker]['denominator']
        else:
            return Decimal(quantity) / self.markets[self.markets[ticker]['payout_contract_ticker']]['denominator']

    def quantity_to_wire(self, ticker, quantity):
        if self.markets[ticker]['contract_type'] == "prediction":
            return int(quantity)
        elif self.markets[ticker]['contract_type'] == "cash":
            return int(quantity * self.markets[ticker]['denominator'])
        else:
            quantity = quantity * self.markets[self.markets[ticker]['payout_contract_ticker']]['denominator']
            return int(quantity - quantity % self.markets[ticker]['lot_size'])

    def ohlcv_from_wire(self, wire_ohlcv):
        ticker = wire_ohlcv['contract']
        ohlcv = {
            'contract': ticker,
            'open': self.price_from_wire(ticker, wire_ohlcv['open']),
            'high': self.price_from_wire(ticker, wire_ohlcv['high']),
            'low': self.price_from_wire(ticker, wire_ohlcv['low']),
            'close': self.price_from_wire(ticker, wire_ohlcv['close']),
            'volume': self.quantity_from_wire(ticker, wire_ohlcv['volume']),
            'vwap': self.price_from_wire(ticker, wire_ohlcv['vwap']),
            'open_timestamp': wire_ohlcv['open_timestamp'],
            'close_timestamp': wire_ohlcv['close_timestamp'],
            'period': wire_ohlcv['period']
        }
        return ohlcv

    def position_from_wire(self, wire_position):
        ticker = wire_position['contract']
        position = copy(wire_position)
        position['position'] = self.quantity_from_wire(ticker, wire_position['position'])
        if self.markets[ticker]['contract_type'] == "futures":
            position['reference_price'] = self.price_from_wire(ticker, wire_position['reference_price'])
        return position

    def order_to_wire(self, order):
        ticker = order['contract']
        wire_order = copy(order)
        wire_order['price'] = self.price_to_wire(ticker, order['price'])
        wire_order['quantity'] = self.quantity_to_wire(ticker, order['quantity'])
        if 'quantity_left' in order:
            wire_order['quantity_left'] = self.quantity_to_wire(ticker, order['quantity_left'])

        return wire_order

    def order_from_wire(self, wire_order):
        ticker = wire_order['contract']
        order = copy(wire_order)
        order['price'] = self.price_from_wire(ticker, wire_order['price'])
        order['quantity'] = self.quantity_from_wire(ticker, wire_order['quantity'])
        order['quantity_left'] = self.quantity_from_wire(ticker, wire_order['quantity_left'])
        return order

    def book_row_from_wire(self, ticker, wire_book_row):
        book_row = copy(wire_book_row)
        book_row['price'] = self.price_from_wire(ticker, wire_book_row['price'])
        book_row['quantity'] = self.price_from_wire(ticker, wire_book_row['quantity'])
        return book_row

    def trade_from_wire(self, wire_trade):
        ticker = wire_trade['contract']
        trade = copy(wire_trade)
        trade['price'] = self.price_from_wire(ticker, wire_trade['price'])
        trade['quantity'] = self.quantity_from_wire(ticker, wire_trade['quantity'])
        return trade

    def fill_from_wire(self, wire_fill):
        ticker = wire_fill['contract']
        fill = copy(wire_fill)
        fill['fees'] = copy(wire_fill['fees'])
        fill['price'] = self.price_from_wire(ticker, wire_fill['price'])
        fill['quantity'] = self.quantity_from_wire(ticker, wire_fill['quantity'])
        for fee_ticker, fee in wire_fill['fees'].iteritems():
            fill['fees'][fee_ticker] = self.quantity_from_wire(fee_ticker, fee)

        return fill

    def transaction_from_wire(self, wire_transaction):
        transaction = copy(wire_transaction)
        ticker = wire_transaction['contract']
        transaction['quantity'] = self.quantity_from_wire(ticker, wire_transaction['quantity'])
        if 'balance' in wire_transaction:
            transaction['balance'] = self.quantity_from_wire(ticker, wire_transaction['balance'])

        return transaction

    @property
    def orders(self):
        return {id: self.order_from_wire(wire_order) for id, wire_order in self.wire_orders.iteritems()}

    @property
    def positions(self):
        return {ticker: self.position_from_wire(wire_position) for ticker, wire_position in self.wire_positions.iteritems()}

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

    def onNewAPIToken(self, token):
        pprint(["onNewAPIToken", token])
        return token

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

    def subOHLCV(self, ticker):
        uri = u"feeds.market.ohlcv.%s" % self.encode_ticker(ticker)
        def _onOHLCV(uri, wire_ohlcv):
            return self.onOHLCV(uri, self.ohlcv_from_wire(wire_ohlcv))

        self.subscribe(_onOHLCV, uri)
        print "subscribed to: ", uri

    def _onBook(self, uri, wire_book):
        ticker = wire_book['contract']
        self.markets[ticker]['wire_book'] = wire_book

        book = copy(wire_book)
        book['bids'] = [self.book_row_from_wire(ticker, row) for row in wire_book['bids']]
        book['asks'] = [self.book_row_from_wire(ticker, row) for row in wire_book['asks']]

        self.markets[ticker]['book'] = book
        return self.onBook(uri, book)

    def subBook(self, ticker):
        uri = u"feeds.market.book.%s" % self.encode_ticker(ticker)

        self.subscribe(self._onBook, uri)
        print 'subscribed to: ', uri

    def subTrades(self, ticker):
        uri = u"feeds.market.trades.%s" % self.encode_ticker(ticker)
        def _onTrade(uri, wire_trade):
            return self.onTrade(uri, self.trade_from_wire(wire_trade))

        self.subscribe(_onTrade, uri)
        print 'subscribed to: ', uri

    def subSafePrices(self, ticker):
        uri = u"feeds.market.safe_prices.%s" % self.encode_ticker(ticker)
        def _onSafePrice(uri, wire_safe_prices):
            return self.onSafePrice(uri, {ticker: self.price_from_wire(ticker, price)
                                          for ticker, price in wire_safe_prices.iteritems()})

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
            ticker = wire_transaction['contract']

            if wire_transaction['direction'] == 'credit':
                sign = 1
            else:
                sign = -1

            if ticker in self.wire_positions:
                self.wire_positions[ticker]['position'] += sign * transaction['quantity']
            else:
                self.wire_positions[ticker] = { 'position': sign * transaction['quantity'],
                                                'contract': ticker }

            return self.onTransaction(uri, self.transaction_from_wire(wire_transaction))

        self.subscribe(_onTransaction, uri)
        print 'subscribed to: ', uri

    """
    Public RPC Calls
    """

    def getTradeHistory(self, ticker):
        d = self.call(u"rpc.market.get_trade_history", ticker)
        def _onTradeHistory(wire_trade_history):
            return self.onTradeHistory([self.trade_from_wire(wire_trade) for wire_trade in wire_trade_history])

        return d.addCallback(_onTradeHistory).addErrback(self.onError, "getTradeHistory")

    def getMarkets(self):
        d = self.call(u"rpc.market.get_markets")
        def _onMarkets(event):
            self.markets = event
            if self.markets is not None:
                for ticker, contract in self.markets.iteritems():
                    if contract['contract_type'] != "cash":
                        self.getOrderBook(ticker)
                        self.subBook(ticker)
                        self.subTrades(ticker)
                        self.subSafePrices(ticker)
                        self.subOHLCV(ticker)

            return self.onMarkets(event)

        return d.addCallback(_onMarkets).addErrback(self.onError, "getMarkets")

    def getOrderBook(self, ticker):
        d = self.call(u"rpc.market.get_order_book", ticker)
        return d.addCallback(lambda x: self._onBook(u"rpc.market.get_order_book", x)).addErrback(self.onError, "getOrderBook")

    def getAudit(self):
        d = self.call(u"rpc.info.get_audit")
        return d.addCallback(self.onAudit).addErrback(self.onError, "getAudit")

    def getOHLCVHistory(self, ticker, period="day", start_datetime=None, end_datetime=None):
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
            return self.onOHLCVHistory({timestamp: self.ohlcv_from_wire(wire_ohlcv)
                                        for timestamp, wire_ohlcv in wire_ohlcv_history.iteritems()})

        d = self.call(u"rpc.market.get_ohlcv_history", ticker, period, start_timestamp, end_timestamp)
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
    def getNewAPIToken(self):
        d = self.call(u"rpc.token.get_new_api_token")
        return d.addCallback(self.onNewAPIToken).addErrback(self.onError, "getNewAPIToken")

    def getPositions(self):
        d = self.call(u"rpc.trader.get_positions")
        def _onPositions(wire_positions):
            self.wire_positions = wire_positions
            self.onPositions(self.positions)

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

    def getTransactionHistory(self, start_datetime=datetime.now()-timedelta(days=2), end_datetime=datetime.now()):
        epoch = datetime.utcfromtimestamp(0)
        start_timestamp = int((start_datetime - epoch).total_seconds() * 1e6)
        end_timestamp = int((end_datetime - epoch).total_seconds() * 1e6)

        def _onTransactionHistory(wire_transaction_history):
            return self.onTransactionHistory([self.transaction_from_wire(wire_transaction)
                                              for wire_transaction in wire_transaction_history])

        d = self.call("rpc.trader.get_transaction_history", start_timestamp, end_timestamp)
        return d.addCallback(_onTransactionHistory).addErrback(self.onError, "getTransactionHistory")

    def requestSupportNonce(self, type='Compliance'):
        d = self.call(u"rpc.trader.request_support_nonce", type)
        return d.addCallback(self.onSupportNonce).addErrback(self.onError, "requestSupportNonce")

    def placeOrder(self, ticker, quantity, price, side):
        ord = {}
        ord['contract'] = ticker
        ord['quantity'] = self.quantity_to_wire(ticker, quantity)
        ord['price'] = self.price_to_wire(ticker, price)
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
                del self.orders[order_id]
            except KeyError as e:
                logging.error("Unable to remove order: %s" % e)

            self.onError(error, "placeOrder")

        def _onPlaceOrder(new_id):
            if order_id in self.wire_orders:
                del self.wire_orders[order_id]

        return d.addCallbacks(_onPlaceOrder, onError)

    def requestWithdrawal(self, ticker, amount, address):
        amount_wire = self.quantity_to_wire(ticker, amount)
        d = self.call(u"rpc.trader.request_withdrawal", ticker, amount_wire, address)
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
        self.getAudit()

        # Test exchange info
        self.getExchangeInfo()

        # Test some OHLCV history fns
        self.getOHLCVHistory('BTC/HUF', 'day')
        self.getOHLCVHistory('BTC/HUF', 'minute')

        # Now make an account
        self.username = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        self.password = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        self.makeAccount(self.username, self.password, "test@m2.io", "Test User")

    def startAutomationAfterAuth(self):
        # self.getNewAPIToken()
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

    def getPositions(self):
        return defer.succeed(self.session.positions)

    def getCurrentAddress(self, ticker):
        return self.session.getCurrentAddress(ticker)

    def requestWithdrawal(self, ticker, amount, address):
        return self.session.requestWithdrawal(ticker, amount, address)

    def placeOrder(self, ticker, quantity, price, side):
        return self.session.placeOrder(ticker, quantity, price, side)

    def cancelOrder(self, id):
        return self.session.cancelOrder(id)

    def getOpenOrders(self):
        return defer.succeed(self.session.orders)

    def getOrderBook(self, ticker):
        return defer.suceed(self.session.markets[ticker]['book'])

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

    sputnik = Sputnik(connection, bot_params, debug, bot=BasicBot)
    sputnik.connect()

    reactor.run()

