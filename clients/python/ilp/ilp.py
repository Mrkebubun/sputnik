__author__ = 'sameer'

from datetime import datetime
from twisted.internet.defer import inlineCallbacks, returnValue, gatherResults, Deferred
from twisted.internet import reactor, task
from twisted.python import log
from copy import copy, deepcopy
import collections
import sys
import math
from pprint import pprint, pformat
from decimal import Decimal
import numpy as np
from scipy.optimize import minimize
from jinja2 import Environment, FileSystemLoader

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

        # Currently offered bid at ask at target exchange
        self.offered_bid = None
        self.offered_ask = None

        # Transit states are a dict of transfers in progress, keyed
        # by a transfer id, the value is a dict with fields 'quantity',
        # 'eta', and 'ticker'
        self.transit_to_source = {}
        self.transit_to_target = {}

        # Transit from are because some API don't support
        # withdrawal, in which case we need to record that we've asked a human
        # to make a transfer from one exchange to another
        self.transit_from_source = {}
        self.transit_from_target = {}

        self.update()

    @inlineCallbacks
    def update(self):
        last_update = self.timestamp
        self.timestamp = datetime.utcnow()
        fb_d = self.data.get_fiat_book()
        sb_d = self.data.get_source_book()
        tb_d = self.data.get_target_book()
        bs_d = self.data.get_source_positions()
        bt_d = self.data.get_target_positions()
        st_d = self.data.get_source_transactions(last_update, self.timestamp)
        tt_d = self.data.get_target_transactions(last_update, self.timestamp)


        # Gather all the results and get all the dataz
        [self.fiat_book, self.source_book, self.target_book, self.balance_source, self.balance_target,
         source_transactions, target_transactions] = \
            yield gatherResults([fb_d, sb_d, tb_d, bs_d, bt_d, st_d, tt_d])

        # Update transits - remove ones that have arrived
        # How do we do this?

        returnValue(None)

    def source_trade(self, quantity):
        """

        :param quantity:
        :return:

        Get the impact to balances if we place a limit order for 'quantity' at the source exchange
        if quantity < 0, we are selling. Quantity is in BTC
        """
        if quantity > 0:
            half = 'asks'
            sign = 1
        elif quantity < 0:
            quantity = -quantity
            half = 'bids'
            sign = -1
        else:
            return {self.data.source_ticker: Decimal(0),
                    self.data.btc_ticker: Decimal(0)}

        quantity_left = quantity
        total_spent = 0
        total_bought = 0

        # Find the liquidity in the book
        for row in self.source_book[half]:
            price = row['price']
            quantity = min(quantity_left, row['quantity'])
            total_spent += price * Decimal(quantity)
            total_bought += quantity
            quantity_left -= quantity
            if quantity_left <= 0:
                break

        fee = abs(total_spent) * Decimal(self.data.source_fee[1]) + self.data.source_fee[0]

        return {self.data.source_ticker: Decimal(-(sign * total_spent + fee)),
                self.data.btc_ticker: Decimal(sign * total_bought)}

    def target_trade(self, quantity, price, side):
        """

        :param quantity:
        :param price:
        :param side:
        :return:

        What are the results if we place a limit order on the target exchange
        and it is executed? Quantity must be greater than 0
        """
        if quantity > 0:
            total_spent = quantity * price
            total_bought = quantity
            fee = abs(total_spent * self.data.target_fee[1]) + self.data.target_fee[0]

            if side == 'BUY':
                sign = 1
            else:
                sign = -1

            return {self.data.target_ticker: Decimal(- sign * total_spent + fee),
                    self.data.btc_ticker: Decimal(sign * total_bought)}
        else:
            return {self.data.target_ticker: Decimal(0),
                    self.data.btc_ticker: Decimal(0)}

    def source_target_fiat_transfer(self, amount):
        """

        :param amount:
        :return:
        What is the impact on balances if we transfer fiat from the source exchange
        to the target exchange. Amount is always in source currency, but if it is negative,
        we are doing a transfer from the target exchange to the source exchange. The fees are charged
        to the exchange that is receiving the money

        """
        if amount != 0:
            fee_in_source = abs(amount) * self.data.fiat_exchange_cost[1] + self.data.fiat_exchange_cost[0]
            if amount > 0:
                return { self.data.source_ticker: Decimal(-amount),
                         self.data.target_ticker: self.convert_to_target(self.data.source_ticker, Decimal(amount - fee_in_source))}
            else:
                return { self.data.source_ticker: Decimal(abs(amount) - fee_in_source),
                         self.data.target_ticker: self.convert_to_target(self.data.source_ticker, Decimal(amount))}
        else:
            return {self.data.target_ticker: Decimal(0),
                    self.data.source_ticker: Decimal(0)}

    def btc_transfer(self, amount):
        """

        :param amount:
        :return:
        Transfer btc from source to target exchange. If amount is negative,
        transfer in the other direction. We assume exchange charges no BTC transfer
        fees but there is a BTC transfer fee charged by the network. We charge it
        to the receiving side
        """
        if amount > 0:
            return {'source_btc': Decimal(-amount),
                    'target_btc': Decimal(amount - self.data.btc_fee)}
        elif amount < 0:
            return {'source_btc': Decimal(abs(amount) - self.data.btc_fee),
                    'target_btc': Decimal(amount)}
        else:
            return {'source_btc': Decimal(0),
                    'target_btc': Decimal(0)}

    def transfer_source_out(self, amount):
        """

        :param amount:
        :return:
        Transfer source currency out of the source exchange to our own bank. We can't transfer in
        """
        fee = abs(amount) * self.data.fiat_exchange_cost[1] + self.data.fiat_exchange_cost[0]
        if amount > 0:
            return {self.data.source_ticker: Decimal(-(amount + fee))}
        else:
            return {self.data.source_ticker: Decimal(0)}

    def get_best_bid(self, book):
        if 'bids' in book and len(book['bids']) > 0:
            return book['bids'][0]['price']
        else:
            # There is no bid, worth 0!
            return Decimal(0)

    def get_best_ask(self, book):
        if 'asks' in book and len(book['asks']) > 0:
            return book['asks'][0]['price']
        else:
            # There is no bid, worth 0!
            return Decimal('Infinity')

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
        total_balance = copy(self.balance_target)

        for id, transit in self.transit_to_target.iteritems():
            total_balance[transit['ticker']]['position'] += transit['quantity']

        for id, transit in self.transit_from_target.iteritems():
            total_balance[transit['ticker']]['position'] -= transit['quantity']

        return total_balance

    @property
    def total_balance_source(self):
        """


        :return:
        Give us the total balances at the source taking into account cash that is in transit
        both in and out
        """
        total_balance = copy(self.balance_source)

        for id, transit in self.transit_to_source.iteritems():
            total_balance[transit['ticker']]['position'] += transit['quantity']

        for id, transit in self.transit_from_source.iteritems():
            total_balance[transit['ticker']]['position'] -= transit['quantity']

        return total_balance

    def constraint_fn(self, params={}):
        """
        Given the state of the exchanges, tell us what we can't do. This current
        version doesn't take into account fees. Actual version will actually call the "impact"
        functions and make sure that they don't result in negative balances

        :param params:
        :return:
        """
        offered_bid = params.get('offered_bid', 0)
        offered_ask = params.get('offered_ask', 0)
        btc_source_target = params.get('btc_source_target', 0)
        fiat_source_target = params.get('fiat_source_target', 0)
        trade_source_qty = params.get('trade_source_qty', 0)
        transfer_source_out = params.get('transfer_source_out', 0)

        if offered_ask or offered_bid < 0:
            return False
        if offered_ask <= offered_bid:
            return False
        if btc_source_target > 0 and btc_source_target > self.total_balance_source[self.data.btc_ticker]['positon']:
            return False
        if btc_source_target < 0 and abs(btc_source_target) > self.total_balance_target[self.data.btc_ticker]['position']:
            return False
        if fiat_source_target > 0 and fiat_source_target > self.total_balance_source[self.data.source_ticker]['position']:
            return False
        if fiat_source_target < 0 and abs(fiat_source_target) > self.convert_to_source(self.data.target_ticker, self.total_balance_target[self.data.target_ticker]['position']):
            return False
        if trade_source_qty < 0 and trade_source_qty > self.total_balance_source[self.data.btc_ticker]['position']:
            return False
        if trade_source_qty > 0 and self.convert_to_source(self.data.btc_ticker, trade_source_qty) > self.total_balance_source[self.data.source_ticker]['position']:
            return False
        if transfer_source_out > 0 and transfer_source_out > self.total_balance_source[self.data.source_ticker]['position']:
            return False
        if transfer_source_out < 0:
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

class Valuation():
    def __init__(self,
                 state,
                 data,
                 edge,
                 target_balance_source,
                 target_balance_target,
                 deviation_penalty, # dimensionless factor on USD
                 risk_aversion, # ( 1 / USD )
                 quote_size, # BTC
                 fiat_exchange_var,
                 source_exchange_var,
                 fiat_source_cov # ignore for now
                 ):

        self.state = state
        self.data = data

        # Tunable parameters
        self.edge = edge
        self.target_balance_source = target_balance_source
        self.target_balance_target = target_balance_target
        self.deviation_penalty = deviation_penalty
        self.risk_aversion = risk_aversion
        self.quote_size = quote_size

        # External
        self.fiat_exchange_var = fiat_exchange_var
        self.source_exchange_var = source_exchange_var
        self.fiat_source_cov = fiat_source_cov

        self.optimized_params = {}
        self.optimized = {}

    # [ offered_bid, offered_ask, BTC source<->target (+ means move to source), Fiat source<->target,
    #   trade_source_qty, transfer_source_out ]
    def valuation(self, params={}):
        # Get current balances

        source_source_balance = self.state.total_balance_source[self.data.source_ticker]['position']
        source_btc_balance = self.state.total_balance_source[self.data.btc_ticker]['position']
        target_target_balance = self.state.total_balance_target[self.data.target_ticker]['position']
        target_btc_balance = self.state.total_balance_target[self.data.btc_ticker]['position']

        offered_bid = params.get('offered_bid', 0)
        offered_ask = params.get('offered_ask', 0)
        btc_source_target = params.get('btc_source_target', 0)
        fiat_source_target = params.get('fiat_source_target', 0)
        trade_source_qty = params.get('trade_source_qty', 0)
        transfer_source_out = params.get('transfer_source_out', 0)

        # Get effect of various activities
        bid_consequence = self.state.target_trade(self.quote_size, offered_bid, 'BUY')
        ask_consequence = self.state.target_trade(self.quote_size, offered_ask, 'ASK')
        btc_transfer_consequence = self.state.btc_transfer(btc_source_target)
        fiat_transfer_consequence = self.state.source_target_fiat_transfer(fiat_source_target)
        trade_source_consequence = self.state.source_trade(trade_source_qty)
        transfer_out_consequence = self.state.transfer_source_out(transfer_source_out)

        # It has an impact on our balances
        target_target_balance += bid_consequence[self.data.target_ticker]
        target_btc_balance += bid_consequence[self.data.btc_ticker]

        target_target_balance += ask_consequence[self.data.target_ticker]
        target_btc_balance += ask_consequence[self.data.btc_ticker]

        target_btc_balance += btc_transfer_consequence['target_btc']
        source_btc_balance += btc_transfer_consequence['source_btc']

        target_target_balance += fiat_transfer_consequence[self.data.target_ticker]
        source_source_balance += fiat_transfer_consequence[self.data.source_ticker]

        source_source_balance += trade_source_consequence[self.data.source_ticker]
        source_btc_balance += trade_source_consequence[self.data.btc_ticker]

        source_source_balance += transfer_out_consequence[self.data.source_ticker]

        # Deviation Penalty
        source_source_target = self.target_balance_source[self.data.source_ticker]
        source_btc_target = self.target_balance_source[self.data.btc_ticker]
        target_target_target = self.target_balance_target[self.data.target_ticker]
        target_btc_target = self.target_balance_target[self.data.btc_ticker]

        def get_penalty(balance, target):
            if balance < 0:
                return Decimal('Infinity')
            critical_min = Decimal(0.25) * target
            min_bal = Decimal(0.75) * target
            max_bal = Decimal(1.25) * target
            critical_max = Decimal(5) * target
            penalty = max(0, critical_min - balance) * 10 + max(0, min_bal - balance) * 3 + max(0, balance - max_bal) * 1 + max(0, balance - critical_max) * 3
            return penalty

        deviation_penalty_in_source = \
            self.state.convert_to_source(self.data.source_ticker, get_penalty(source_source_balance, source_source_target)) + \
            self.state.convert_to_source(self.data.btc_ticker, get_penalty(source_btc_balance, source_btc_target)) + \
            self.state.convert_to_source(self.data.target_ticker, get_penalty(target_target_balance, target_target_target)) + \
            self.state.convert_to_source(self.data.btc_ticker, get_penalty(target_btc_balance, target_btc_target))

        deviation_penalty_in_source *= Decimal(self.deviation_penalty)

        # Market Risk
        market_risk_in_source = Decimal(self.risk_aversion) * \
                      (Decimal(self.source_exchange_var) * pow(source_btc_balance + target_btc_balance, 2) +
                       Decimal(self.fiat_exchange_var) * pow(target_target_balance, 2))

        # Total value
        total_value_in_source = self.state.convert_to_source(self.data.source_ticker, source_source_balance) + \
                      self.state.convert_to_source(self.data.btc_ticker, source_btc_balance + target_btc_balance) + \
                      self.state.convert_to_source(self.data.target_ticker, target_target_balance)

        value = total_value_in_source - market_risk_in_source - deviation_penalty_in_source
        ret = {'optimized_value': value,
                    'total_value_in_source': total_value_in_source,
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
            wait = yield self.state.update()
            self.base_params = {}
            if self.state.offered_bid is not None:
                self.base_params['offered_bid'] = self.state.offered_bid
            if self.state.offered_ask is not None:
                self.base_params['offered_ask'] = self.state.offered_ask

            self.base_value = self.valuation(params=self.base_params)['optimized_value']
            def negative_valuation(x):
                params = {'offered_bid': x[0],
                          'offered_ask': x[1],
                          'btc_source_target': x[2],
                          'fiat_source_target': x[3],
                          'trade_source_qty': x[4],
                          'transfer_source_out': x[5]}

                ret = self.valuation(params=params)
                return float(-ret['optimized_value'])

            base_rate = float(self.state.source_exchange_rate) / float(self.state.fiat_exchange_rate)
            def constraint(x):
                params = {'offered_bid': x[0],
                          'offered_ask': x[1],
                          'btc_source_target': x[2],
                          'fiat_source_target': x[3],
                          'trade_source_qty': x[4],
                          'transfer_source_out': x[5]}
                if self.state.constraint_fn(params):
                    return 1
                else:
                    return -1

            x0 = np.array([base_rate, base_rate, 0, 0, 0, 0])

            res = minimize(negative_valuation, x0, method='COBYLA',
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



class MarketData():
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


    def get_fiat_book(self):
        return self.fiat_exchange.getOrderBook('%s/%s' % (self.target_ticker, self.source_ticker))

    def get_source_book(self):
        return self.source_exchange.getOrderBook('%s/%s' % (self.btc_ticker, self.source_ticker))

    def get_target_book(self):
        return self.target_exchange.getOrderBook('%s/%s' % (self.btc_ticker, self.target_ticker))

    def get_target_positions(self):
        return self.target_exchange.getPositions()

    def get_source_positions(self):
        return self.source_exchange.getPositions()

    def get_source_transactions(self, start_timestamp, end_timestamp):
        return self.source_exchange.getTransactionHistory(start_timestamp, end_timestamp)

    def get_target_transactions(self, start_timestamp, end_timestamp):
        return self.target_exchange.getTransactionHistory(start_timestamp, end_timestamp)

from twisted.web.resource import Resource
from twisted.web.server import Site

class Webserver(Resource):
    isLeaf = True
    def __init__(self, state, valuation, template_dir="."):
        self.state = state
        self.valuation = valuation


        self.jinja_env = Environment(loader=FileSystemLoader(template_dir),
                                     autoescape=True)

    def render_GET(self, request):
        # Do the JINJA

        t = self.jinja_env.get_template("template.html")
        return t.render(object=self).encode('utf-8')

if __name__ == "__main__":
    @inlineCallbacks
    def main():
        import sys
        sys.path.append("..")
        from sputnik import Sputnik
        from yahoo import Yahoo

        connection = { 'ssl': False,
                       'port': 8880,
                       'hostname': 'localhost',
                       'ca_certs_dir': "/etc/ssl/certs" }

        debug = False

        source_exchange = Sputnik(connection, {'username': 'ilp_source',
                                               'password': 'ilp'}, debug)
        target_exchange = Sputnik(connection, {'username': 'ilp_target',
                                               'password': 'ilp'}, debug)
        se = source_exchange.connect()
        te = target_exchange.connect()
        yield gatherResults([se, te])

        fiat_exchange = Yahoo()
        market_data = MarketData(source_exchange=source_exchange,
                                 target_exchange=target_exchange,
                                 fiat_exchange=fiat_exchange,
                                 source_ticker='USD',
                                 target_ticker='HUF',
                                 btc_ticker='BTC',
                                 fiat_exchange_cost=(150, 0.1), # Set the exchange cost pretty high because of the delay
                                 fiat_exchange_delay=86400 * 3,
                                 source_fee=(0, 0.01),
                                 target_fee=(0, 0.005),
                                 btc_fee=0.0001,
                                 btc_delay=3600,
                                 variance_period="day",
                                 variance_window="30"
                                 )
        state = State(market_data)
        valuation = Valuation(state=state,
                              data=market_data,
                              edge=0.04,
                              target_balance_source={ 'USD': Decimal(6000),
                                                      'BTC': Decimal(6) },
                              target_balance_target={ 'HUF': Decimal(1626000),
                                                      'BTC': Decimal(6) },
                              deviation_penalty=50,
                              risk_aversion=0.0001,
                              quote_size=0.01,
                              fiat_exchange_var=23,
                              source_exchange_var=1003,
                              fiat_source_cov=0)

        server = Webserver(state, valuation)
        site = Site(server)
        reactor.listenTCP(9304, site)

        while True:
            try:
                yield valuation.optimize()
            except Exception as e:
                log.err(e)
                pass

    log.startLogging(sys.stdout)
    main().addErrback(log.err)
    reactor.run()





