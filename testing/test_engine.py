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

    def test_ask(self):
        order = self.create_order(1, 100, 1)
        # make a copy of the order to compare against
        order2 = self.create_order(1, 100, 1)
        order2.id = order.id
        order2.timestamp = order.timestamp
        self.engine.place_order(order)
        self.assertDictEqual(self.engine.orderbook, {-1:[], 1:[order2]})

class TestAccountantNotifier(TestEngine):
    pass

class TestWebserverNotifier(TestEngine):
    pass

class TestSafePriceNotifier(TestEngine):
    pass

