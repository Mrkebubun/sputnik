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

        self.administrator_export = engine2.AdministratorExport(self.engine)

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

    def test_trade_aggressive_smaller(self):
        order_bid = self.create_order(2, 100, -1)
        order_bid2 = self.create_order(2, 100, -1)
        order_bid3 = self.create_order(2, 100, -1)
        order_bid3.quantity_left = 1
        order_ask = self.create_order(1, 100, 1)
        order_ask2 = self.create_order(1, 100, 1)
        order_ask3 = self.create_order(1, 100, 1)
        order_ask3.quantity_left = 0

        self.engine.place_order(order_ask)
        self.engine.place_order(order_bid)
        self.assertTrue(self.fake_listener.component.check_for_calls([('on_queue_success',
                                                                       (order_ask2,),
                                                                       {}),
                                                                      ('on_trade_success',
                                                                       (order_bid3,
                                                                        order_ask3,
                                                                        100,
                                                                        1),
                                                                       {}),
                                                                      ('on_queue_success',
                                                                       (order_bid3,),
                                                                       {})]))


    def test_price_priority(self):
        order_bid = self.create_order(1, 100, -1)
        order_bid_copy = self.create_order(1, 100, -1)
        self.engine.place_order(order_bid)
        order_bid2 = self.create_order(1, 101, -1)
        order_bid2_copy = self.create_order(1, 101, -1)
        order_bid2_zero = self.create_order(1, 101, -1)
        order_bid2_zero.quantity_left = 0
        self.engine.place_order(order_bid2)

        # Should trade vs the 101 order
        order_ask = self.create_order(1, 99, 1)
        order_ask_zero = self.create_order(1, 99, 1)
        order_ask_zero.quantity_left = 0
        self.engine.place_order(order_ask)
        self.assertTrue(self.fake_listener.component.check_for_calls([('on_queue_success',
                                                                       (order_bid_copy,),
                                                                       {}),
                                                                      ('on_queue_success',
                                                                       (order_bid2_copy,),
                                                                       {}),
                                                                      ('on_trade_success',
                                                                       (order_ask_zero,
                                                                        order_bid2_zero,
                                                                        101,
                                                                        1),
                                                                       {})]))


    def test_cancel_order(self):
        order_bid = self.create_order(2, 100, -1)
        self.engine.place_order(order_bid)
        self.assertTrue(self.engine.cancel_order(order_bid.id))
        self.assertTrue(self.fake_listener.component.check_for_calls(
            [('on_queue_success',
              (order_bid,),
              {}),
             ('on_cancel_success',
              (order_bid,),
              {})]))


class TestAdministratorExport(TestEngine):
    def test_get_order_book(self):
        order_bid = self.create_order(1, 100, -1)
        order_ask = self.create_order(1, 105, 1)

        self.engine.place_order(order_bid)
        self.engine.place_order(order_ask)

        order_book = self.administrator_export.get_order_book()
        self.assertTrue(FakeComponent.check(
            {'BUY': {1: {'errors': [],
                         'id': 1,
                         'price': 100,
                         'quantity': 1,
                         'quantity_left': 1,
                         'username': None}},
             'SELL': {2: {'errors': [],
                          'id': 2,
                          'price': 105,
                          'quantity': 1,
                          'quantity_left': 1,
                          'username': None}}}, order_book))


class TestNotifier(TestEngine):
    def setUp(self):
        TestEngine.setUp(self)

        from sputnik import engine2, models

        self.contract = models.Contract("FOO")

        self.order = engine2.Order(id=1, contract=self.contract.ticker, quantity=10,
                                   price=13, side=-1, username='aggressive')
        self.passive_order = engine2.Order(id=2, contract=self.contract.ticker, quantity=10,
                                           price=10, side=1, username='passive')
        self.small_order = engine2.Order(id=3, contract=self.contract.ticker, quantity=5,
                                         price=13, side=-1, username='aggressive')


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
                                                                      'other_order': 2,
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
                                                                      'other_order': 1,
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
        self.assertTrue(self.webserver.component.check_for_calls([
            ('book', ('FOO', {'asks': [], 'bids': [{'price': 13, 'quantity': 10}], 'contract': 'FOO'}),
             {})]))

    def test_on_cancel_success(self):
        self.webserver_notifier.on_queue_success(self.order)
        self.webserver_notifier.on_cancel_success(self.order)

        self.assertTrue(self.webserver.component.check_for_calls([('book',
                                                                   ('FOO',
                                                                    {'asks': [],
                                                                     'bids': [{'price': 13, 'quantity': 10}],
                                                                     'contract': 'FOO'}),
                                                                   {}),
                                                                  ('book',
                                                                   ('FOO', {'asks': [], 'bids': [], 'contract': 'FOO'}),
                                                                   {})]
        ))

    def test_on_cancel_success_not_all(self):
        self.webserver_notifier.on_queue_success(self.order)
        self.webserver_notifier.on_queue_success(self.order)

        self.webserver_notifier.on_cancel_success(self.order)
        self.assertTrue(self.webserver.component.check_for_calls([('book',
                                                                   ('FOO',
                                                                    {'asks': [],
                                                                     'bids': [{'price': 13, 'quantity': 10}],
                                                                     'contract': 'FOO'}),
                                                                   {}),
                                                                  ('book',
                                                                   ('FOO',
                                                                    {'asks': [],
                                                                     'bids': [{'price': 13, 'quantity': 20}],
                                                                     'contract': 'FOO'}),
                                                                   {}),
                                                                  ('book',
                                                                   ('FOO',
                                                                    {'asks': [],
                                                                     'bids': [{'price': 13, 'quantity': 10}],
                                                                     'contract': 'FOO'}),
                                                                   {}),
        ]))

    def test_on_trade_success(self):
        self.webserver_notifier.on_queue_success(self.passive_order)
        self.webserver_notifier.on_trade_success(self.order, self.passive_order, 13, 5)
        self.assertTrue(self.webserver.component.check_for_calls([('book',
                                                                   ('FOO',
                                                                    {'asks': [],
                                                                     'bids': [{'price': 13, 'quantity': 10}],
                                                                     'contract': 'FOO'}),
                                                                   {}),
                                                                  ('book',
                                                                   ('FOO',
                                                                    {'asks': [],
                                                                     'bids': [{'price': 13, 'quantity': 5}],
                                                                     'contract': 'FOO'}),
                                                                   {}),
        ]))

    def test_on_trade_success_aggressive_smaller(self):
        order_bid = self.create_order(1, 100, -1)
        order_ask = self.create_order(2, 100, 1)
        self.webserver_notifier.on_queue_success(order_bid)
        self.webserver_notifier.on_trade_success(order_ask, order_bid, 100, 1)
        order_ask.quantity_left = 1
        self.webserver_notifier.on_queue_success(order_ask)
        self.assertTrue(self.webserver.component.check_for_calls([('book',
                                                                   ('FOO',
                                                                    {'asks': [],
                                                                     'bids': [{'price': 100, 'quantity': 1}],
                                                                     'contract': 'FOO'}),
                                                                   {}),
                                                                  ('book',
                                                                   ('FOO', {'asks': [], 'bids': [], 'contract': 'FOO'}),
                                                                   {}),
                                                                  ('book',
                                                                   ('FOO',
                                                                    {'asks': [{'price': 100, 'quantity': 1}],
                                                                     'bids': [], 'contract': 'FOO'}),
                                                                   {})]
        ))


class TestSafePriceNotifier(TestNotifier):
    pass

