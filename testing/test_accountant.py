import sys
import os
from test_sputnik import TestSputnik, FakeComponent
from twisted.internet import defer
from pprint import pprint

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../tools"))

accountant_init = """
permissions add Deposit deposit login
permissions add Trade trade login
permissions add Withdraw withdraw login
"""


class FakeEngine(FakeComponent):
    name = "engine"

    def place_order(self, order):
        self._log_call('place_order', order)
        # Always return a good fake result
        return defer.succeed(order.id)

    def cancel_order(self, id):
        self._log_call('cancel_order', id)
        # Always return success, with None
        return defer.succeed(None)


class FakeLedger(FakeComponent):
    name = "ledger"

    def post(self, *postings):
        self._log_call('post', *postings)
        return defer.succeed(None)


class TestAccountant(TestSputnik):
    def setUp(self):
        TestSputnik.setUp(self)
        self.run_leo(accountant_init)

        from sputnik import accountant
        from sputnik import ledger
        from sputnik import cashier
        from sputnik import engine2

        self.engines = {"BTC/MXN": engine2.AccountantExport(FakeEngine()),
                        "NETS2014": engine2.AccountantExport(FakeEngine())}
        self.webserver = FakeComponent("webserver")
        self.cashier = cashier.AccountantExport(FakeComponent("cashier"))
        self.ledger = ledger.AccountantExport(ledger.Ledger(self.session, 5000))
        self.alerts_proxy = FakeComponent("alerts")
        self.accountant_proxy = accountant.AccountantExport(FakeComponent("accountant"))
        self.accountant = accountant.Accountant(self.session, self.engines,
                                                self.cashier,
                                                self.ledger,
                                                self.webserver,
                                                self.accountant_proxy,
                                                self.alerts_proxy,
                                                debug=True,
                                                trial_period=False)
        #self.accountant_proxy = self.accountant.accountant_proxy = self.accountant
        self.cashier_export = accountant.CashierExport(self.accountant)
        self.administrator_export = accountant.AdministratorExport(self.accountant)
        self.webserver_export = accountant.WebserverExport(self.accountant)
        self.engine_export = accountant.EngineExport(self.accountant)


    def set_permissions_group(self, username, groupname):
        from sputnik import models

        user = self.session.query(models.User).filter_by(username=username).one()
        group = self.session.query(models.PermissionGroup).filter_by(name=groupname).one()
        user.permissions = group
        self.session.merge(user)
        self.session.commit()


class TestCashierExport(TestAccountant):
    def test_deposit_cash_permission_allowed(self):
        from sputnik import models

        self.create_account('test', '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('test', 'Deposit')

        d = self.cashier_export.deposit_cash("test", "18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv", 10)

        def onSuccess(result):
            position = self.session.query(models.Position).filter_by(
                username="test").one()
            self.assertEqual(position.position, 10)
            self.assertTrue(self.webserver.component.check_for_calls([('transaction',
                                                                       (u'onlinecash',
                                                                        {'contract': u'BTC',
                                                                         'quantity': 10,
                                                                         'direction': 'debit',
                                                                         'type': u'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       (u'test',
                                                                        {'contract': u'BTC',
                                                                         'quantity': 10,
                                                                         'direction': 'credit',
                                                                         'type': u'Deposit'}),
                                                                       {})]))

        d.addCallback(onSuccess)
        return d

    def test_deposit_cash_too_much(self):
        from sputnik import models

        self.create_account('test', '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('test', 'Deposit')

        # Set a deposit limit
        self.accountant.deposit_limits['BTC'] = 100000000

        d = self.cashier_export.deposit_cash("test", "18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv", 1000000000)

        def onSuccess(result):
            position = self.session.query(models.Position).filter_by(
                username="test").one()

            self.assertEqual(position.position, self.accountant.deposit_limits['BTC'])

            # Make sure the overflow position gets the cash
            overflow_position = self.session.query(models.Position).filter_by(
                username="depositoverflow").one()
            self.assertEqual(overflow_position.position, 1000000000 - self.accountant.deposit_limits['BTC'])
            self.assertTrue(self.webserver.component.check_for_calls([('transaction',
                                                                       ('onlinecash',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'debit',
                                                                         'quantity': 1000000000,
                                                                         'type': 'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       (u'test',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'credit',
                                                                         'quantity': 1000000000,
                                                                         'type': 'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       (u'test',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'debit',
                                                                         'quantity': 900000000,
                                                                         'type': 'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       ('depositoverflow',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'credit',
                                                                         'quantity': 900000000,
                                                                         'type': 'Deposit'}),
                                                                       {})]))

        d.addCallback(onSuccess)
        return d

    def test_deposit_cash_permission_denied(self):
        from sputnik import models

        self.create_account('test', '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.session.commit()

        d = self.cashier_export.deposit_cash("test", "18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv", 10)

        def onSuccess(result):
            # Make sure the position didn't get updated
            position = self.session.query(models.Position).filter_by(
                username="test").one()
            self.assertEqual(position.position, 0)

            # Make sure the overflow position gets the cash
            overflow_position = self.session.query(models.Position).filter_by(
                username="depositoverflow").one()
            self.assertEqual(overflow_position.position, 10)
            self.assertTrue(self.webserver.component.check_for_calls([('transaction',
                                                                       ('onlinecash',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'debit',
                                                                         'quantity': 10,
                                                                         'type': 'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       (u'test',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'credit',
                                                                         'quantity': 10,
                                                                         'type': 'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       (u'test',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'debit',
                                                                         'quantity': 10,
                                                                         'type': 'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       ('depositoverflow',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'credit',
                                                                         'quantity': 10,
                                                                         'type': 'Deposit'}),
                                                                       {})]
            ))

        d.addCallback(onSuccess)
        return d

    def test_transfer_position(self):
        from sputnik import models

        self.create_account("from_account", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.create_account("to_account", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('from_account', 'Deposit')
        self.set_permissions_group('to_account', 'Deposit')
        self.cashier_export.deposit_cash("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 10)
        self.cashier_export.deposit_cash("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 10)

        from sputnik import util

        uid = util.get_uid()
        d1 = self.administrator_export.transfer_position('from_account', 'BTC', 'debit', 5, 'note', uid)
        d2 = self.administrator_export.transfer_position('to_account', 'BTC', 'credit', 5, None, uid)
        d = defer.DeferredList([d1, d2])

        def onSuccess(result):
            from_position = self.session.query(models.Position).filter_by(username='from_account').one()
            to_position = self.session.query(models.Position).filter_by(username='to_account').one()

            self.assertEqual(from_position.position, 5)
            self.assertEqual(to_position.position, 15)
            self.assertTrue(self.webserver.component.check_for_calls([('transaction',
                                                                       ('onlinecash',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'debit',
                                                                         'quantity': 10,
                                                                         'type': 'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       (u'from_account',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'credit',
                                                                         'quantity': 10,
                                                                         'type': 'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       ('onlinecash',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'debit',
                                                                         'quantity': 10,
                                                                         'type': 'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       (u'to_account',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'credit',
                                                                         'quantity': 10,
                                                                         'type': 'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       ('from_account',
                                                                        {'contract': 'BTC',
                                                                         'direction': 'debit',
                                                                         'quantity': 5,
                                                                         'type': 'Transfer'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       ('to_account',
                                                                        {'contract': 'BTC',
                                                                         'direction': 'credit',
                                                                         'quantity': 5,
                                                                         'type': 'Transfer'}),
                                                                       {})]
            ))

        d.addCallback(onSuccess)
        return d

    def test_get_position(self):
        self.create_account('test', '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('test', 'Deposit')

        self.cashier_export.deposit_cash("test", "18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv", 10)
        position = self.cashier_export.get_position('test', 'BTC')
        self.assertEqual(position, 10)


class TestAdministratorExport(TestAccountant):
    def test_transfer_position(self):
        from sputnik import models

        self.create_account("from_account", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.create_account("to_account", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('from_account', 'Deposit')
        self.set_permissions_group('to_account', 'Deposit')
        self.cashier_export.deposit_cash("from_account", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 10)
        self.cashier_export.deposit_cash("to_account", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 10)

        from sputnik import util

        uid = util.get_uid()
        d1 = self.administrator_export.transfer_position('from_account', 'BTC', 'debit', 5, 'note', uid)
        d2 = self.administrator_export.transfer_position('to_account', 'BTC', 'credit', 5, None, uid)
        d = defer.DeferredList([d1, d2])

        def onSuccess(result):
            from_position = self.session.query(models.Position).filter_by(username='from_account').one()
            to_position = self.session.query(models.Position).filter_by(username='to_account').one()

            self.assertEqual(from_position.position, 5)
            self.assertEqual(to_position.position, 15)
            self.assertTrue(self.webserver.component.check_for_calls([('transaction',
                                                                       ('onlinecash',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'debit',
                                                                         'quantity': 10,
                                                                         'type': 'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       (u'from_account',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'credit',
                                                                         'quantity': 10,
                                                                         'type': 'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       ('onlinecash',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'debit',
                                                                         'quantity': 10,
                                                                         'type': 'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       (u'to_account',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'credit',
                                                                         'quantity': 10,
                                                                         'type': 'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       ('from_account',
                                                                        {'contract': 'BTC',
                                                                         'direction': 'debit',
                                                                         'quantity': 5,
                                                                         'type': 'Transfer'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       ('to_account',
                                                                        {'contract': 'BTC',
                                                                         'direction': 'credit',
                                                                         'quantity': 5,
                                                                         'type': 'Transfer'}),
                                                                       {})]
            ))


        d.addCallback(onSuccess)
        return d

    def test_adjust_position(self):
        from sputnik import models

        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('test', 'Deposit')
        self.cashier_export.deposit_cash('test', '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 10)

        d = self.administrator_export.adjust_position('test', 'BTC', 10)

        def onSuccess(result):
            position = self.session.query(models.Position).filter_by(
                username="test").one()
            self.assertEqual(position.position, 20)
            self.assertTrue(self.webserver.component.check_for_calls([('transaction',
                                                                       ('onlinecash',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'debit',
                                                                         'quantity': 10,
                                                                         'type': 'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       (u'test',
                                                                        {'contract': u'BTC',
                                                                         'direction': 'credit',
                                                                         'quantity': 10,
                                                                         'type': 'Deposit'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       ('test',
                                                                        {'contract': 'BTC',
                                                                         'direction': 'credit',
                                                                         'quantity': 10,
                                                                         'type': 'Transfer'}),
                                                                       {}),
                                                                      ('transaction',
                                                                       ('adjustments',
                                                                        {'contract': 'BTC',
                                                                         'direction': 'debit',
                                                                         'quantity': 10,
                                                                         'type': 'Transfer'}),
                                                                       {})]))

        d.addCallback(onSuccess)
        return d

    def test_change_permission_group(self):
        from sputnik import models

        self.create_account("test")
        id = self.session.query(models.PermissionGroup.id).filter_by(name='Deposit').one().id
        self.administrator_export.change_permission_group('test', id)
        user = self.session.query(models.User).filter_by(username='test').one()
        self.assertEqual(user.permission_group_id, id)


class TestEngineExport(TestAccountant):
    def test_post_transaction(self):
        from sputnik import util, models
        import datetime

        self.create_account("aggressive_user", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.create_account("passive_user", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("aggressive_user", 'Deposit')
        self.set_permissions_group("passive_user", "Deposit")
        self.cashier_export.deposit_cash('aggressive_user', '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash('passive_user', '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 3000000)

        self.add_address('aggressive_user', 'MXN_address', 'MXN')
        self.add_address('passive_user', 'BTC_address', 'BTC')

        self.cashier_export.deposit_cash('aggressive_user', 'MXN_address', 500000)
        self.cashier_export.deposit_cash('passive_user', 'BTC_address', 400000000)

        self.set_permissions_group("aggressive_user", 'Trade')
        self.set_permissions_group("passive_user", "Trade")

        passive_deferred = self.webserver_export.place_order('passive_user', {'username': 'passive_user',
                                                                              'contract': 'BTC/MXN',
                                                                              'price': 60000000,
                                                                              'quantity': 3000000,
                                                                              'side': 'BUY',
                                                                              'timestamp': util.dt_to_timestamp(
                                                                                  datetime.datetime.utcnow())})

        aggressive_deferred = self.webserver_export.place_order('aggressive_user', {'username': 'aggressive_user',
                                                                                    'contract': 'BTC/MXN',
                                                                                    'price': 60000000,
                                                                                    'quantity': 3000000,
                                                                                    'side': 'SELL',
                                                                                    'timestamp': util.dt_to_timestamp(
                                                                                        datetime.datetime.utcnow())})

        def onSuccessPlaceOrder(result):
            (dummy, passive_order), (dummy, aggressive_order) = result
            uid = util.get_uid()
            timestamp = util.dt_to_timestamp(datetime.datetime.utcnow())
            aggressive = {'username': 'aggressive_user',
                          'aggressive': True,
                          'contract': 'BTC/MXN',
                          'price': 60000000,
                          'quantity': 3000000,
                          'order': aggressive_order,
                          'other_order': passive_order,
                          'side': 'SELL',
                          'uid': uid,
                          'timestamp': timestamp}

            passive = {'username': 'passive_user',
                       'aggressive': False,
                       'contract': 'BTC/MXN',
                       'price': 60000000,
                       'quantity': 3000000,
                       'order': passive_order,
                       'other_order': aggressive_order,
                       'side': 'BUY',
                       'uid': uid,
                       'timestamp': timestamp}

            d1 = self.engine_export.post_transaction('aggressive_user', aggressive)
            d2 = self.engine_export.post_transaction('passive_user', passive)

            def onSuccess(result):
                # Inspect the positions
                BTC = self.session.query(models.Contract).filter_by(ticker='BTC').one()
                MXN = self.session.query(models.Contract).filter_by(ticker='MXN').one()
                aggressive_user_btc_position = self.session.query(models.Position).filter_by(username='aggressive_user',
                                                                                             contract=BTC).one()
                passive_user_btc_position = self.session.query(models.Position).filter_by(username='passive_user',
                                                                                          contract=BTC).one()
                aggressive_user_mxn_position = self.session.query(models.Position).filter_by(username='aggressive_user',
                                                                                             contract=MXN).one()
                passive_user_mxn_position = self.session.query(models.Position).filter_by(username='passive_user',
                                                                                          contract=MXN).one()

                # This is based on all BTC fees being zero
                self.assertEqual(aggressive_user_btc_position.position, 2000000)
                self.assertEqual(passive_user_btc_position.position, 400000000 + 3000000)

                # This is based on 40bps MXN fee, only charged to the aggressive_user
                self.assertEqual(aggressive_user_mxn_position.position, 1792800 + 500000)
                self.assertEqual(passive_user_mxn_position.position, 1200000)

            dl = defer.DeferredList([d1, d2])
            dl.addCallback(onSuccess)
            return dl

        dl = defer.DeferredList([aggressive_deferred, passive_deferred])
        dl.addCallback(onSuccessPlaceOrder)
        return dl
    """
    # Not implemented yet
    def test_safe_prices(self):
        self.engine_export.safe_prices('BTC', 42)
        self.assertEqual(self.accountant.safe_prices['BTC'], 42)
    """


class TestWebserverExport(TestAccountant):
    def test_place_order(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash('test', '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash('test', '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group("test", 'Trade')

        from sputnik import util
        import datetime
        # Place a sell order, we have enough cash
        d = self.webserver_export.place_order('test', {'username': 'test',
                                                       'contract': 'BTC/MXN',
                                                       'price': 1000000,
                                                       'quantity': 3000000,
                                                       'side': 'SELL',
                                                       'timestamp': util.dt_to_timestamp(datetime.datetime.utcnow())})

        def onFail(failure):
            self.assertFalse(True)

        def onSuccess(id):
            from sputnik import models

            order = self.session.query(models.Order).filter_by(id=id).one()
            self.assertEqual(order.username, 'test')
            self.assertEqual(order.contract.ticker, 'BTC/MXN')
            self.assertEqual(order.price, 1000000)
            self.assertEqual(order.quantity, 3000000)
            self.assertEqual(order.side, 'SELL')
            from sputnik import engine2
            self.assertTrue(self.engines['BTC/MXN'].component.check_for_calls([('place_order',
                                                                                (engine2.Order(**{'contract': 5,
                                                                                  'id': 1,
                                                                                  'price': 1000000,
                                                                                  'quantity': 3000000,
                                                                                  'side': 1,
                                                                                  'username': u'test'}),),
                                                                                {})]))

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_place_order_prediction_buy(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group("test", 'Trade')

        # Place a buy order, we have enough cash
        from sputnik import util
        import datetime

        d = self.webserver_export.place_order('test', {'username': 'test',
                                                       'contract': 'NETS2014',
                                                       'price': 500,
                                                       'quantity': 3,
                                                       'side': 'BUY',
                                                       'timestamp': util.dt_to_timestamp(datetime.datetime.utcnow())})

        def onSuccess(id):
            from sputnik import models

            order = self.session.query(models.Order).filter_by(id=id).one()
            self.assertEqual(order.username, 'test')
            self.assertEqual(order.contract.ticker, 'NETS2014')
            self.assertEqual(order.price, 500)
            self.assertEqual(order.quantity, 3)
            self.assertEqual(order.side, 'BUY')
            from sputnik import engine2
            self.assertTrue(self.engines['NETS2014'].component.check_for_calls([('place_order',
                                                                                 (engine2.Order(**{'contract': 8,
                                                                                   'id': 1,
                                                                                   'price': 500,
                                                                                   'quantity': 3,
                                                                                   'side': -1,
                                                                                   'username': u'test'}),),
                                                                                 {})]))

            # Check to make sure margin is right
            from sputnik import margin

            [low_margin, high_margin] = margin.calculate_margin('test', self.session)
            self.assertEqual(low_margin, 1500000)
            self.assertEqual(high_margin, 1500000)

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_place_order_prediction_sell(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group("test", 'Trade')

        # Place a buy order, we have enough cash
        from sputnik import util
        import datetime

        d = self.webserver_export.place_order('test', {'username': 'test',
                                                       'contract': 'NETS2014',
                                                       'price': 100,
                                                       'quantity': 3,
                                                       'side': 'SELL',
                                                       'timestamp': util.dt_to_timestamp(datetime.datetime.utcnow())})

        def onSuccess(id):
            from sputnik import models

            order = self.session.query(models.Order).filter_by(id=id).one()
            self.assertEqual(order.username, 'test')
            self.assertEqual(order.contract.ticker, 'NETS2014')
            self.assertEqual(order.price, 100)
            self.assertEqual(order.quantity, 3)
            self.assertEqual(order.side, 'SELL')

            from sputnik import engine2
            self.assertTrue(self.engines['NETS2014'].component.check_for_calls([('place_order',
                                                                                 (engine2.Order(**{'contract': 8,
                                                                                   'id': 1,
                                                                                   'price': 100,
                                                                                   'quantity': 3,
                                                                                   'side': 1,
                                                                                   'username': u'test'}),),
                                                                                 {})]))

            # Check to make sure margin is right
            from sputnik import margin

            [low_margin, high_margin] = margin.calculate_margin('test', self.session)
            self.assertEqual(low_margin, 2700000)
            self.assertEqual(high_margin, 2700000)

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_place_order_bad_audit(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)

        # Mess with a position
        from sputnik import models
        btc_contract = self.session.query(models.Contract).filter_by(ticker='BTC').one()
        btc_position = self.session.query(models.Position).filter_by(username='test', contract=btc_contract).one()
        btc_position.position = 10000000
        self.session.add(btc_position)
        self.session.commit()

        self.set_permissions_group("test", 'Trade')
        # Place a sell order, we have enough cash
        from sputnik import accountant
        from sputnik import util
        import datetime

        with self.assertRaisesRegexp(accountant.AccountantException, 'Audit failure'):
            self.webserver_export.place_order('test', {'username': 'test',
                                                       'contract': 'BTC/MXN',
                                                       'price': 1000000,
                                                       'quantity': 3000000,
                                                       'side': 'SELL',
                                                       'timestamp': util.dt_to_timestamp(datetime.datetime.utcnow())})

    def test_place_order_no_perms(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)

        # Place a sell order, we have enough cash
        from sputnik import accountant
        from sputnik import util
        import datetime

        with self.assertRaisesRegexp(accountant.AccountantException, 'Trading not permitted'):
            self.webserver_export.place_order('test', {'username': 'test',
                                                       'contract': 'BTC/MXN',
                                                       'price': 1000000,
                                                       'quantity': 3000000,
                                                       'side': 'SELL',
                                                       'timestamp': util.dt_to_timestamp(datetime.datetime.utcnow())})


    def test_place_order_no_cash(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group("test", 'Trade')

        # Place a sell order, we have no cash
        from sputnik import accountant
        from sputnik import util
        import datetime

        with self.assertRaisesRegexp(accountant.AccountantException, 'Insufficient margin'):
            self.webserver_export.place_order('test', {'username': 'test',
                                                       'contract': 'BTC/MXN',
                                                       'price': 1000000,
                                                       'quantity': 3000000,
                                                       'side': 'SELL',
                                                       'timestamp': util.dt_to_timestamp(datetime.datetime.utcnow())})

    def test_place_order_little_cash(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group("test", 'Trade')


        # Place a sell order, we have too little cash
        from sputnik import accountant
        from sputnik import util
        import datetime

        with self.assertRaisesRegexp(accountant.AccountantException, 'Insufficient margin'):
            result = self.webserver_export.place_order('test', {'username': 'test',
                                                                'contract': 'BTC/MXN',
                                                                'price': 1000000,
                                                                'quantity': 9000000,
                                                                'side': 'SELL',
                                                                'timestamp': util.dt_to_timestamp(
                                                                    datetime.datetime.utcnow())})


    def test_place_many_orders(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group("test", 'Trade')

        # Place a sell order, we have enough cash
        from sputnik import util
        import datetime

        d = self.webserver_export.place_order('test', {'username': 'test',
                                                       'contract': 'BTC/MXN',
                                                       'price': 1000000,
                                                       'quantity': 3000000,
                                                       'side': 'SELL',
                                                       'timestamp': util.dt_to_timestamp(datetime.datetime.utcnow())})


        def onFail():
            self.assertFalse(True)

        def onSuccess(id):
            from sputnik import models

            order = self.session.query(models.Order).filter_by(id=id).one()
            self.assertEqual(order.username, 'test')
            self.assertEqual(order.contract.ticker, 'BTC/MXN')
            self.assertEqual(order.price, 1000000)
            self.assertEqual(order.quantity, 3000000)
            self.assertEqual(order.side, 'SELL')
            from sputnik import engine2
            self.assertTrue(self.engines['BTC/MXN'].component.check_for_calls([('place_order',
                                                                                (engine2.Order(**{'contract': 5,
                                                                                  'id': 1,
                                                                                  'price': 1000000,
                                                                                  'quantity': 3000000,
                                                                                  'side': 1,
                                                                                  'username': u'test'}),),
                                                                                {})]))

            # Place another sell, we have insufficient cash now
            from sputnik import accountant
            from sputnik import util
            import datetime

            with self.assertRaisesRegexp(accountant.AccountantException, 'Insufficient margin'):
                self.webserver_export.place_order('test', {'username': 'test',
                                                           'contract': 'BTC/MXN',
                                                           'price': 1000000,
                                                           'quantity': 3000000,
                                                           'side': 'SELL',
                                                           'timestamp': util.dt_to_timestamp(
                                                               datetime.datetime.utcnow())})

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_cancel_order_success(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group("test", 'Trade')

        # Place a sell order, we have enough cash
        from sputnik import util
        import datetime

        d = self.webserver_export.place_order('test', {'username': 'test',
                                                       'contract': 'BTC/MXN',
                                                       'price': 1000000,
                                                       'quantity': 3000000,
                                                       'side': 'SELL',
                                                       'timestamp': util.dt_to_timestamp(datetime.datetime.utcnow())})

        def onFail(failure):
            self.assertFalse(True)

        def onSuccess(id):
            def cancelSuccess(result):
                self.assertEquals(result, None)

            def cancelFail(failure):
                self.assertTrue(False)

            d = self.webserver_export.cancel_order('test', id)
            d.addCallbacks(cancelSuccess, cancelFail)
            return d


        d.addCallbacks(onSuccess, onFail)
        return d

    def test_cancel_order_wrong_user(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group("test", 'Trade')

        # Place a sell order, we have enough cash
        from sputnik import util
        import datetime

        d = self.webserver_export.place_order('test', {'username': 'test',
                                                       'contract': 'BTC/MXN',
                                                       'price': 1000000,
                                                       'quantity': 3000000,
                                                       'side': 'SELL',
                                                       'timestamp': util.dt_to_timestamp(datetime.datetime.utcnow())})

        def onFail(failure):
            self.assertFalse(True)

        def onSuccess(id):
            def cancelSuccess(result):
                self.assertTrue(False)

            def cancelFail(failure):
                self.assertTrue(False)

            from sputnik import accountant

            with self.assertRaisesRegexp(accountant.AccountantException, "User wrong does not own the order"):
                d = self.webserver_export.cancel_order('wrong', id)
                d.addCallbacks(cancelSuccess, cancelFail)
                return d


        d.addCallbacks(onSuccess, onFail)
        return d

    def test_cancel_order_no_order(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group("test", 'Trade')

        def cancelSuccess(result):
            self.assertTrue(False)

        def cancelFail(failure):
            self.assertTrue(False)

        from sputnik import accountant

        id = 5
        with self.assertRaisesRegexp(accountant.AccountantException, "No order 5 found"):
            d = self.webserver_export.cancel_order('wrong', id)
            d.addCallbacks(cancelSuccess, cancelFail)
            return d

    def test_request_withdrawal_success(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('test', 'Deposit')
        self.cashier_export.deposit_cash('test', '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group('test', 'Withdraw')
        result = self.webserver_export.request_withdrawal('test', 'BTC', 3000000, 'bad_address')

        # Make sure it returns success
        self.assertTrue(self.successResultOf(result))

        # Check that the positions are changed
        from sputnik import models

        user_position = self.session.query(models.Position).filter_by(username='test').one()
        pending_position = self.session.query(models.Position).filter_by(username='pendingwithdrawal').one()

        self.assertEqual(user_position.position, 2000000)
        self.assertEqual(pending_position.position, 3000000)

        self.assertTrue(self.webserver.component.check_for_calls([('transaction',
                                                                   (u'onlinecash',
                                                                    {'contract': u'BTC',
                                                                     'quantity': 5000000,
                                                                     'direction': 'debit',
                                                                     'type': u'Deposit'}),
                                                                   {}),
                                                                  ('transaction',
                                                                   (u'test',
                                                                    {'contract': u'BTC',
                                                                     'direction': 'credit',
                                                                     'quantity': 5000000,
                                                                     'type': u'Deposit'}),
                                                                   {}),
                                                                  ('transaction',
                                                                   (u'pendingwithdrawal',
                                                                    {'contract': u'BTC',
                                                                     'direction': 'credit',
                                                                     'quantity': 3000000,
                                                                     'type': u'Withdrawal'}),
                                                                   {}),
                                                                  ('transaction',
                                                                   (u'test',
                                                                    {'contract': u'BTC',
                                                                     'direction': 'debit',
                                                                     'quantity': 3000000,
                                                                     'type': u'Withdrawal'}),
                                                                   {})]))
        self.assertTrue(
            self.cashier.component.check_for_calls(
                [('request_withdrawal', ('test', 'BTC', 'bad_address', 3000000), {})]))


    def test_request_withdrawal_no_perms(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')

        from sputnik import accountant

        with self.assertRaisesRegexp(accountant.AccountantException, 'Withdrawals not permitted'):
            self.webserver_export.request_withdrawal('test', 'BTC', 3000000, 'bad_address')

        self.assertEqual(self.cashier.component.log, [])

    def test_request_withdrawal_no_margin_btc(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('test', 'Deposit')
        self.cashier_export.deposit_cash('test', '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group('test', 'Withdraw')

        from sputnik import accountant

        with self.assertRaisesRegexp(accountant.AccountantException, 'Insufficient margin'):
            self.webserver_export.request_withdrawal('test', 'BTC', 8000000, 'bad_address')

        self.assertEqual(self.cashier.component.log, [])

    def test_request_withdrawal_no_margin_fiat(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('test', 'Deposit')
        self.cashier_export.deposit_cash('test', '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group('test', 'Withdraw')

        from sputnik import accountant

        with self.assertRaisesRegexp(accountant.AccountantException, 'Insufficient margin'):
            self.webserver_export.request_withdrawal('test', 'MXN', 8000000, 'bad_address')

        self.assertEqual(self.cashier.component.log, [])


