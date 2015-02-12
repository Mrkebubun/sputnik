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

from datetime import datetime
from twisted.internet.defer import inlineCallbacks, returnValue, gatherResults, succeed
from twisted.internet import reactor
from twisted.internet.threads import deferToThread
from twisted.python import log
from copy import deepcopy
import sys
from decimal import Decimal
from scipy.optimize import minimize
from dateutil import relativedelta
import numpy as np
from datetime import timedelta
import util
import pickle
import decimal
from fsm import FSM
from ConfigParser import ConfigParser
from os import path
import logging

def load(klass, file, ignore=[]):
    # Load from pickle file
    try:
        attrs = pickle.load(open(file, "rb"))
        for key, value in attrs.iteritems():
            if key not in ignore:
                setattr(klass, key, value)
    except Exception as e:
        log.err("Unable to load")
        log.err(e)

def save(klass, file):
    dict = klass.todict()
    pickle.dump(dict, open(file, "w"))

def todict(klass, params):
    attrs = {}
    for param in params:
        try:
            attrs[param] = getattr(klass, param)
        except (AttributeError, TypeError) as e:
            log.msg("%s not in %s" % (param, klass))
    return attrs

# Don't do anything if its value is less than this in source currency
EPSILON = 1

# Source: Source exchange or currency. Ie if we are taking liquidity from BTC/USD at Bitstamp
#         Then the source exchange is Bitstamp and the source currency is USD
# Fiat: This is the exchange which allows us to convert from the source fiat currency (say, USD)
#       to the target fiat currency (HUF in the example)
# Target: The target exchange or currency. Ie if we are providing liquidity to BTC/HUF at
#         Demo, then the target currency is HUF and the target exchange is Demo
#

class State():
    def __init__(self, data):
        # ILP
        self.data = data

        # State
        self.timestamp = None

        # Book at fiat exchange
        self.fiat_book = None

        # Book at source exchange
        self.source_book = None

        # Book at target exchange
        self.target_book = None

        # Balances at target exchange
        self.balance_target = {}

        # Balances at source exchange
        self.balance_source = {}

        # Variances - only update infrequently
        self.fiat_variance = None
        self.source_variance = None

        # Currently offered bid at ask at target exchange
        self.offered_bid = None
        self.offered_ask = None

        # Transit states are a list of transfers in progress,
        self.transit_to_source = []
        self.transit_to_target = []

        # Transit from are because some API don't support
        # withdrawal, in which case we need to record that we've asked a human
        # to make a transfer from one exchange to another

        self.transit_from_source = []
        self.transit_from_target = []

        # Transaction history
        self.source_transactions = []
        self.target_transactions = []

        self.source_orders = {}
        self.target_orders = {}

        self.trader = None

        load(self, 'state.pickle', ignore=['source_best_bid', 'source_best_ask', 'fiat_best_bid', 'fiat_best_ask'])
        self.save()

    @inlineCallbacks
    def update(self):
        last_update = self.timestamp
        self.timestamp = datetime.utcnow()
        fb_d = self.data.get_fiat_book().addErrback(log.err)
        sb_d = self.data.get_source_book().addErrback(log.err)
        tb_d = self.data.get_target_book().addErrback(log.err)
        bs_d = self.data.get_source_positions().addErrback(log.err)
        bt_d = self.data.get_target_positions().addErrback(log.err)
        if last_update is None:
            st_d = succeed([])
            tt_d = succeed([])
        else:
            st_d = self.data.get_source_transactions(last_update, self.timestamp).addErrback(log.err)
            tt_d = self.data.get_target_transactions(last_update, self.timestamp).addErrback(log.err)

        so_d = self.trader.get_source_orders()
        to_d = self.trader.get_target_orders()

        # Gather all the results and get all the dataz
        [self.fiat_book, self.source_book, self.target_book, self.balance_source, self.balance_target,
         source_transactions, target_transactions, self.source_orders, self.target_orders] = \
            yield gatherResults([fb_d, sb_d, tb_d, bs_d, bt_d, st_d, tt_d, so_d, to_d])

        self.source_transactions += source_transactions
        self.target_transactions += target_transactions

        # Find offered bid and ask in target_orders
        if self.offered_bid is None:
            bids = [order['price'] for order in self.target_orders.values() if order['side'] == 'BUY']
            if bids:
                self.offered_bid = max(bids)

        if self.offered_ask is None:
            asks = [order['price'] for order in self.target_orders.values() if order['side'] == 'SELL']
            if asks:
                self.offered_ask = min(asks)

        if self.fiat_variance is None or (self.timestamp - last_update) > timedelta(days=7):
            self.fiat_variance = yield self.data.get_fiat_variance().addErrback(log.err)

        if self.source_variance is None or (self.timestamp - last_update) > timedelta(days=7):
            self.source_variance = yield self.data.get_source_variance().addErrback(log.err)

        # Update transits - remove ones that have arrived
        # How do we do this?
        source_deposits = [transaction for transaction in source_transactions if transaction['type'] == "Deposit"]
        target_deposits = [transaction for transaction in target_transactions if transaction['type'] == "Deposit"]
        source_withdrawals = [transaction for transaction in source_transactions if transaction['type'] == "Withdrawal"]
        target_withdrawals = [transaction for transaction in target_transactions if transaction['type'] == "Withdrawal"]

        def clear_transits(transits, tx_list, field='to'):
            def near(value_1, value_2):
                if abs(value_1-value_2)/value_1 < 0.01:
                    return True
                else:
                    return False
            kept_transits = []

            for ix in range(len(transits)):
                found = False
                for tx in tx_list:
                    contract = tx['contract']
                    quantity = tx['quantity']
                    if transits[ix]['%s_ticker' % field] == contract and near(transits[ix]['%s_quantity' % field],
                                                                              quantity):
                        if field == "from":
                            destination = transits[ix].get("destination")
                            if destination == "source":
                                self.transit_to_source.append(transits[ix])
                            if destination == "target":
                                self.transit_to_target.append(transits[ix])
                        found = True
                        break

                if not found:
                    kept_transits.append(transits[ix])



            return kept_transits

        self.transit_to_source = clear_transits(self.transit_to_source, source_deposits, field='to')
        self.transit_to_target = clear_transits(self.transit_to_target, target_deposits, field='to')
        self.transit_from_source = clear_transits(self.transit_from_source, source_withdrawals, field='from')
        self.transit_from_target = clear_transits(self.transit_from_target, target_withdrawals, field='from')

        self.save()
        returnValue(None)

    def save(self):
        save(self, 'state.pickle')

    def todict(self):
        return todict(self, ['fiat_book', 'source_book', 'target_book', 'source_orders',
                                  'target_orders', 'balance_source', 'balance_target', 'timestamp',
                                  'transit_to_source', 'transit_to_target', 'transit_from_source',
                                  'transit_from_target', 'source_variance', 'fiat_variance',
                                  'source_best_bid', 'source_best_ask', 'fiat_best_bid', 'fiat_best_ask',
                                  'source_transactions', 'target_transactions'])

    def source_price_for_size(self, quantity):
        if quantity > 0:
            half = 'asks'
            price = float('inf')
        else:
            half = 'bids'
            price = 0

        quantity_left = abs(quantity)
        total_spent = 0
        total_traded = 0

        # Find the liquidity in the book
        for row in self.source_book[half]:
            price = float(row['price'])
            quantity = min(quantity_left, float(row['quantity']))
            total_spent += price * quantity
            total_traded += quantity
            quantity_left -= quantity
            if quantity_left <= 0:
                break

        return price, total_spent, total_traded

    def source_trade(self, quantity):
        """

        :param quantity:
        :return:

        Get the impact to balances if we place a limit order for 'quantity' at the source exchange
        if quantity < 0, we are selling. Quantity is in BTC
        """
        if self.convert_to_source(self.data.btc_ticker, quantity) > EPSILON:
            sign = 1
        elif self.convert_to_source(self.data.btc_ticker, quantity) < -EPSILON:
            sign = -1
        else:
            return {self.data.source_ticker: 0,
                    self.data.btc_ticker: 0}

        price, total_spent, total_traded = self.source_price_for_size(quantity)
        fee = total_spent * self.data.source_fee[1] + self.data.source_fee[0]

        return {self.data.source_ticker: -(sign * total_spent + fee),
                self.data.btc_ticker: sign * total_traded}

    def target_trade(self, quantity, price, side):
        """

        :param quantity:
        :param price:
        :param side:
        :return:

        What are the results if we place a limit order on the target exchange
        and it is executed? Quantity must be greater than 0
        """
        if self.convert_to_source(self.data.btc_ticker, quantity) > EPSILON:
            total_spent = quantity * price
            total_bought = quantity
            fee = abs(total_spent * self.data.target_fee[1]) + self.data.target_fee[0]

            if side == 'BUY':
                sign = 1
            else:
                sign = -1

            return {self.data.target_ticker: - sign * total_spent + fee,
                    self.data.btc_ticker: sign * total_bought}
        else:
            return {self.data.target_ticker: 0,
                    self.data.btc_ticker: 0}

    def source_target_fiat_transfer(self, amount):
        """

        :param amount:
        :return:
        What is the impact on balances if we transfer fiat from the source exchange
        to the target exchange. Amount is always in source currency, but if it is negative,
        we are doing a transfer from the target exchange to the source exchange. The fees are charged
        to the exchange that is receiving the money

        """
        if self.convert_to_source(self.data.source_ticker, abs(amount)) > EPSILON:
            fee_in_source = abs(amount) * self.data.fiat_exchange_cost[1] + self.data.fiat_exchange_cost[0]
            if amount > 0:
                return { self.data.source_ticker: -amount,
                         self.data.target_ticker: self.convert_to_target(self.data.source_ticker, amount - fee_in_source)}
            else:
                return { self.data.source_ticker: abs(amount) - fee_in_source,
                         self.data.target_ticker: self.convert_to_target(self.data.source_ticker, amount)}
        else:
            return {self.data.target_ticker: 0,
                    self.data.source_ticker: 0}

    def btc_transfer(self, amount):
        """

        :param amount:
        :return:
        Transfer btc from source to target exchange. If amount is negative,
        transfer in the other direction. We assume exchange charges no BTC transfer
        fees but there is a BTC transfer fee charged by the network. We charge it
        to the receiving side
        """
        if self.convert_to_source(self.data.btc_ticker, amount) > EPSILON:
            return {'source_btc': -amount,
                    'target_btc': amount - self.data.btc_fee}
        elif self.convert_to_source(self.data.btc_ticker, amount) < -EPSILON:
            return {'source_btc': abs(amount) - self.data.btc_fee,
                    'target_btc': amount}
        else:
            return {'source_btc': 0,
                    'target_btc': 0}

    def transfer_source_out(self, amount):
        """

        :param amount:
        :return:
        Transfer source currency out of the source exchange to our own bank. We can't transfer in
        """
        fee = abs(amount) * self.data.fiat_exchange_cost[1] + self.data.fiat_exchange_cost[0]
        if self.convert_to_source(self.data.source_ticker, amount) > EPSILON:
            return {self.data.source_ticker: -(amount + fee)}
        else:
            return {self.data.source_ticker: 0}

    def get_best_bid(self, book):
        if 'bids' in book and len(book['bids']) > 0:
            return float(book['bids'][0]['price'])
        else:
            # There is no bid, worth 0!
            return 0

    def get_best_ask(self, book):
        if 'asks' in book and len(book['asks']) > 0:
            fl = float(book['asks'][0]['price'])
            if fl != float('inf'):
                return fl

        # There is no ask, worth max!
        return sys.float_info.max

    @property
    def source_best_ask(self):
        return self.get_best_ask(self.source_book)

    @property
    def source_best_bid(self):
        return self.get_best_bid(self.source_book)

    @property
    def fiat_best_ask(self):
        return self.get_best_ask(self.fiat_book)

    @property
    def fiat_best_bid(self):
        return self.get_best_bid(self.fiat_book)


    @property
    def source_exchange_rate(self):
        """
        Get the rate to convert BTC to the source currency. Use the bid

        :return:
        """
        return self.get_best_bid(self.source_book)

    @property
    def fiat_exchange_rate(self):
        """
        Get the rate to convert target currency to source currency

        :return:
        """
        return self.get_best_bid(self.fiat_book)

    @property
    def total_balance_target(self):
        """


        :return:
        Give us the total balances at the target taking into account cash that is in transit
        both in and out
        """
        total_balance = deepcopy(self.balance_target)

        for transit in self.transit_to_target:
            total_balance[transit['to_ticker']]['position'] += transit['to_quantity']

        for transit in self.transit_from_source:
            if transit['destination'] == 'target':
                total_balance[transit['to_ticker']]['position'] += transit['to_quantity']

        for transit in self.transit_from_target:
            total_balance[transit['from_ticker']]['position'] -= transit['from_quantity']

        return total_balance

    @property
    def total_balance_source(self):
        """


        :return:
        Give us the total balances at the source taking into account cash that is in transit
        both in and out
        """
        total_balance = deepcopy(self.balance_source)

        for transit in self.transit_to_source:
            total_balance[transit['to_ticker']]['position'] += transit['to_quantity']

        for transit in self.transit_from_target:
            if transit['destination'] == 'source':
                total_balance[transit['to_ticker']]['position'] += transit['to_quantity']

        for transit in self.transit_from_source:
            total_balance[transit['from_ticker']]['position'] -= transit['from_quantity']

        return total_balance

    def constraint_fn(self, params={}, quote_size=0):
        """
        Given the state of the exchanges, tell us what we can't do. This current
        version doesn't take into account fees. Actual version will actually call the "impact"
        functions and make sure that they don't result in negative balances

        :param params:
        :return:
        """
        consequences = self.get_consequences(params, quote_size=quote_size)

        offered_bid = params.get('offered_bid', 0)
        offered_ask = params.get('offered_ask', 0)
        transfer_source_out = params.get('transfer_source_out', 0)

        if offered_ask < 0 or offered_bid < 0:
            return False
        if offered_ask <= offered_bid:
            return False

        if transfer_source_out < 0:
            return False

        # Make sure we don't end up with a negative balance
        def sum_negatives(numbers):
            return abs(sum([min(x, 0) for x in numbers]))

        if (sum_negatives([consequences['bid'][self.data.target_ticker],
                          consequences['ask'][self.data.target_ticker],
                          consequences['fiat_transfer'][self.data.target_ticker]]) >
            self.balance_target[self.data.target_ticker]['position']):
            return False

        if (sum_negatives([consequences['bid'][self.data.btc_ticker],
                          consequences['ask'][self.data.btc_ticker],
                          consequences['btc_transfer']['target_btc']]) >
            self.balance_target[self.data.btc_ticker]['position']):
            return False

        if (sum_negatives([consequences['trade_source'][self.data.source_ticker],
                           consequences['fiat_transfer'][self.data.source_ticker],
                           consequences['transfer_out'][self.data.source_ticker]]) >
            self.balance_source[self.data.source_ticker]['position']):
            return False

        if (sum_negatives([consequences['trade_source'][self.data.btc_ticker],
                           consequences['btc_transfer']['source_btc']]) >
            self.balance_source[self.data.btc_ticker]['position']):
            return False

        return True

    def convert_to_source(self, ticker, quantity):
        if ticker == self.data.source_ticker:
            return quantity
        if ticker == self.data.btc_ticker:
            return quantity * self.source_best_bid
        if ticker == self.data.target_ticker:
            return quantity * self.fiat_best_bid

    def convert_to_target(self, ticker, quantity):
        if ticker == self.data.target_ticker:
            return quantity
        if ticker == self.data.btc_ticker:
            raise NotImplementedError
        if ticker == self.data.source_ticker:
            return quantity / self.fiat_best_ask

    def convert_to_btc(self, ticker, quantity):
        if ticker == self.data.btc_ticker:
            return quantity
        if ticker == self.data.source_ticker:
            return quantity / self.source_best_ask
        if ticker == self.data.target_ticker:
            raise NotImplementedError

    def get_consequences(self, params, quote_size):
        offered_bid = params.get('offered_bid', 0)
        offered_ask = params.get('offered_ask', 0)
        btc_source_target = params.get('btc_source_target', 0)
        fiat_source_target = params.get('fiat_source_target', 0)
        trade_source_qty = params.get('trade_source_qty', 0)
        transfer_source_out = params.get('transfer_source_out', 0)

        # Get effect of various activities
        bid_consequence = self.target_trade(quote_size, offered_bid, 'BUY')
        ask_consequence = self.target_trade(quote_size, offered_ask, 'ASK')
        btc_transfer_consequence = self.btc_transfer(btc_source_target)
        fiat_transfer_consequence = self.source_target_fiat_transfer(fiat_source_target)
        trade_source_consequence = self.source_trade(trade_source_qty)
        transfer_out_consequence = self.transfer_source_out(transfer_source_out)
        return {'bid': bid_consequence,
                'ask': ask_consequence,
                'btc_transfer': btc_transfer_consequence,
                'fiat_transfer': fiat_transfer_consequence,
                'trade_source': trade_source_consequence,
                'transfer_out': transfer_out_consequence}

class Valuation():
    def __init__(self,
                 state,
                 data,
                 target_balance_source,
                 target_balance_target,
                 deviation_penalty, # dimensionless factor on USD
                 risk_aversion, # ( 1 / USD )
                 ):

        self.state = state
        self.data = data
        self.trader = None

        # Tunable parameters
        self.target_balance_source = target_balance_source
        self.target_balance_target = target_balance_target
        self.deviation_penalty = deviation_penalty
        self.risk_aversion = risk_aversion

        self.optimized_params = {}
        self.optimized = {}
        self.base_params = {}
        self.base = {}

        load(self, 'valuation.pickle')
        self.save()

    def save(self):
        save(self, 'valuation.pickle')

    def todict(self):
        return todict(self, ['target_balance_source',
                                      'target_balance_target',
                                      'deviation_penalty',
                                      'risk_aversion',
                                      'base_params', 'base',
                                      'optimized_params', 'optimized'])

    # [ offered_bid, offered_ask, BTC source<->target (+ means move to source), Fiat source<->target,
    #   trade_source_qty, transfer_source_out ]
    def valuation(self, params={}):
        # Get current balances

        source_source_balance = float(self.state.total_balance_source[self.data.source_ticker]['position'])
        source_btc_balance = float(self.state.total_balance_source[self.data.btc_ticker]['position'])
        target_target_balance = float(self.state.total_balance_target[self.data.target_ticker]['position'])
        target_btc_balance = float(self.state.total_balance_target[self.data.btc_ticker]['position'])

        consequences = self.state.get_consequences(params, quote_size=float(self.trader.quote_size))

        # It has an impact on our balances
        target_target_balance += consequences['bid'][self.data.target_ticker]
        target_btc_balance += consequences['bid'][self.data.btc_ticker]

        target_target_balance += consequences['ask'][self.data.target_ticker]
        target_btc_balance += consequences['ask'][self.data.btc_ticker]

        target_btc_balance += consequences['btc_transfer']['target_btc']
        source_btc_balance += consequences['btc_transfer']['source_btc']

        target_target_balance += consequences['fiat_transfer'][self.data.target_ticker]
        source_source_balance += consequences['fiat_transfer'][self.data.source_ticker]

        source_source_balance += consequences['trade_source'][self.data.source_ticker]
        source_btc_balance += consequences['trade_source'][self.data.btc_ticker]

        source_source_balance += consequences['transfer_out'][self.data.source_ticker]

        # Deviation Penalty
        source_source_target = self.target_balance_source[self.data.source_ticker]
        source_btc_target = self.target_balance_source[self.data.btc_ticker]
        target_target_target = self.target_balance_target[self.data.target_ticker]
        target_btc_target = self.target_balance_target[self.data.btc_ticker]

        def get_penalty(balance, target):
            if balance < 0:
                return float('inf')
            critical_min = 0.25 * target
            min_bal = 0.75 * target
            max_bal = 1.25 * target
            critical_max = 5 * target
            penalty = max(0, critical_min - balance) * 10 + max(0, min_bal - balance) * 3 + max(0, balance - max_bal) * 1 + max(0, balance - critical_max) * 3
            return penalty

        deviation_penalty_in_source = \
            self.state.convert_to_source(self.data.source_ticker, get_penalty(source_source_balance, source_source_target)) + \
            self.state.convert_to_source(self.data.btc_ticker, get_penalty(source_btc_balance, source_btc_target)) + \
            self.state.convert_to_source(self.data.target_ticker, get_penalty(target_target_balance, target_target_target)) + \
            self.state.convert_to_source(self.data.btc_ticker, get_penalty(target_btc_balance, target_btc_target))

        deviation_penalty_in_source *= self.deviation_penalty

        # Market Risk
        market_risk_in_source = self.risk_aversion * \
                      (self.state.source_variance * pow(source_btc_balance + target_btc_balance, 2) +
                       self.state.fiat_variance * pow(target_target_balance, 2))

        # Total value
        cash_value_in_source = self.state.convert_to_source(self.data.source_ticker, source_source_balance) + \
                      self.state.convert_to_source(self.data.btc_ticker, source_btc_balance + target_btc_balance) + \
                      self.state.convert_to_source(self.data.target_ticker, target_target_balance)

        value = cash_value_in_source - market_risk_in_source - deviation_penalty_in_source
        ret = {'value': value,
                    'cash_value_in_source': cash_value_in_source,
                    'market_risk_in_source': market_risk_in_source,
                    'deviation_penalty': deviation_penalty_in_source,
                    'target_target_balance': target_target_balance,
                    'target_btc_balance': target_btc_balance,
                    'source_source_balance': source_source_balance,
                    'source_btc_balance': source_btc_balance,
                }
        return ret

    @inlineCallbacks
    def optimize(self):
            yield self.state.update()
            self.base_params = {}

            base_bid = self.state.source_best_bid / self.state.fiat_best_ask
            base_ask = self.state.source_best_ask / self.state.fiat_best_bid
            if base_ask == float('inf'):
                base_ask = sys.float_info.max

            if self.state.offered_bid is not None:
                self.base_params['offered_bid'] = float(self.state.offered_bid)
            else:
                self.base_params['offered_bid'] = base_bid

            if self.state.offered_ask is not None:
                self.base_params['offered_ask'] = float(self.state.offered_ask)
            else:
                self.base_params['offered_ask'] = base_ask

            self.base = self.valuation(params=self.base_params)
            def negative_valuation(x):
                params = {'offered_bid': x[0],
                          'offered_ask': x[1],
                          'btc_source_target': x[2],
                          'fiat_source_target': x[3],
                          'trade_source_qty': x[4],
                          'transfer_source_out': x[5]}
                ret = self.valuation(params=params)
                return -ret['value']


            def constraint(x):
                params = {'offered_bid': x[0],
                          'offered_ask': x[1],
                          'btc_source_target': x[2],
                          'fiat_source_target': x[3],
                          'trade_source_qty': x[4],
                          'transfer_source_out': x[5]}
                if self.state.constraint_fn(params, quote_size=float(self.trader.quote_size)):
                    return 1
                else:
                    return -1

            x0 = np.array([base_bid, base_ask, 0, 0, 0, 0])
            log.msg("Optimizing...")
            res = yield deferToThread(minimize, negative_valuation, x0, method='COBYLA',
                           constraints={'type': 'ineq',
                                         'fun': constraint},
                           tol=1e-2,
                           options={'disp': True,
                                    'maxiter': 100,
                                    })
            x = res.x
            self.optimized_params =  {'offered_bid': x[0],
                          'offered_ask': x[1],
                          'btc_source_target': x[2],
                          'fiat_source_target': x[3],
                          'trade_source_qty': x[4],
                          'transfer_source_out': x[5]}
            self.optimized = self.valuation(params=self.optimized_params)



class Data():
    def __init__(self,
                 source_exchange,
                 target_exchange,
                 fiat_exchange,
                 source_ticker,
                 target_ticker,
                 btc_ticker,
                 fiat_exchange_cost, # (fixed_fee, prop_fee) (assume fees are charged in 'source' currency)
                 fiat_exchange_delay, # (source->target, target->source) (seconds)
                 source_fee, # (fixed_fee, prop_fee)
                 target_fee, # (fixed_fee, prop_fee)
                 btc_fee, # fixed_fee
                 btc_delay, # (seconds)
                 variance_period, # "day", "hour", "minute"
                 variance_window # How many periods to use to calculate variance
    ):

        # Configurations
        self.source_exchange = source_exchange
        self.target_exchange = target_exchange
        self.fiat_exchange = fiat_exchange
        self.source_ticker = source_ticker
        self.target_ticker = target_ticker
        self.btc_ticker = btc_ticker
        self.variance_period = variance_period
        self.variance_window = variance_window

        # Outside parameters
        self.fiat_exchange_cost = fiat_exchange_cost
        self.fiat_exchange_delay = fiat_exchange_delay
        self.source_fee = source_fee
        self.target_fee = target_fee
        self.btc_fee = btc_fee
        self.btc_delay = btc_delay

        load(self, 'data.pickle')
        self.save()

    def save(self):
        save(self, 'data.pickle')

    def todict(self):
        return todict(self, ['source_ticker', 'target_ticker', 'btc_ticker', 'variance_period',
                                 'variance_window', 'fiat_exchange_cost', 'fiat_exchange_delay',
                                 'source_fee', 'target_fee', 'btc_fee', 'btc_delay'])

    @property
    def fiat_exchange_ticker(self):
        return '%s/%s' % (self.target_ticker, self.source_ticker)

    @property
    def source_exchange_ticker(self):
        return '%s/%s' % (self.btc_ticker, self.source_ticker)

    @property
    def target_exchange_ticker(self):
        return '%s/%s' % (self.btc_ticker, self.target_ticker)

    def get_fiat_book(self):
        return self.fiat_exchange.getOrderBook(self.fiat_exchange_ticker)

    def get_source_book(self):
        return self.source_exchange.getOrderBook(self.source_exchange_ticker)

    def get_target_book(self):
        return self.target_exchange.getOrderBook(self.target_exchange_ticker)

    def get_target_positions(self):
        return self.target_exchange.getPositions()

    def get_source_positions(self):
        return self.source_exchange.getPositions()

    def get_source_transactions(self, start_timestamp, end_timestamp):
        return self.source_exchange.getTransactionHistory(start_timestamp, end_timestamp)

    def get_target_transactions(self, start_timestamp, end_timestamp):
        return self.target_exchange.getTransactionHistory(start_timestamp, end_timestamp)

    @inlineCallbacks
    def get_variance(self, ticker, exchange):
        if self.variance_window == "month":
            now = datetime.utcnow()
            start_datetime = now - relativedelta.relativedelta(months=1)
            end_datetime = now - relativedelta.relativedelta(days=1)
        else:
            raise NotImplementedError

        if self.variance_period == "day":
            period = "day"
        else:
            raise NotImplementedError

        if ticker == "BTC/USD":
            returnValue(2000.0)
            trade_history = []
            start = int(util.dt_to_timestamp(start_datetime)/1e6)
            end = int(util.dt_to_timestamp(end_datetime)/1e6)

            log.msg("Loading BTC/USD history")
            import wget, gzip
            gzip_file = wget.download("http://api.bitcoincharts.com/v1/csv/bitstampUSD.csv.gz", out="/tmp", bar=None)

            with gzip.GzipFile(gzip_file, "r") as f:
                for row in f:
                    timestamp_str, price_str, quantity_str = row.split(',')
                    if int(timestamp_str) > end:
                        break
                    if int(timestamp_str) < start:
                        continue

                    trade_history.append({'contract': 'BTC/USD',
                                          'price': float(price_str),
                                          'timestamp': int(int(timestamp_str) * 1e6),
                                          'quantity': float(quantity_str)
                             })
            ohlcv_history = util.trade_history_to_ohlcv(trade_history, period=period)
        else:
            ohlcv_history = yield exchange.getOHLCVHistory(ticker, period=period, start_datetime=start_datetime,
                                                          end_datetime=end_datetime)

        closes = [float(ohlcv['close']) for timestamp, ohlcv in ohlcv_history.iteritems()]
        variance = np.var(closes)
        returnValue(variance)

    def get_source_variance(self):
        return self.get_variance(self.source_exchange_ticker, self.source_exchange)

    def get_fiat_variance(self):
        return self.get_variance(self.fiat_exchange_ticker, self.fiat_exchange)

class Trader():
    def __init__(self, source_exchange, target_exchange, quote_size, out_address,
                 edge_to_enter, edge_to_leave,
                 state, data, valuation, period):
        self.source_exchange = source_exchange
        self.target_exchange = target_exchange
        self.quote_size = quote_size
        self.out_address = out_address # Where do we transfer source currency to get out of the system
        self.edge_to_enter = edge_to_enter
        self.edge_to_leave = edge_to_leave

        self.state = state
        self.data = data
        self.valuation = valuation
        self.period = period

        self.valuation.trader = self
        self.state.trader = self
        self.looping_call = task.LoopingCall(self.loop)

        fsm = FSM("DISCONNECTED", None)
        self.fsm = fsm
        #fsm.set_default_transition(self.error, "ERROR")
        fsm.add_transition("connected", "DISCONNECTED", self.initialize, "INITIALIZING")
        fsm.add_transition("updated", "INITIALIZING", None, "READY")
        fsm.add_transition("start", "READY", None, "TRADING")
        fsm.add_transition("stop", "TRADING", self.stop, "READY")
        fsm.add_transition("stop", "READY", None, "READY")
        fsm.add_transition("disconnected", "DISCONNECTED", None, "DISCONNECTED")
        fsm.add_transition("disconnected", "READY", None, "DISCONNECTED")
        fsm.add_transition("disconnected", "TRADING", None, "DISCONNECTED")
        fsm.add_transition("disconnected", "STOPPING", None, "DISCONNECTED")

        load(self, 'trader.pickle', ignore=['fsm'])
        self.save()

    def save(self):
        save(self, 'trader.pickle')

    def todict(self):
        dict = todict(self, ['quote_size', 'out_address', 'edge_to_enter', 'edge_to_leave', 'period', 'rounded', 'rounded_params'])
        dict['fsm'] = { 'current_state': self.fsm.current_state }
        return dict

    @inlineCallbacks
    def start(self):
        joined_list = []
        def onConnect(exchange):
            joined_list.append(exchange)
            if "source" in joined_list and "target" in joined_list:
                self.fsm.process("connected")

        def onDisconnect(exchange, name):
            # Mark as not connected
            if name in joined_list:
                del joined_list[joined_list.index(name)]

            self.fsm.process("disconnected")
            if self.looping_call.running:
                self.looping_call.stop()

            # Try to reconnect in 5 seconds
            reactor.callLater(5, exchange.connect)

        self.source_exchange.on("connect", lambda x: onConnect("source"))
        self.target_exchange.on("connect", lambda x: onConnect("target"))

        self.source_exchange.on("disconnect", lambda x: onDisconnect(x, "source"))
        self.target_exchange.on("disconnect", lambda x: onDisconnect(x, "target"))

        se = self.source_exchange.connect()
        te = self.target_exchange.connect()
        yield gatherResults([se, te])

    @inlineCallbacks
    def initialize(self, fsm):
        yield self.cancel_all_orders()
        yield self.state.update()
        self.fsm.process("updated")
        self.looping_call.start(self.period)

    def stop(self, fsm):
        self.cancel_all_orders()

    @inlineCallbacks
    def cancel_all_orders(self):
        for id in self.state.source_orders.keys():
            yield self.source_exchange.cancelOrder(id)

        for id in self.state.target_orders.keys():
            yield self.target_exchange.cancelOrder(id)

    def get_source_orders(self):
        return self.source_exchange.getOpenOrders()

    def get_target_orders(self):
        return self.target_exchange.getOpenOrders()

    def round_btc(self, quantity):
        # Round to 2 decimal places
        return Decimal(quantity).quantize(Decimal('1E-2'), rounding=decimal.ROUND_DOWN)

    def round_source(self, quantity):
        # Round to '100'
        return Decimal(quantity).quantize(Decimal('1E2'), rounding=decimal.ROUND_DOWN)

    @inlineCallbacks
    def loop(self):
        try:
            yield self.valuation.optimize()
        except Exception as e:
            log.err("Unable to optimize")
            log.err(e)
            return

        base_value = self.valuation.base['value']
        base_params = self.valuation.base_params

        optimized_params = self.valuation.optimized_params
       #
       # 1) recalculate the exact quotes you would like to have
       # 2) round this quote to the precision allowed by the engine ( round up for ask, down for bid)
       # 3) if you're not currently quoting the full amount that you ought to be quoting, send the different at the optimal quote level
       # 4) if your new quote improves on the price of the old quote, send it and cancel the old quote
       # 5) if your new quote is more conservative than the old quote, only replace the old quote if its edge is less than the edge_to_leave

        # Round optimized results
        self.rounded_params = {'offered_bid': self.target_exchange.round_bid(self.data.target_exchange_ticker, optimized_params['offered_bid']),
                          'offered_ask': self.target_exchange.round_ask(self.data.target_exchange_ticker, optimized_params['offered_ask']),
                          'btc_source_target': self.round_btc(optimized_params['btc_source_target']),
                          'fiat_source_target': self.round_source(optimized_params['fiat_source_target']),
                          'trade_source_qty': self.round_btc(optimized_params['trade_source_qty']),
                          'transfer_source_out': self.round_source(optimized_params['transfer_source_out'])}
        rp_as_floats = {key: float(value) for key, value in self.rounded_params.iteritems()}
        self.rounded = self.valuation.valuation(rp_as_floats)


        if self.fsm.current_state == "TRADING":
            try:
                yield self.update_offers(optimized_params['offered_bid'], optimized_params['offered_ask'])
            except Exception as e:
                log.err("Can't update offers")
                log.err(e)

            try:
                yield self.source_trade(self.rounded_params['trade_source_qty'])
            except Exception as e:
                log.err("Can't execute a trade on source exchange")
                log.err(e)

            try:
                yield self.btc_transfer(self.rounded_params['btc_source_target'])
            except Exception as e:
                log.err("Can't transfer BTC")
                log.err(e)

            try:
                yield self.source_target_fiat_transfer(self.rounded_params['fiat_source_target'])
            except Exception as e:
                log.err("Can't transfer fiat")
                log.err(e)

            try:
                yield self.transfer_source_out(self.rounded_params['transfer_source_out'])
            except Exception as e:
                log.err("Can't transfer fiat out of source")
                log.err(e)

    @inlineCallbacks
    def source_trade(self, quantity):
        # Check for orders outstanding and cancel them
        my_ids = [order['id'] for order in self.state.source_orders.values()
                  if order['contract'] == self.data.source_exchange_ticker]
        for id in my_ids:
            yield self.source_exchange.cancelOrder(id)

        if self.state.convert_to_source(self.data.btc_ticker, float(quantity)) > EPSILON:
            side = 'BUY'
        elif self.state.convert_to_source(self.data.btc_ticker, float(quantity)) < -EPSILON:
            side = 'SELL'
        else:
            return

        # Place a new order
        price, total_spent, total_traded = self.state.source_price_for_size(float(quantity))
        try:
            yield self.source_exchange.placeOrder(self.data.source_exchange_ticker, total_traded, price, side)
        except Exception as e:
            log.err("Unable to place order on source exchange: %s %s %s %s" % (
                self.data.source_exchange_ticker,
                total_traded,
                price, side
                                                                              ))
            log.err(e)

    @inlineCallbacks
    def btc_transfer(self, quantity):
        """
        :param ticker:
        :param quantity:
        :return:

        Transfer quantity of BTC from source to target
        If quantity is negative we transfer from target to source
        """
        if abs(self.state.convert_to_source(self.data.btc_ticker, float(quantity))) < EPSILON:
            return

        if quantity > 0:
            from_exchange = self.source_exchange
            to_exchange = self.target_exchange
            from_state = self.state.transit_from_source
            to_state = self.state.transit_to_target
            destination = 'target'
        else:
            from_exchange = self.target_exchange
            to_exchange = self.source_exchange
            from_state = self.state.transit_from_target
            to_state = self.state.transit_to_source
            destination = 'source'

        # Get deposit address
        deposit_address = None
        try:
            deposit_address = yield to_exchange.getNewAddress(self.data.btc_ticker)
            yield from_exchange.requestWithdrawal(self.data.btc_ticker, abs(quantity), deposit_address)

            to_state.append({'to_ticker': self.data.btc_ticker,
                              'from_ticker': self.data.btc_ticker,
                              'from_quantity': abs(quantity),
                              'to_quantity': abs(quantity),
                              'address': deposit_address})

        except NotImplementedError:
            from_state.append({'to_ticker': self.data.btc_ticker,
                               'from_ticker': self.data.btc_ticker,
                                'from_quantity': abs(quantity),
                                'to_quantity': abs(quantity),
                                'address': deposit_address,
                                'destination': destination})

    @inlineCallbacks
    def source_target_fiat_transfer(self, quantity):
        """
        :param ticker:
        :param quantity:
        :return:

        Transfer quantity of fiat from source to target
        If quantity is negative we transfer from target to source
        quantity is in source currency
        """
        if abs(self.state.convert_to_source(self.data.source_ticker, float(quantity))) < EPSILON:
            return

        if quantity > 0:
            from_exchange = self.source_exchange
            to_exchange = self.target_exchange
            from_state = self.state.transit_from_source
            to_state = self.state.transit_to_target
            from_ticker = self.data.source_ticker
            to_ticker = self.data.target_ticker
            from_converter = self.state.convert_to_source
            to_converter = self.state.convert_to_target
            destination = 'target'
        else:
            from_exchange = self.target_exchange
            to_exchange = self.source_exchange
            from_state = self.state.transit_from_target
            to_state = self.state.transit_to_source
            from_ticker = self.data.target_ticker
            to_ticker = self.data.source_ticker
            from_converter = self.state.convert_to_target
            to_converter = self.state.convert_to_source
            destination = 'source'

        from_quantity = from_converter(self.data.source_ticker, abs(quantity))
        to_quantity = to_converter(self.data.source_ticker, abs(quantity))
        deposit_address = None

        # Get deposit address
        try:
            deposit_address = yield to_exchange.getNewAddress(to_ticker)
            yield from_exchange.requestWithdrawal(from_ticker, from_quantity, deposit_address)

            to_state.append({'to_ticker': to_ticker,
                              'from_ticker': from_ticker,
                              'from_quantity': from_quantity,
                              'to_quantity': to_quantity,
                              'address': deposit_address})
        except NotImplementedError:
            from_state.append({'to_ticker': to_ticker,
                               'from_ticker': from_ticker,
                                'from_quantity': from_quantity,
                                'to_quantity': to_quantity,
                                'address': deposit_address,
                                'destination': destination})

    @inlineCallbacks
    def transfer_source_out(self, quantity):
        if self.state.convert_to_source(self.data.source_ticker, float(quantity)) < EPSILON:
            return

        try:
            yield self.source_exchange.requestWithdrawal(self.data.source_ticker, quantity, self.out_address)
        except NotImplementedError:
            self.state.transit_from_source.append({'to_ticker': self.data.source_ticker,
                               'from_ticker': self.data.source_ticker,
                                'from_quantity': quantity,
                                'to_quantity': quantity,
                                'address': self.out_address,
                                'destination': 'OUT'})

    @inlineCallbacks
    def update_offers(self, bid, ask):
        edge_to_enter_in_target = self.state.convert_to_target(self.data.source_ticker, self.edge_to_enter)
        edge_to_leave_in_target = self.state.convert_to_target(self.data.source_ticker, self.edge_to_leave)
        bid_to_leave = self.target_exchange.round_bid(self.data.target_exchange_ticker, bid - edge_to_leave_in_target)
        bid_to_enter = self.target_exchange.round_bid(self.data.target_exchange_ticker, bid - edge_to_enter_in_target)
        ask_to_leave = self.target_exchange.round_ask(self.data.target_exchange_ticker, ask + edge_to_leave_in_target)
        ask_to_enter = self.target_exchange.round_ask(self.data.target_exchange_ticker, ask + edge_to_enter_in_target)

        ticker = self.data.target_exchange_ticker
        my_orders = [order for order in self.state.target_orders.values() if order['contract'] == ticker]

        bid_size = 0
        ask_size = 0
        for bid in [order for order in my_orders if order['side'] == 'BUY']:
            if bid['price'] > bid_to_leave or bid['price'] < bid_to_enter:
                self.target_exchange.cancelOrder(bid['id'])
            else:
                bid_size += bid['quantity_left']

        for ask in [order for order in my_orders if order['side'] == 'SELL']:
            if ask['price'] < ask_to_leave or ask['price'] > ask_to_enter:
                self.target_exchange.cancelOrder(ask['id'])
            else:
                ask_size += ask['quantity_left']

        if ask_to_enter < Decimal('Infinity'):
            if ask_size < self.quote_size:
                difference = self.quote_size - ask_size
                try:
                    yield self.target_exchange.placeOrder(ticker, difference, ask_to_enter, 'SELL')
                except Exception as e:
                    log.err("Unable to place SELL order on target: %s - %s %s" % (ticker, difference, ask_to_enter))
                    log.err(e)

        if bid_to_enter > 0:
            if bid_size < self.quote_size:
                difference = self.quote_size - bid_size
                try:
                    yield self.target_exchange.placeOrder(ticker, difference, bid_to_enter, 'BUY')
                except Exception as e:
                    log.err("Unable to place BUY order on target: %s - %s %s" % (ticker, difference, ask_to_enter))
                    log.err(e)


from twisted.web.resource import Resource
from twisted.web.static import File
from twisted.web.server import Site, NOT_DONE_YET
from twisted.internet import task
import json

class ILPEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return util.dt_to_timestamp(o)
        if isinstance(o, Decimal):
            return str(o)

        return json.JSONEncoder.default(self, o)

class ILPServer(Resource):
    isLeaf = True
    def __init__(self, state, valuation, data, trader):
        self.state = state
        self.valuation = valuation
        self.data = data
        self.trader = trader

    def get_update(self, request):
        # Send back all our data as a JSON
        data = {'state': self.state.todict(),
                'valuation': self.valuation.todict(),
                'data': self.data.todict(),
                'trader': self.trader.todict()
        }
        result = json.dumps(data, indent=2, sort_keys=True, allow_nan=False, cls=ILPEncoder).encode('utf-8')
        request.setHeader('Content-Type', 'application/json; charset=UTF-8')
        return result

    def render_GET(self, request):
        if request.postpath[0] == 'update':
            pass
        elif request.postpath[0] == 'start':
            self.trader.fsm.process("start")
        elif request.postpath[0] == 'stop':
            self.trader.fsm.process("stop")

        return self.get_update(request)

    def render_POST(self, request):
        data = json.load(request.content)
        fields = {'valuation': ['risk_aversion', 'deviation_penalty', 'target_balance_source', 'target_balance_target'],
                  'trader': ['quote_size', 'edge_to_enter', 'edge_to_leave'],
                  'data': ['source_fee', 'target_fee', 'btc_fee', 'fiat_exchange_cost']}
        decimal_fields = [('trader', 'quote_size')]
        for section, list in fields.iteritems():
            object = getattr(self, section)
            for field in list:
                if section in data and field in data[section]:
                    try:
                        if (section, field) in decimal_fields:
                            value = Decimal(data[section][field])
                        else:
                            value = data[section][field]
                            if isinstance(value, basestring):
                                value = float(value)
                        setattr(object, field, value)
                    except Exception as e:
                        log.err(e)
                        request.responseCode = 400
                        return str(e)

            object.save()

        d = self.valuation.optimize()
        def _cb(result):
            update = self.get_update(request)
            request.write(update)
            request.finish()

        d.addCallback(_cb)
        return NOT_DONE_YET


if __name__ == "__main__":
    log.startLogging(sys.stdout)
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s',
                        level=logging.INFO)

    config = ConfigParser()
    config_file = path.abspath(path.join(path.dirname(__file__),
                                         "./ilp.ini"))
    config.read(config_file)

    modules = dict(config.items("modules"))

    def load(path):
        module_name, class_name = path.rsplit(".", 1)
        mod = __import__(module_name)
        for component in module_name.split(".")[1:]:
            mod = getattr(mod, component)
        klass = getattr(mod, class_name)
        return klass

    target_class = load(modules['target'])
    source_class = load(modules['source'])
    fiat_class = load(modules['fiat'])

    source_connection = dict(config.items("source_connection"))
    target_connection = dict(config.items("target_connection"))
    source_exchange = source_class(**source_connection)
    target_exchange = target_class(**target_connection)
    fiat_exchange = fiat_class()

    tickers = dict(config.items("tickers"))

    data_params = {'fiat_exchange_cost': json.loads(config.get("data", "fiat_exchange_cost")),
                   'source_fee': json.loads(config.get("data", "source_fee")),
                   'target_fee': json.loads(config.get("data", "target_fee")),
                   'btc_fee': config.getfloat("data", "btc_fee"),
                   'btc_delay': config.getint("data", "btc_delay"),
                   'fiat_exchange_delay': config.getint("data", 'fiat_exchange_delay'),
                   'variance_period': config.get("data", "variance_period"),
                   'variance_window': config.get("data", "variance_window")}

    data = Data(source_exchange=source_exchange,
                target_exchange=target_exchange,
                fiat_exchange=fiat_exchange,
                source_ticker=tickers['source'],
                target_ticker=tickers['target'],
                btc_ticker=tickers['BTC'],
                **data_params)

    state = State(data)

    def to_float_dict(d):
        return {key: float(value) for key, value in d}

    target_balance_source = to_float_dict(config.items("target_balance_source"))
    target_balance_target = to_float_dict(config.items("target_balance_target"))

    valuation_params = to_float_dict(config.items("valuation"))

    valuation = Valuation(state=state,
                          data=data,
                          target_balance_source=target_balance_source,
                          target_balance_target=target_balance_target,
                          **valuation_params)

    trader_params = {'quote_size': Decimal(config.get("trader", "quote_size")),
                     'out_address': config.get("trader", "out_address"),
                     'edge_to_enter': config.getfloat("trader", "edge_to_enter"),
                     'edge_to_leave': config.getfloat("trader", "edge_to_leave"),
                     'period': config.getint("trader", "period")}

    trader = Trader(source_exchange=source_exchange,
                    target_exchange=target_exchange,
                    state=state,
                    data=data,
                    valuation=valuation,
                    **trader_params)

    server = ILPServer(state, valuation, data, trader)
    root = File("./ilp")
    root.putChild('api', server)
    site = Site(root)
    reactor.listenTCP(9304, site)
    trader.start().addErrback(log.err)

    reactor.run()





