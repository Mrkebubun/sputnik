import sys
import os
from test_sputnik import TestSputnik, FakeProxy
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


class FakeEngine(FakeProxy):
    def place_order(self, order):
        self.log.append(('place_order', (order), {}))
        # Always return a good fake result
        return defer.succeed(order['id'])

    def cancel_order(self, id):
        self.log.append(('cancel_order', (id), {}))
        # Always return success, with None
        return defer.succeed(None)

class TestAccountant(TestSputnik):
    def setUp(self):
        TestSputnik.setUp(self)
        self.run_leo(accountant_init)

        from sputnik import accountant

        self.engines = {"BTC/MXN": FakeEngine(),
                        "NETS2014": FakeEngine()}
        self.webserver = FakeProxy()
        self.cashier = FakeProxy()
        self.ledger = FakeProxy()
        self.alerts_proxy = FakeProxy()
        self.accountant = accountant.Accountant(self.session, self.engines,
                                                self.cashier,
                                                self.ledger,
                                                self.webserver, 
                                                self.alerts_proxy,
                                                debug=True,
                                                trial_period=False)
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

        self.cashier_export.deposit_cash("18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv", 10)
        position = self.session.query(models.Position).filter_by(
            username="test").one()
        self.assertEqual(position.position, 10)
        self.assertTrue(self.webserver.check_for_calls([('transaction',
                                                         (u'onlinecash',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'test',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {})]))

    def test_deposit_cash_too_much(self):
        from sputnik import models

        self.create_account('test', '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('test', 'Deposit')

        # Set a deposit limit
        self.accountant.deposit_limits['BTC'] = 100000

        self.cashier_export.deposit_cash("18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv", 1000000000)
        position = self.session.query(models.Position).filter_by(
            username="test").one()

        self.assertEqual(position.position, self.accountant.deposit_limits['BTC'])
        self.assertEqual(position.position, position.position_calculated)

        # Make sure the overflow position gets the cash
        overflow_position = self.session.query(models.Position).filter_by(
            username="depositoverflow").one()
        self.assertEqual(overflow_position.position, 1000000000 - self.accountant.deposit_limits['BTC'])
        self.assertEqual(overflow_position.position_calculated, overflow_position.position)
        self.assertTrue(self.webserver.check_for_calls([('transaction',
                                                         (u'onlinecash',
                                                          {'contract': u'BTC',
                                                           'quantity': 1000000000,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'test',
                                                          {'contract': u'BTC',
                                                           'quantity': 1000000000,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'test',
                                                          {'contract': u'BTC',
                                                           'quantity': -900000000,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'depositoverflow',
                                                          {'contract': u'BTC',
                                                           'quantity': 900000000,
                                                           'type': u'Deposit'}),
                                                         {})]))

    def test_deposit_cash_permission_denied(self):
        from sputnik import models

        self.create_account('test', '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.session.commit()

        self.cashier_export.deposit_cash("18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv", 10)

        # Make sure the position didn't get updated
        position = self.session.query(models.Position).filter_by(
            username="test").one()
        self.assertEqual(position.position, 0)
        self.assertEqual(position.position_calculated, position.position)

        # Make sure the overflow position gets the cash
        overflow_position = self.session.query(models.Position).filter_by(
            username="depositoverflow").one()
        self.assertEqual(overflow_position.position, 10)
        self.assertEqual(overflow_position.position_calculated, overflow_position.position)
        self.assertTrue(self.webserver.check_for_calls([('transaction',
                                                         (u'onlinecash',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'test',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'test',
                                                          {'contract': u'BTC',
                                                           'quantity': -10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'depositoverflow',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {})]))


class TestAdministratorExport(TestAccountant):
    def test_transfer_position(self):
        from sputnik import models

        self.create_account("from_account", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.create_account("to_account", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('from_account', 'Deposit')
        self.set_permissions_group('to_account', 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 10)
        self.cashier_export.deposit_cash('28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 10)

        self.administrator_export.transfer_position('BTC', 'from_account', 'to_account', 5, 'note')
        from_position = self.session.query(models.Position).filter_by(username='from_account').one()
        to_position = self.session.query(models.Position).filter_by(username='to_account').one()

        self.assertEqual(from_position.position, 5)
        self.assertEqual(to_position.position, 15)
        self.assertEqual(from_position.position_calculated, from_position.position)
        self.assertEqual(to_position.position_calculated, to_position.position)
        self.assertTrue(self.webserver.check_for_calls([('transaction',
                                                         (u'onlinecash',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'from_account',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'onlinecash',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'to_account',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'from_account',
                                                          {'contract': u'BTC',
                                                           'quantity': -5,
                                                           'type': u'Transfer'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'to_account',
                                                          {'contract': u'BTC',
                                                           'quantity': 5,
                                                           'type': u'Transfer'}),
                                                         {})]
        ))

    def test_adjust_position(self):
        from sputnik import models

        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('test', 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 10)

        self.administrator_export.adjust_position('test', 'BTC', 10)
        position = self.session.query(models.Position).filter_by(
            username="test").one()
        self.assertEqual(position.position, 20)
        self.assertEqual(position.position_calculated, position.position)

        self.assertTrue(self.webserver.check_for_calls([('transaction',
                                                         (u'onlinecash',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'test',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'test',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Adjustment'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'adjustments',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Adjustment'}),
                                                         {})]))

    def test_get_balance_sheet(self):
        # NOT IMPLEMENTED
        pass

    def test_change_permission_group(self):
        from sputnik import models

        self.create_account("test")
        id = self.session.query(models.PermissionGroup.id).filter_by(name='Deposit').one().id
        self.administrator_export.change_permission_group('test', id)
        user = self.session.query(models.User).filter_by(username='test').one()
        self.assertEqual(user.permission_group_id, id)

    def test_new_permission_group(self):
        from sputnik import models
        new_permissions = ['trade', 'login']
        self.administrator_export.new_permission_group('New Test Group', new_permissions)

        group = self.session.query(models.PermissionGroup).filter_by(name='New Test Group').one()

        self.assertFalse(group.deposit)
        self.assertFalse(group.withdraw)
        self.assertTrue(group.trade)
        self.assertTrue(group.login)

class TestEngineExport(TestAccountant):
    def test_post_transaction(self):
        from sputnik import util, models
        import datetime

        self.create_account("aggressive_user", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.create_account("passive_user", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("aggressive_user", 'Deposit')
        self.set_permissions_group("passive_user", "Deposit")
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash('28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 3000000)

        test_transaction = {'aggressive_username': 'aggressive_user',
                            'passive_username': 'passive_user',
                            'contract': 'BTC/MXN',
                            'price': 60000000,
                            'quantity': 3000000,
                            'aggressive_order_id': 54,
                            'passive_order_id': 50,
                            'side': 'SELL',
                            'timestamp': util.dt_to_timestamp(datetime.datetime.utcnow())}
        self.engine_export.post_transaction(test_transaction)

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
        self.assertEqual(passive_user_btc_position.position, 3000000)

        # This is based on 40bps MXN fee, only charged to the aggressive_user
        self.assertEqual(aggressive_user_mxn_position.position, 1792800)
        self.assertEqual(passive_user_mxn_position.position, 1200000)

        # Check to be sure it made all the right calls
        self.assertTrue(self.webserver.check_for_calls([('transaction',
                                                         (u'onlinecash',
                                                          {'contract': u'BTC',
                                                           'quantity': 5000000,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'aggressive_user',
                                                          {'contract': u'BTC',
                                                           'quantity': 5000000,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'onlinecash',
                                                          {'contract': u'MXN',
                                                           'quantity': 3000000,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'passive_user',
                                                          {'contract': u'MXN',
                                                           'quantity': 3000000,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'aggressive_user',
                                                          {'contract': u'MXN',
                                                           'quantity': 1800000,
                                                           'type': u'Trade'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'aggressive_user',
                                                          {'contract': u'BTC',
                                                           'quantity': -3000000,
                                                           'type': u'Trade'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'passive_user',
                                                          {'contract': u'MXN',
                                                           'quantity': -1800000,
                                                           'type': u'Trade'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'passive_user',
                                                          {'contract': u'BTC',
                                                           'quantity': 3000000,
                                                           'type': u'Trade'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'aggressive_user',
                                                          {'contract': u'MXN',
                                                           'quantity': -7200,
                                                           'type': u'Trade'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'customer',
                                                          {'contract': u'MXN',
                                                           'quantity': 3600,
                                                           'type': u'Trade'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'm2',
                                                          {'contract': u'MXN',
                                                           'quantity': 3600,
                                                           'type': u'Trade'}),
                                                         {}),
                                                        ('fill',
                                                         ('aggressive_user',
                                                          {'contract': 'BTC/MXN',
                                                           'fees': {u'BTC': 0, u'MXN': 3600},
                                                           'id': 54,
                                                           'price': 60000000,
                                                           'quantity': 3000000,
                                                           'side': 'SELL'
                                                          }),
                                                         {}),
                                                        ('fill',
                                                         ('passive_user',
                                                          {'contract': 'BTC/MXN',
                                                           'fees': {u'BTC': 0, u'MXN': 3600},
                                                           'id': 50,
                                                           'price': 60000000,
                                                           'quantity': 3000000,
                                                           'side': 'BUY'
                                                          }),
                                                         {})]))

    def test_safe_prices(self):
        pass


class TestWebserverExport(TestAccountant):
    def test_place_order(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash('28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group("test", 'Trade')

        # Place a sell order, we have enough cash
        d = self.webserver_export.place_order({'username': 'test',
                                                    'contract': 'BTC/MXN',
                                                    'price': 1000000,
                                                    'quantity': 3000000,
                                                    'side': 'SELL'})

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

            self.assertTrue(self.engines['BTC/MXN'].check_for_calls([('place_order',
                                                                      {'contract': 5,
                                                                       'id': 1,
                                                                       'price': 1000000,
                                                                       'quantity': 3000000,
                                                                       'quantity_left': 3000000,
                                                                       'side': 1,
                                                                       'username': u'test'},
                                                                      {})]))

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_place_order_prediction_buy(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group("test", 'Trade')

        # Place a buy order, we have enough cash
        d = self.webserver_export.place_order({'username': 'test',
                                                    'contract': 'NETS2014',
                                                    'price': 500,
                                                    'quantity': 3,
                                                    'side': 'BUY'})
        def onSuccess(id):
            from sputnik import models

            order = self.session.query(models.Order).filter_by(id=id).one()
            self.assertEqual(order.username, 'test')
            self.assertEqual(order.contract.ticker, 'NETS2014')
            self.assertEqual(order.price, 500)
            self.assertEqual(order.quantity, 3)
            self.assertEqual(order.side, 'BUY')

            self.assertTrue(self.engines['NETS2014'].check_for_calls([('place_order',
                                                                      {'contract': 8,
                                                                       'id': 1,
                                                                       'price': 500,
                                                                       'quantity': 3,
                                                                       'quantity_left': 3,
                                                                       'side': -1,
                                                                       'username': u'test'},
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
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group("test", 'Trade')

        # Place a buy order, we have enough cash
        d = self.webserver_export.place_order({'username': 'test',
                                                    'contract': 'NETS2014',
                                                    'price': 100,
                                                    'quantity': 3,
                                                    'side': 'SELL'})
        def onSuccess(id):
            from sputnik import models

            order = self.session.query(models.Order).filter_by(id=id).one()
            self.assertEqual(order.username, 'test')
            self.assertEqual(order.contract.ticker, 'NETS2014')
            self.assertEqual(order.price, 100)
            self.assertEqual(order.quantity, 3)
            self.assertEqual(order.side, 'SELL')

            self.assertTrue(self.engines['NETS2014'].check_for_calls([('place_order',
                                                                      {'contract': 8,
                                                                       'id': 1,
                                                                       'price': 100,
                                                                       'quantity': 3,
                                                                       'quantity_left': 3,
                                                                       'side': 1,
                                                                       'username': u'test'},
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

    def test_place_order_no_perms(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash('28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)

        # Place a sell order, we have enough cash
        from sputnik import accountant
        with self.assertRaisesRegexp(accountant.AccountantException, 'Trading not permitted'):
            self.webserver_export.place_order({'username': 'test',
                                                        'contract': 'BTC/MXN',
                                                        'price': 1000000,
                                                        'quantity': 3000000,
                                                        'side': 'SELL'})


    def test_place_order_no_cash(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group("test", 'Trade')

        # Place a sell order, we have no cash
        from sputnik import accountant
        with self.assertRaisesRegexp(accountant.AccountantException, 'Insufficient margin'):
             self.webserver_export.place_order({'username': 'test',
                                                        'contract': 'BTC/MXN',
                                                        'price': 1000000,
                                                        'quantity': 3000000,
                                                        'side': 'SELL'})

    def test_place_order_little_cash(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash('28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group("test", 'Trade')


        # Place a sell order, we have too little cash
        from sputnik import accountant
        with self.assertRaisesRegexp(accountant.AccountantException, 'Insufficient margin'):
            result = self.webserver_export.place_order({'username': 'test',
                                                        'contract': 'BTC/MXN',
                                                        'price': 1000000,
                                                        'quantity': 9000000,
                                                        'side': 'SELL'})


    def test_place_many_orders(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash('28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group("test", 'Trade')

        # Place a sell order, we have enough cash
        d = self.webserver_export.place_order({'username': 'test',
                                                    'contract': 'BTC/MXN',
                                                    'price': 1000000,
                                                    'quantity': 3000000,
                                                    'side': 'SELL'})



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

            self.assertTrue(self.engines['BTC/MXN'].check_for_calls([('place_order',
                                                                      {'contract': 5,
                                                                       'id': 1,
                                                                       'price': 1000000,
                                                                       'quantity': 3000000,
                                                                       'quantity_left': 3000000,
                                                                       'side': 1,
                                                                       'username': u'test'},
                                                                      {})]))

            # Place another sell, we have insufficient cash now
            from sputnik import accountant
            with self.assertRaisesRegexp(accountant.AccountantException, 'Insufficient margin'):
                self.webserver_export.place_order({'username': 'test',
                                                            'contract': 'BTC/MXN',
                                                            'price': 1000000,
                                                            'quantity': 3000000,
                                                            'side': 'SELL'})

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_cancel_order_success(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash('28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group("test", 'Trade')

        # Place a sell order, we have enough cash
        d = self.webserver_export.place_order({'username': 'test',
                                                    'contract': 'BTC/MXN',
                                                    'price': 1000000,
                                                    'quantity': 3000000,
                                                    'side': 'SELL'})

        def onFail(failure):
            self.assertFalse(True)

        def onSuccess(id):
            def cancelSuccess(result):
                self.assertEquals(result, None)

            def cancelFail(failure):
                self.assertTrue(False)

            d = self.webserver_export.cancel_order(id, username='test')
            d.addCallbacks(cancelSuccess, cancelFail)


        d.addCallbacks(onSuccess, onFail)
        return d

    def test_cancel_order_wrong_user(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash('28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group("test", 'Trade')

        # Place a sell order, we have enough cash
        d = self.webserver_export.place_order({'username': 'test',
                                                    'contract': 'BTC/MXN',
                                                    'price': 1000000,
                                                    'quantity': 3000000,
                                                    'side': 'SELL'})

        def onFail(failure):
            self.assertFalse(True)

        def onSuccess(id):
            def cancelSuccess(result):
                self.assertTrue(False)

            def cancelFail(failure):
                self.assertTrue(False)

            from sputnik import accountant
            with self.assertRaisesRegexp(accountant.AccountantException, "User wrong does not own the order"):
                d = self.webserver_export.cancel_order(id, username='wrong')
                d.addCallbacks(cancelSuccess, cancelFail)


        d.addCallbacks(onSuccess, onFail)
        return d

    def test_cancel_order_no_order(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'MXN')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash('28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group("test", 'Trade')

        def cancelSuccess(result):
            self.assertTrue(False)

        def cancelFail(failure):
            self.assertTrue(False)

        from sputnik import accountant
        id = 5
        with self.assertRaisesRegexp(accountant.AccountantException, "No order 5 found"):
            d = self.webserver_export.cancel_order(id, username='wrong')
            d.addCallbacks(cancelSuccess, cancelFail)
            return d

    def test_get_permissions(self):
        pass

    def test_get_audit(self):
        pass

    def test_get_transaction_history(self):
        pass

    def test_request_withdrawal_success(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('test', 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group('test', 'Withdraw')
        result = self.webserver_export.request_withdrawal('test', 'BTC', 3000000, 'bad_address')

        # Make sure it returns success
        self.assertTrue(result)

        # Check that the positions are changed
        from sputnik import models

        user_position = self.session.query(models.Position).filter_by(username='test').one()
        pending_position = self.session.query(models.Position).filter_by(username='pendingwithdrawal').one()

        self.assertEqual(user_position.position, 2000000)
        self.assertEqual(pending_position.position, 3000000)

        self.assertTrue(self.webserver.check_for_calls([('transaction',
                                                         (u'onlinecash',
                                                          {'contract': u'BTC',
                                                           'quantity': 5000000,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'test',
                                                          {'contract': u'BTC',
                                                           'quantity': 5000000,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'pendingwithdrawal',
                                                          {'contract': u'BTC',
                                                           'quantity': 3000000,
                                                           'type': u'Withdrawal'}),
                                                         {}),
                                                        ('transaction',
                                                         (u'test',
                                                          {'contract': u'BTC',
                                                           'quantity': -3000000,
                                                           'type': u'Withdrawal'}),
                                                         {})]))
        self.assertTrue(
            self.cashier.check_for_calls([('request_withdrawal', ('test', 'BTC', 'bad_address', 3000000), {})]))


    def test_request_withdrawal_no_perms(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')

        from sputnik import accountant
        with self.assertRaisesRegexp(accountant.AccountantException, 'Withdrawals not permitted'):
            self.webserver_export.request_withdrawal('test', 'BTC', 3000000, 'bad_address')

        self.assertEqual(self.cashier.log, [])

    def test_request_withdrawal_no_margin_btc(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('test', 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group('test', 'Withdraw')

        from sputnik import accountant
        with self.assertRaisesRegexp(accountant.AccountantException, 'Insufficient margin'):
            self.webserver_export.request_withdrawal('test', 'BTC', 8000000, 'bad_address')

        self.assertEqual(self.cashier.log, [])

    def test_request_withdrawal_no_margin_fiat(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('test', 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.set_permissions_group('test', 'Withdraw')

        from sputnik import accountant
        with self.assertRaisesRegexp(accountant.AccountantException, 'Insufficient margin'):
            self.webserver_export.request_withdrawal('test', 'MXN', 8000000, 'bad_address')

        self.assertEqual(self.cashier.log, [])


