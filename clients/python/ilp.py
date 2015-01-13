__author__ = 'sameer'

from datetime import datetime
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor
from twisted.python import log
from copy import copy, deepcopy
import collections

class State():
    def __init__(self, data):
        # ILP
        self.data = data

        # State
        self.timestamp = None
        self.fiat_book = None
        self.source_book = None
        self.target_book = None
        self.balance_target = None
        self.balance_source = None
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
        self.fiat_book = yield self.data.get_fiat_book()
        self.source_book = yield self.data.get_source_book()
        self.target_book = yield self.data.get_target_book()
        self.balance_source = yield self.data.get_source_positions()
        self.balance_target = yield self.data.get_target_positions()

        # Update transits - remove ones that have arrived
        source_transactions = yield self.data.get_source_transactions(last_update, self.timestamp)
        target_transactions = yield self.data.get_target_transactions(last_update, self.timestamp)

        returnValue(None)

    def source_trade(self, quantity, side):
        quantity_left = quantity
        if side == 'BUY':
            half = 'asks'
            sign = 1
        else:
            half = 'bids'
            sign = -1

        total_spent = 0
        total_bought = 0

        for row in self.source_book[half]:
            price = row['price']
            quantity = min(quantity_left, row['quantity'])
            total_spent += price * quantity
            total_bought += quantity
            quantity_left -= quantity

        fee = abs(total_spent * self.data.source_fee[1]) + self.data.source_fee[0]

        self.balance_source[self.data.source_ticker]['position'] -= sign * total_spent + fee
        self.balance_source[self.data.btc_ticker]['position'] += sign * total_bought

    def target_trade(self, quantity, price, side):
        total_spent = quantity * price
        total_bought = quantity
        fee = abs(total_spent * self.data.target_fee[1]) + self.data.target_fee[0]

        if side == 'BUY':
            sign = 1
        else:
            sign = -1

        self.balance_target[self.data.target_ticker]['position'] -= sign * total_spent + fee
        self.balance_target[self.data.btc_ticker]['position'] += sign * total_bought

    def source_target_fiat_transfer(self, amount):
        assert(amount > 0)
        fee = amount * self.data.fiat_exchange_cost[1] + self.data.fiat_exchange_cost[0]
        self.balance_source[self.data.source_ticker]['position'] -= amount + fee
        self.balance_target[self.data.target_ticker]['position'] += amount * self.fiat_book['asks'][0]['price']

    def target_source_fiat_transfer(self, amount):
        assert(amount > 0)
        self.balance_source[self.data.target_ticker]['position'] -= amount
        fee = amount / self.fiat_exchange_rate * self.data.fiat_exchange_cost[1] + self.data.fiat_exchange_cost[0]
        self.balance_target[self.data.source_ticker]['position'] += amount / self.fiat_book['bids'][0]['price'] - fee

    # BTC transfer from source->fiat, we can make amount negative
    def btc_transfer(self, amount):
        fee = self.data.btc_fee
        self.balance_source[self.data.btc_ticker]['position'] -= amount
        self.balance_target[self.data.btc_ticker]['position'] += amount
        if amount > 0:
            self.balance_source[self.data.btc_ticker]['position'] -= self.data.btc_fee
        else:
            self.balance_target[self.data.btc_ticker]['position'] -= self.data.btc_fee

    def mid(self, bid, ask):
        return (bid + ask) / 2

    @property
    def source_exchange_rate(self):
        return self.mid(self.source_book['bids'][0]['price'],
                 self.source_book['asks'][0]['price'])

    @property
    def fiat_exchange_rate(self):
        return self.mid(self.fiat_book['bids'][0]['price'],
                 self.fiat_book['asks'][0]['price'])

    @property
    def target_exchange_rate(self):
        return self.mid(self.target_book['bids'][0]['price'],
                        self.target_book['asks'][0]['price'])

    @property
    def total_balance_target(self):
        total_balance = copy(self.balance_target)

        for id, transit in self.transit_to_target.iteritems():
            total_balance[transit['ticker']]['position'] += transit['quantity']

        for id, transit in self.transit_from_target.iteritems():
            total_balance[transit['ticker']]['position'] -= transit['quantity']

        return total_balance

    @property
    def total_balance_source(self):
        total_balance = copy(self.balance_source)

        for id, transit in self.transit_to_source.iteritems():
            total_balance[transit['ticker']]['position'] += transit['quantity']

        for id, transit in self.transit_from_source.iteritems():
            total_balance[transit['ticker']]['position'] -= transit['quantity']

        return total_balance

class Valuation():
    def __init__(self,
                 state,
                 data,
                 edge,
                 target_balance_source,
                 target_balance_target,
                 deviation_penalty, # (per dollar of deviation)
                 risk_aversion,
                 quote_size,
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

    def convert_to_source(self, ticker, quantity):
        if ticker == self.data.source_ticker:
            return quantity
        if ticker == self.data.btc_ticker:
            return self.state.source_exchange_rate * quantity
        if ticker == self.data.target_ticker:
            return self.state.fiat_exchange_rate * quantity

    @property
    def penalty(self):
        excess_in_source = 0
        for ticker, target in self.target_balance_source.iteritems():
            position = self.state.total_balance_source.get(ticker)
            if position is not None:
                excess = position['position'] - target
            else:
                excess = -target

            excess_in_source += self.convert_to_source(ticker, excess)

        for ticker, target in self.target_balance_target.iteritems():
            position = self.state.total_balance_target.get(ticker)
            if position is not None:
                excess = position['position'] = target
            else:
                excess = -target

            excess_in_source += self.convert_to_source(ticker, excess)

        return self.deviation_penalty * excess_in_source

    @property
    def balance_in_source(self):
        balance_in_source = collections.defaultdict(int)
        for ticker, position in self.state.total_balance_source.iteritems():
            balance_in_source[ticker] += self.convert_to_source(ticker, position['position'])

        for ticker, position in self.state.total_balance_target.iteritems():
            balance_in_source[ticker] += self.convert_to_source(ticker, position['position'])

        return balance_in_source

    @property
    def total_in_source(self):
        return(sum(self.balance_in_source.values()))

    @property
    def market_risk(self):
        risk = 0
        for ticker, balance in self.balance_in_source.iteritems():
            if ticker == self.source_ticker:
                pass
            if ticker == self.target_ticker:
                risk += balance * self.fiat_exchange_var
            if ticker == self.btc_ticker:
                risk += balance * self.source_exchange_var

        risk *= self.risk_aversion
        return risk

    @property
    def happiness(self):
        return self.total_in_source - self.market_risk - self.penalty

    @inlineCallbacks
    def run_scenarios(self):
        result = yield self.state.update()

        # Baseline
        base_state = deepcopy(self.state)
        base_happiness = self.happiness

        # Consider state if quotes are filled
        if self.state.offered_ask is not None:
            self.state.target_trade(self.quote_size, self.state.offered_ask, 'SELL')

        if self.state.offered_bid is not None:
            self.state.target_trade(self.quote_size, self.state.offered_bid, 'BUY')

        executed_state = deepcopy(self.state)
        happiness_if_executed = self.happiness

        # Consider new bid/ask
        self.state = base_state

        max_happiness = happiness_if_executed
        happy_details = None

        # Consider different bids
        base_bid = self.state.fiat_book['bids'][0]['price'] * self.state.source_book['bids'][0]['price']
        for bid in [base_bid * factor for factor in range(0.90,0.99,0.01)]:

            # Consider different asks
            base_ask = self.state.fiat_book['asks'][0]['price'] * self.state.source_book['asks'][0]['price']
            for ask in [base_ask * factor for factor in range(0.90,0.99,0.01)]:

                # Consider buying or selling on the source exchange
                for source_trade_side in ['BUY', 'SELL']:

                    # Up to 10% of my btc position on that exchange
                    source_btc = self.state.balance_source[self.data.btc_ticker]['position']
                    for source_trade_size in [source_btc * factor for factor in range(0.01, 0.10, 0.01)]:

                        # Transfer up to 10% of my fiat position to the other exchange
                        for transfer in ['source', 'target']:
                            if transfer == "source":
                                transfer_balance = self.state.balance_source[self.data.source_ticker]['position']
                            else:
                                transfer_balance = self.state.balance_target[self.data.target_ticker]['position']
                            for transfer_size in [transfer_balance * factor for factor in range(0.01, 0.10, 0.01)]:

                                # Consider transferring BTC from one exchange to another
                                btc_balance = self.state.balance_source[self.data.btc_ticker]['position'] + self.state.balance_target[self.data.target_ticker]['position']
                                for btc_transfer_size in [btc_balance * factor for factor in range(-0.05, 0.05, 0.01)]:
                                    self.state = base_state
                                    self.state.target_trade(self.quote_size, ask, 'SELL')
                                    self.state.target_trade(self.quote_size, bid, 'BUY')
                                    self.state.source_trade(source_trade_size, source_trade_side)

                                    if transfer == 'source':
                                        self.state.source_target_fiat_transfer(transfer_size)
                                    else:
                                        self.state.target_source_fiat_transfer(transfer_size)

                                    self.state.btc_transfer(btc_transfer_size)


                                    happiness = self.happiness
                                    if max_happiness is None or happiness > max_happiness:
                                        max_happiness = happiness
                                        happy_details = {'bid': bid,
                                                         'ask': ask,
                                                         'source_trade_side': source_trade_side,
                                                         'source_trade_size': source_trade_size,
                                                         'transfer': transfer,
                                                         'transfer_size': transfer_size,
                                                         'btc_transfer_size': btc_transfer_size }

        if (max_happiness - happiness_if_executed) / happiness_if_executed - 1.0 > self.edge:
            returnValue(happy_details)
        else:
            returnValue(None)

class MarketData():
    def __init__(self,
                 source_exchange,
                 target_exchange,
                 fiat_data,
                 source_ticker,
                 target_ticker,
                 btc_ticker,
                 fiat_exchange_cost, # (fixed_fee, prop_fee) (assume fees are charged in 'source' currency)
                 fiat_exchange_delay, # (source->target, target->source) (seconds)
                 source_fee, # (fixed_fee, prop_fee)
                 target_fee, # (fixed_fee, prop_fee)
                 btc_fee, # fixed_fee
                 btc_delay, # (seconds)
    ):

        # Configurations
        self.source_exchange = source_exchange
        self.target_exchange = target_exchange
        self.fiat_data = fiat_data
        self.source_ticker = source_ticker
        self.target_ticker = target_ticker
        self.btc_ticker = btc_ticker

        # Outside parameters
        self.fiat_exchange_cost = fiat_exchange_cost
        self.fiat_exchange_delay = fiat_exchange_delay
        self.source_fee = source_fee
        self.target_fee = target_fee
        self.btc_fee = btc_fee
        self.btc_delay = btc_delay


    def get_fiat_order_book(self):
        return self.fiat_exchange.getOrderBook('%s/%s' % (self.source_ticker, self.target_ticker))

    def get_source_order_book(self):
        return self.source_exchange.getOrderBook('%s/%s' % (self.btc_ticker, self.source_ticker))

    def get_target_positions(self):
        return self.target_exchange.getPositions()

    def get_source_positions(self):
        return self.source_exchange.getPositions()

    def get_source_transactions(self, start_timestamp, end_timestamp):
        return self.source_exchange.getTransactionHistory(start_timestamp, end_timestamp)

    def get_target_transactions(self, start_timestamp, end_timestamp):
        return self.target_exchange.getTransactionHistory(start_timestamp, end_timestamp)










