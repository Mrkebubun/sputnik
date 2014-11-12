import sys
import os
from test_sputnik import fix_config, TestSputnik, FakeComponent
from twisted.internet import defer, reactor, task
from pprint import pprint

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../tools"))

fix_config()

from sputnik import models, margin

class TestMargin(TestSputnik):
    def setUp(self):
        TestSputnik.setUp(self)
        self.create_account("trader")

    def makeOrder(self, contract, quantity, price, side):
        user = self.get_user("trader")
        contract = self.get_contract(contract)
        order = models.Order(user, contract, quantity, price, side)
        self.session.add(order)
        return order

    def test_sufficient_cash(self):
        btc = self.get_contract("BTC")
        user = self.get_user("trader")
        position = self.session.query(models.Position).filter_by(
                user=user, contract=btc)
        position.position = 100000000
        order = self.makeOrder("BTC/MXN", 100000, 5500, "SELL")
        self.session.add(order)
        self.session.commit()

        low, high, _ = margin.calculate_margin(user, self.session, {}, order.id)
        assert high < position.position

    def test_insufficient_cash(self):
        btc = self.get_contract("BTC")
        user = self.get_user("trader")
        position = self.session.query(models.Position).filter_by(
                user=user, contract=btc)
        position.position = 100000000
        order = self.makeOrder("BTC/MXN", 1000000000, 5500, "SELL")
        self.session.add(order)
        self.session.commit()

        low, high, _ = margin.calculate_margin(user, self.session, {}, order.id)
        assert high > position.position
    
    def test_sufficient_cash_with_order(self):
        btc = self.get_contract("BTC")
        user = self.get_user("trader")
        position = self.session.query(models.Position).filter_by(
                user=user, contract=btc)
        position.position = 100000000
        existing_order = self.makeOrder("BTC/MXN", 40000000, 5500, "SELL")
        existing_order.accepted = True
        order = self.makeOrder("BTC/MXN", 50000000, 5500, "SELL")
        self.session.add(existing_order)
        self.session.commit()

        low, high, _ = margin.calculate_margin(user, self.session, {}, order.id)
        assert high < position.position

    def test_insufficient_cash_with_order(self):
        btc = self.get_contract("BTC")
        user = self.get_user("trader")
        position = self.session.query(models.Position).filter_by(
                user=user, contract=btc)
        position.position = 100000000
        existing_order = self.makeOrder("BTC/MXN", 60000000, 5500, "SELL")
        existing_order.accepted = True
        order = self.makeOrder("BTC/MXN", 50000000, 5500, "SELL")
        self.session.add(existing_order)
        self.session.commit()

        low, high, _ = margin.calculate_margin(user, self.session, {}, order.id)
        assert high > position.position

