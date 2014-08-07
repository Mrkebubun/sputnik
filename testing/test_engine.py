import sys
import os
import copy
from test_sputnik import TestSputnik, FakeComponent
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
        self.fake_listener = FakeComponent("listener")
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
        self.engine.place_order(order)
        self.assertTrue(FakeComponent.check(self.engine.orderbook, {-1: [order2], 1: []}))
        self.assertTrue(self.fake_listener.component.check_for_calls([('on_queue_success',
                                                             (order2,),
                                                             {})]))

    def test_ask(self):
        order = self.create_order(1, 100, 1)
        # make a copy of the order to compare against
        order2 = self.create_order(1, 100, 1)
        self.engine.place_order(order)
        self.assertTrue(FakeComponent.check(self.engine.orderbook, {-1: [], 1: [order2]}))
        self.assertTrue(self.fake_listener.component.check_for_calls([('on_queue_success',
                                                             (order2,),
                                                             {})]))

    def test_trade_perfect_match(self):
        order_bid = self.create_order(1, 100, -1)
        order_bid2 = self.create_order(1, 100, -1)
        order_bid3 = self.create_order(1, 100, -1)
        order_bid3.quantity_left = 0

        order_ask = self.create_order(1, 100, 1)
        order_ask2 = self.create_order(1, 100, 1)
        order_ask2.quantity_left = 0

        self.engine.place_order(order_bid)
        self.engine.place_order(order_ask)
        self.assertTrue(FakeComponent.check(self.engine.orderbook, {-1: [], 1: []}))
        self.assertTrue(self.fake_listener.component.check_for_calls([('on_queue_success',
                                                             (order_bid2,),
                                                             {}),
                                                            ('on_trade_success',
                                                             (order_ask2,
                                                              order_bid3,
                                                              100,
                                                              1),
                                                             {})]))

    def test_trade_crossed(self):
        order_bid = self.create_order(1, 100, -1)
        order_bid2 = self.create_order(1, 100, -1)
        order_bid3 = self.create_order(1, 100, -1)
        order_bid3.quantity_left = 0
        order_ask = self.create_order(1, 95, 1)
        order_ask2 = self.create_order(1, 95, 1)
        order_ask2.quantity_left = 0

        self.engine.place_order(order_bid)
        self.engine.place_order(order_ask)
        self.assertTrue(FakeComponent.check(self.engine.orderbook, {-1: [], 1: []}))
        self.assertTrue(self.fake_listener.component.check_for_calls([('on_queue_success',
                                                             (order_bid2,),
                                                             {}),
                                                            ('on_trade_success',
                                                             (
                                                                 order_ask2,
                                                                 order_bid3,
                                                                 100,
                                                                 1),
                                                             {})]))

    def test_no_trade(self):
        order_bid = self.create_order(1, 100, -1)
        order_ask = self.create_order(1, 105, 1)

        self.engine.place_order(order_bid)
        self.engine.place_order(order_ask)
        self.assertTrue(FakeComponent.check(self.engine.orderbook, {-1: [order_bid], 1: [order_ask]}))
        self.assertTrue(self.fake_listener.component.check_for_calls([('on_queue_success',
                                                             (order_bid,),
                                                             {}),
                                                            ('on_queue_success',
                                                             (order_ask,),
                                                             {})]))

    def test_trade_different_size(self):
        order_bid = self.create_order(2, 100, -1)
        order_bid2 = self.create_order(2, 100, -1)
        order_bid3 = self.create_order(2, 100, -1)
        order_bid3.quantity_left = 1
        order_ask = self.create_order(1, 100, 1)
        order_ask2 = self.create_order(1, 100, 1)
        order_ask2.quantity_left = 0

        self.engine.place_order(order_bid)
        self.engine.place_order(order_ask)
        self.assertTrue(self.fake_listener.component.check_for_calls([('on_queue_success',
                                                             (order_bid2,),
                                                             {}),
                                                            ('on_trade_success',
                                                             (order_ask2,
                                                              order_bid3,
                                                              100,
                                                              1),
                                                             {})]
        ))


class TestNotifier(TestEngine):
    def setUp(self):
        TestEngine.setUp(self)

        from sputnik import engine2, models

        self.contract = models.Contract("FOO")

        self.order = engine2.Order(id=1, contract=self.contract.ticker, quantity=10,
                                   price=13, side='BUY', username='aggressive')
        self.passive_order = engine2.Order(id=2, contract=self.contract.ticker, quantity=10,
                                           price=10, side='SELL', username='passive')


class TestAccountantNotifier(TestNotifier):
    def setUp(self):
        TestNotifier.setUp(self)
        from sputnik import engine2
        from sputnik import accountant

        self.accountant = accountant.EngineExport(FakeComponent("accountant"))
        self.accountant_notifier = engine2.AccountantNotifier(self.engine, self.accountant, self.contract)

    def test_on_trade_success(self):
        self.accountant_notifier.on_trade_success(self.order, self.passive_order, 10, 10)
        self.assertTrue(self.accountant.component.check_for_calls([('post_transaction',
                                                          (u'aggressive',
                                                           {'aggressive': True,
                                                            'contract': self.contract.ticker,
                                                            'order': 1,
                                                            'price': 10,
                                                            'quantity': 10,
                                                            'side': u'BUY',
                                                            'username': u'aggressive'},),
                                                          {}),
                                                         ('post_transaction',
                                                          (u'passive',
                                                           {'aggressive': False,
                                                            'contract': self.contract.ticker,
                                                            'order': 2,
                                                            'price': 10,
                                                            'quantity': 10,
                                                            'side': u'SELL',
                                                            'username': u'passive'},),
                                                          {})]))


class TestWebserverNotifier(TestNotifier):
    def setUp(self):
        TestNotifier.setUp(self)
        from sputnik import engine2

        self.webserver = FakeComponent()
        self.webserver_notifier = engine2.WebserverNotifier(self.engine, self.webserver, self.contract)

    def test_on_queue_success(self):
        self.webserver_notifier.on_queue_success(self.order)
        self.assertTrue(self.webserver.component.check_for_calls([('order',
                                                         ('aggressive',
                                                          {'contract': self.contract.ticker,
                                                           'id': 1,
                                                           'is_cancelled': False,
                                                           'price': 13,
                                                           'quantity': 10,
                                                           'quantity_left': 10,
                                                           'side': 'SELL',
                                                          }),
                                                         {}),
                                                        ('book', ('FOO', {'asks': [], 'bids': [], 'contract': 'FOO'}),
                                                         {})]))

    def test_on_cancel_success(self):
        pass

    def test_update_book(self):
        pass


class TestSafePriceNotifier(TestNotifier):
    pass

