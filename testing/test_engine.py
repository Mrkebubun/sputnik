import sys
import os
import copy
from test_sputnik import TestSputnik, FakeProxy
from twisted.internet import defer
from pprint import pprint

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../tools"))

class TestEngine(TestSputnik):
    def setUp(self):
        TestSputnik.setUp(self)

        from sputnik import engine2

        self.engine = engine2.Engine()
        self.fake_listener = FakeProxy()
        self.engine.add_listener(self.fake_listener)
        self.order_counter = 0

    def create_order(self, quantity=None, price=None, side=None):
        from sputnik.engine2 import Order
        self.order_counter += 1
        return Order(id=self.order_counter, contract="FOO", quantity=quantity,
            price=price, side=side)

class TestEngineInternals(TestEngine):
    def test_bid(self):
        order = self.create_order(1, 100, -1)
        # make a copy of the order to compare against
        order2 = self.create_order(1, 100, -1)
        order2.id = order.id
        order2.timestamp = order.timestamp
        self.engine.place_order(order)
        self.assertDictEqual(self.engine.orderbook, {-1:[order2], 1:[]})
        pprint(self.fake_listener.log)

    def test_ask(self):
        order = self.create_order(1, 100, 1)
        # make a copy of the order to compare against
        order2 = self.create_order(1, 100, 1)
        order2.id = order.id
        order2.timestamp = order.timestamp
        self.engine.place_order(order)
        self.assertDictEqual(self.engine.orderbook, {-1:[], 1:[order2]})
        pprint(self.fake_listener.log)

    def test_trade_perfect_match(self):
        order_bid = self.create_order(1, 100, -1)
        order_ask = self.create_order(1, 100, 1)

        self.engine.place_order(order_bid)
        self.engine.place_order(order_ask)
        self.assertDictEqual(self.engine.orderbook, {-1: [], 1:[]})
        pprint(self.fake_listener.log)

    def test_trade_crossed(self):
        order_bid = self.create_order(1, 100, -1)
        order_ask = self.create_order(1, 95, 1)

        self.engine.place_order(order_bid)
        self.engine.place_order(order_ask)
        self.assertDictEqual(self.engine.orderbook, {-1: [], 1:[]})
        pprint(self.fake_listener.log)

    def test_no_trade(self):
        order_bid = self.create_order(1, 100, -1)
        order_ask = self.create_order(1, 105, 1)

        self.engine.place_order(order_bid)
        self.engine.place_order(order_ask)
        self.assertDictEqual(self.engine.orderbook, {-1: [order_bid], 1:[order_ask]})
        pprint(self.fake_listener.log)

    def test_trade_different_size(self):
        order_bid = self.create_order(2, 100, -1)
        order_ask = self.create_order(1, 100, 1)

        self.engine.place_order(order_bid)
        self.engine.place_order(order_ask)
        pprint(self.engine.orderbook)
        pprint(self.fake_listener.log)

class TestAccountantNotifier(TestEngine):
    pass

class TestWebserverNotifier(TestEngine):
    pass

class TestSafePriceNotifier(TestEngine):
    pass

