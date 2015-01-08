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

from twisted.python import log
from twisted.internet import reactor, defer
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.endpoints import clientFromString
from autobahn.twisted import wamp, websocket
from autobahn.wamp import types
from autobahn.wamp import auth
import hashlib

import Crypto.Random.random


class TradingBot(wamp.ApplicationSession):
    """
   Authenticated WAMP client using WAMP-Challenge-Response-Authentication ("WAMP-CRA").

   """
    auth = False

    def __init__(self, *args, **kwargs):
        wamp.ApplicationSession.__init__(self, *args, **kwargs)
        self.markets = {}
        self.orders = {}
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

    def onJoin(self, details):
        log.msg("Joined as %s" % details.authrole)
        self.getMarkets()
        self.startAutomation()

        if details.authrole != u'anonymous':
            log.msg("Authenticated")
            self.auth = True
            self.username = details.authrole
            self.subOrders()
            self.subFills()
            self.subTransactions()
            self.getOpenOrders()

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
        wamp.ApplicationSession.subscribe(self, handler, unicode(topic), **kwargs)

    def publish(self, topic, message, **kwargs):
        log.msg("publishing %s to %s" % (message, topic))
        wamp.ApplicationSession.publish(self, unicode(topic), unicode(message), **kwargs)

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
            return float(price) / self.markets[ticker]['denominator']
        else:
            return float(price) / (self.markets[self.markets[ticker]['denominated_contract_ticker']]['denominator'] *
                            self.markets[ticker]['denominator'])

    def quantity_from_wire(self, ticker, quantity):
        if self.markets[ticker]['contract_type'] == "prediction":
            return quantity
        elif self.markets[ticker]['contract_type'] == "cash":
            return float(quantity) / self.markets[ticker]['denominator']
        else:
            return float(quantity) / self.markets[self.markets[ticker]['payout_contract_ticker']]['denominator']

    def quantity_to_wire(self, ticker, quantity):
        if self.markets[ticker]['contract_type'] == "prediction":
            return int(quantity)
        elif self.markets[ticker]['contract_type'] == "cash":
            return int(quantity * self.markets[ticker]['denominator'])
        else:
            quantity = quantity * self.markets[self.markets[ticker]['payout_contract_ticker']]['denominator']
            return int(quantity - quantity % self.markets[ticker]['lot_size'])


    """
    reactive events - on* 
    """



    def onMarkets(self, event):
        pprint(event)
        self.markets = event
        if self.markets is not None:
            for ticker, contract in self.markets.iteritems():
                if contract['contract_type'] != "cash":
                    self.getOrderBook(ticker)
                    self.subBook(ticker)
                    self.subTrades(ticker)
                    self.subSafePrices(ticker)
                    self.subOHLCV(ticker)
        return event

    def onOpenOrders(self, event):
        pprint(event)
        if event is not None:
            for id, order in event.iteritems():
                self.orders[int(id)] = order

    def onOrder(self, topicUri, order):
        """
        overwrite me
        """
        id = order['id']
        if id in self.orders and (order['is_cancelled'] or order['quantity_left'] == 0):
            del self.orders[id]
        else:
            if 'quantity' in order:
                # Try to find it in internal orders, if found, delete it
                for search_id, search_order in self.orders.items():
                    if isinstance(search_id, basestring) and search_id.startswith('internal_'):
                        if (order['quantity'] == search_order['quantity'] and
                            order['side'] == search_order['side'] and
                            order['contract'] == search_order['contract'] and
                            order['price'] == search_order['price']):
                            del self.orders[search_id]

            # Add or update, if not cancelled and quantity_left > 0
            if not order['is_cancelled'] and order['quantity_left'] > 0:
                self.orders[id] = order

        pprint(["Order", topicUri, order])

    def onFill(self, topicUri, event):
        """
        overwrite me
        """
        pprint(["Fill", topicUri, event])

    def onTransaction(self, topicUri, event):
        """
        overwrite me
        """
        pprint(["Transaction", topicUri, event])

    def onChat(self, topicUri, event):
        """
        overwrite me
        """
        self.chats.append(event)
        pprint(["Chat", topicUri, event])

    def onChatHistory(self, event):
        self.chats = event
        pprint(["Chat History", event])

    def onPlaceOrder(self, event):
        """
        overwrite me
        """
        pprint(event)

    def onOHLCV(self, topicUri, event):
        pprint(event)

    def onOHLCVHistory(self, event):
        pprint(event)

    def onError(self, message, call=None):
        pprint(["Error", message.value, call])

    def onRpcFailure(self, event):
        pprint(["RpcFailure", event.value.args])

    def onAudit(self, event):
        pprint(event)

    def onMakeAccount(self, event):
        pprint(event)

    def onSupportNonce(self, event):
        pprint(event)

    def onTransactionHistory(self, event):
        pprint(event)

    """
    Feed handlers
    """

    def onBook(self, topicUri, event):
        """
        overwrite me
        """
        pprint(["Book: ", topicUri, event])
        self.markets[event['contract']]['bids'] = event['bids']
        self.markets[event['contract']]['asks'] = event['asks']

    def onTrade(self, topicUri, event):
        """
        overwrite me
        """
        pprint(["Trade: ", topicUri, event])

    def onSafePrice(self, topicUri, event):
        """
        overwrite me
        """
        pprint(["SafePrice", topicUri, event])


    """
    Public Subscriptions
    """
    def encode_ticker(self, ticker):
        return ticker.replace("/", "_").lower()

    def subOHLCV(self, ticker):
        uri = u"feeds.market.ohlcv.%s" % self.encode_ticker(ticker)
        self.subscribe(self.onOHLCV, uri)
        print "subscribed to: ", uri

    def subBook(self, ticker):
        uri = u"feeds.market.book.%s" % self.encode_ticker(ticker)
        self.subscribe(self.onBook, uri)
        print 'subscribed to: ', uri

    def subTrades(self, ticker):
        uri = u"feeds.market.trades.%s" % self.encode_ticker(ticker)
        self.subscribe(self.onTrade, uri)
        print 'subscribed to: ', uri

    def subSafePrices(self, ticker):
        uri = u"feeds.market.safe_prices.%s" % self.encode_ticker(ticker)
        self.subscribe(self.onSafePrice, uri)
        print 'subscribed to: ', uri

    """
    Private Subscriptions
    """
    def encode_username(self, username):
        return hashlib.sha256(username).hexdigest()

    def subOrders(self):
        uri = u"feeds.users.orders.%s" % self.encode_username(self.username)
        self.subscribe(self.onOrder, uri)
        print 'subscribed to: ', uri

    def subFills(self):
        uri = u"feeds.user.fills.%s" % self.encode_username(self.username)
        self.subscribe(self.onFill, uri)
        print 'subscribed to: ', uri

    def subTransactions(self):
        uri = u"feeds.user.transactions.%s" % self.encode_username(self.username)
        self.subscribe(self.onTransaction, uri)
        print 'subscribed to: ', uri

    """
    Public RPC Calls
    """


    def getTradeHistory(self, ticker):
        d = self.call(u"rpc.market.get_trade_history", ticker)
        d.addCallback(pprint).addErrback(self.onError, "getTradeHistory")


    def getMarkets(self):
        d = self.call(u"rpc.market.get_markets")
        d.addCallback(self.onMarkets).addErrback(self.onError, "getMarkets")

    def getOrderBook(self, ticker):
        d = self.call(u"rpc.market.get_order_book", ticker)
        d.addCallback(lambda x: self.onBook(u"rpc.market.get_order_book", x)).addErrback(self.onError, "getOrderBook")

    def getAudit(self):
        d = self.call(u"rpc.info.get_audit")
        d.addCallback(self.onAudit).addErrback(self.onError, "getAudit")

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

        d = self.call(u"rpc.market.get_ohlcv_history", ticker, period, start_timestamp, end_timestamp)
        d.addCallback(self.onOHLCVHistory).addErrback(self.onError, "getOHLCVHistory")

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
        d.addCallback(self.onMakeAccount).addErrback(self.onError, "makeAccount")

    def getResetToken(self, username):
        d = self.call(u"rpc.registrar.get_reset_token", username)
        d.addCallback(pprint).addErrback(self.onError, "getResetToken")

    def getExchangeInfo(self):
        d = self.call(u"rpc.info.get_exchange_info")
        d.addCallback(pprint).addErrback(self.onError, "getExchangeInfo")

    """
    Private RPC Calls
    """

    def getPositions(self):
        d = self.call(u"rpc.trader.get_positions")
        d.addCallback(pprint).addErrback(self.onError, "getPositions")

    def getCurrentAddress(self):
        d = self.call(u"rpc.trader.get_current_address")
        d.addCallback(pprint).addErrback(self.onError, "getCurrentAddress")

    def getNewAddress(self):
        d = self.call(u"rpc.trader.get_new_address")
        d.addCallback(pprint).addErrback(self.onError, "getNewAddress")

    def getOpenOrders(self):
        # store cache of open orders update asynchronously
        d = self.call(u"rpc.trader.get_open_orders")
        d.addCallback(self.onOpenOrders).addErrback(self.onError, "getOpenOrders")

    def getTransactionHistory(self, start_datetime=datetime.now()-timedelta(days=2), end_datetime=datetime.now()):
        epoch = datetime.utcfromtimestamp(0)
        start_timestamp = int((start_datetime - epoch).total_seconds() * 1e6)
        end_timestamp = int((end_datetime - epoch).total_seconds() * 1e6)

        d = self.call("rpc.trader.get_transaction_history", start_timestamp, end_timestamp)
        d.addCallback(self.onTransactionHistory).addErrback(self.onError, "getTransactionHistory")

    def requestSupportNonce(self, type='Compliance'):
        d = self.call(u"rpc.trader.request_support_nonce", type)
        d.addCallback(self.onSupportNonce).addErrback(self.onError, "requestSupportNonce")

    def placeOrder(self, ticker, quantity, price, side):
        ord= {}
        ord['contract'] = ticker
        ord['quantity'] = quantity
        ord['price'] = price
        ord['side'] = side
        d = self.call(u"rpc.trader.place_order", ord)

        self.last_internal_id += 1
        ord['quantity_left'] = ord['quantity']
        ord['is_cancelled'] = False
        order_id = 'internal_%d' % self.last_internal_id
        self.orders[order_id] = ord

        def onError(error):
            logging.info("removing internal order %s" % order_id)
            try:
                del self.orders[order_id]
            except KeyError as e:
                logging.error("Unable to remove order: %s" % e)

            self.onError(error, "placeOrder")

        d.addCallbacks(self.onPlaceOrder, onError)

    def cancelOrder(self, id):
        """
        cancels an order by its id.
        :param id: order id
        """
        if isinstance(id, basestring) and id.startswith('internal_'):
            print "can't cancel internal order: %s" % id

        print "cancel order: %s" % id
        d = self.call(u"rpc.trader.cancel_order", id)
        d.addCallback(pprint).addErrback(self.onError, "cancelOrder")
        del self.orders[id]

class BasicBot(TradingBot):
    def onMakeAccount(self, event):
        TradingBot.onMakeAccount(self, event)
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
        self.getTransactionHistory()
        self.requestSupportNonce()

        self.placeOrder('BTC/HUF', 100000000, 5000000, 'BUY')

class BotFactory(wamp.ApplicationSessionFactory):
    def __init__(self, **kwargs):
        self.username = kwargs.pop('username')
        self.password = kwargs.pop('password')
        if 'ignore_contracts' in kwargs:
            self.ignore_contracts = kwargs.pop('ignore_contracts')

        if 'rate' in kwargs:
            self.rate = kwargs.pop('rate')

        wamp.ApplicationSessionFactory.__init__(self, **kwargs)


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
            "./client.ini"))
    config.read(config_file)

    username = config.get("client", "username")
    password = config.get("client", "password")

    component_config = types.ComponentConfig(realm = u"sputnik")
    session_factory = BotFactory(config=component_config, username=username, password=password)
    session_factory.session = BasicBot

    # The below should be the same for all clients
    ssl = config.getboolean("client", "ssl")
    port = config.getint("client", "port")
    hostname = config.get("client", "hostname")
    ca_certs_dir = config.get("client", "ca_certs_dir")

    if ssl:
        base_uri = "wss://"
        connection_string = "ssl:host=%s:port=%d:caCertsDir=%s" % (hostname, port, ca_certs_dir)
    else:
        base_uri = "ws://"
        connection_string = "tcp:%s:%d" % (hostname, port)

    base_uri += "%s:%d/ws" % (hostname, port)

    transport_factory = websocket.WampWebSocketClientFactory(session_factory,
                                                             url = base_uri, debug=debug,
                                                             debug_wamp=debug)
    client = clientFromString(reactor, connection_string)
    client.connect(transport_factory)

    reactor.run()

