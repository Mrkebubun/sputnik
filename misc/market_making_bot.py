import sys
from pprint import pprint

from twisted.python import log
from twisted.internet import reactor, ssl

from autobahn.websocket import connectWS
from autobahn.wamp import WampClientFactory, WampCraClientProtocol

import database as db
from pepsiClient import TradingBot

class MarketMakingBot(TradingBot):
    def __init__(self, user_id, contract_id, ticker, risk_sensitivity, quantity):
        self.user_id = user_id
        self.contract_id = contract_id
        self.ticker = ticker
        self.risk_sensitivity = risk_sensitivity
        self.quantity = quantity

    def adjusted_price(self):
        return self.theoretical_price - 2 * self.risk_sensitivity * self.position

    def get_bid_price(self):
        return self.adjusted_price() - self.risk_sensitivity

    def get_ask_price(self):
        return self.adjusted_price() + self.risk_sensitivity

    def on_trade(self, amount, quantity):
       #todo: cancel existing orders
       # place new orders
       # bid_order = {"side":0,"price":get_bid_price(),ticker=self.ticker,quantity=self.quantity}
       # ask_order = {"side":1,"price":get_ask_price(),ticker=self.ticker,quantity=self.quantity}

       self.placeOrder(self.ticker,self.quantity,self.get_bid_price(), 0)
       self.placeOrder(self.ticker,self.quantity,self.get_ask_price(), 1)
