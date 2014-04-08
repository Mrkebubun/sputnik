import sys
import os
from test_sputnik import TestSputnik, FakeProxy
from pprint import pprint

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../tools"))

accountant_init = """
permissions add Deposit
permissions modify Deposit deposit 1

permissions add Trade
permissions modify Trade trade 1

permissions add Withdraw
permissions modify Withdraw withdraw 1

permissions add Full
permissions modify Full deposit 1
permissions modify Full trade 1
permissions modify Full withdraw 1
"""


class FakeEngine(FakeProxy):
    def place_order(self, order):
        self.log.append(('place_order', (order), {}))
        # Always return a good fake result
        return [True, order['id']]


class TestAccountant(TestSputnik):
    def setUp(self):
        TestSputnik.setUp(self)
        self.run_leo(accountant_init)

        from sputnik import accountant

        self.engines = {"BTC/MXN": FakeEngine()}
        self.webserver = FakeProxy()
        self.accountant = accountant.Accountant(self.session, self.engines,
                                                self.webserver, True)
        self.cashier_export = accountant.CashierExport(self.accountant)
        self.administrator_export = accountant.AdministratorExport(self.accountant)
        self.webserver_export = accountant.WebserverExport(self.accountant)
        self.engine_export = accountant.EngineExport(self.accountant)


    def add_address(self, username, address, currency='btc'):
        self.leo.parse("addresses add %s %s" % (currency, address))
        self.leo.parse("addresses modify %s username %s" % (address, username))
        self.leo.parse("addresses modify %s active 1" % address)
        self.session.commit()

    def create_account(self, username, address=None, currency='btc'):
        self.leo.parse("accounts add %s" % username)
        self.session.commit()

        if address is not None:
            self.add_address(username, address, currency=currency)

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
        self.assertTrue(self.webserver.check_for_calls([('ledger',
                                                         (u'onlinecash',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'test',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {})]))

    def test_deposit_cash_too_much(self):
        from sputnik import models

        self.create_account('test', '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('test', 'Deposit')

        self.cashier_export.deposit_cash("18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv", 1000000000)
        position = self.session.query(models.Position).filter_by(
            username="test").one()
        self.assertEqual(position.position, self.accountant.deposit_limits['btc'])
        self.assertEqual(position.position, position.position_calculated)

        # Make sure the overflow position gets the cash
        overflow_position = self.session.query(models.Position).filter_by(
            username="depositoverflow").one()
        self.assertEqual(overflow_position.position, 1000000000 - self.accountant.deposit_limits['btc'])
        self.assertEqual(overflow_position.position_calculated, overflow_position.position)
        self.assertTrue(self.webserver.check_for_calls([('ledger',
                                                         (u'onlinecash',
                                                          {'contract': u'BTC',
                                                           'quantity': 1000000000,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'test',
                                                          {'contract': u'BTC',
                                                           'quantity': 1000000000,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'test',
                                                          {'contract': u'BTC',
                                                           'quantity': -900000000,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
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
        self.assertTrue(self.webserver.check_for_calls([('ledger',
                                                         (u'onlinecash',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'test',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'test',
                                                          {'contract': u'BTC',
                                                           'quantity': -10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
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

        self.administrator_export.transfer_position('BTC', 'from_account', 'to_account', 5)
        from_position = self.session.query(models.Position).filter_by(username='from_account').one()
        to_position = self.session.query(models.Position).filter_by(username='to_account').one()

        self.assertEqual(from_position.position, 5)
        self.assertEqual(to_position.position, 15)
        self.assertEqual(from_position.position_calculated, from_position.position)
        self.assertEqual(to_position.position_calculated, to_position.position)
        self.assertTrue(self.webserver.check_for_calls([('ledger',
                                                         (u'onlinecash',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'from_account',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'onlinecash',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'to_account',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'from_account',
                                                          {'contract': u'BTC',
                                                           'quantity': -5,
                                                           'type': u'Transfer'}),
                                                         {}),
                                                        ('ledger',
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

        self.assertTrue(self.webserver.check_for_calls([('ledger',
                                                         (u'onlinecash',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'test',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'test',
                                                          {'contract': u'BTC',
                                                           'quantity': 10,
                                                           'type': u'Adjustment'}),
                                                         {}),
                                                        ('ledger',
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

        self.administrator_export.new_permission_group('New Test Group')
        count = self.session.query(models.PermissionGroup).filter_by(name='New Test Group').count()
        self.assertEqual(count, 1)

    def test_modify_permission_group(self):
        from sputnik import models

        id = self.session.query(models.PermissionGroup.id).filter_by(name='Deposit').one().id
        new_permissions = ['trade', 'login']

        self.administrator_export.modify_permission_group(id, new_permissions)
        group = self.session.query(models.PermissionGroup).filter_by(name='Deposit').one()
        self.assertFalse(group.deposit)
        self.assertFalse(group.withdraw)
        self.assertTrue(group.trade)
        self.assertTrue(group.login)


class TestEngineExport(TestAccountant):
    def test_post_transaction(self):
        from sputnik import util, models
        import datetime

        self.create_account("aggressive_user", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.create_account("passive_user", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'mxn')
        self.set_permissions_group("aggressive_user", 'Deposit')
        self.set_permissions_group("passive_user", "Deposit")
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash('28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 30000)

        test_transaction = {'aggressive_username': 'aggressive_user',
                            'passive_username': 'passive_user',
                            'contract': 'BTC/MXN',
                            'price': 600000,
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

        # This is based on 20bps MXN fee
        self.assertEqual(aggressive_user_mxn_position.position, 17964)
        self.assertEqual(passive_user_mxn_position.position, 11964)

        # Check to be sure it made all the right calls
        self.assertTrue(self.webserver.check_for_calls([('ledger',
                                                         (u'onlinecash',
                                                          {'contract': u'BTC',
                                                           'quantity': 5000000,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'aggressive_user',
                                                          {'contract': u'BTC',
                                                           'quantity': 5000000,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'onlinecash',
                                                          {'contract': u'MXN',
                                                           'quantity': 30000,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'passive_user',
                                                          {'contract': u'MXN',
                                                           'quantity': 30000,
                                                           'type': u'Deposit'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'aggressive_user',
                                                          {'contract': u'MXN',
                                                           'quantity': 18000,
                                                           'type': u'Trade'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'aggressive_user',
                                                          {'contract': u'BTC',
                                                           'quantity': -3000000,
                                                           'type': u'Trade'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'passive_user',
                                                          {'contract': u'MXN',
                                                           'quantity': -18000,
                                                           'type': u'Trade'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'passive_user',
                                                          {'contract': u'BTC',
                                                           'quantity': 3000000,
                                                           'type': u'Trade'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'aggressive_user',
                                                          {'contract': u'MXN',
                                                           'quantity': -36,
                                                           'type': u'Fee'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'mexbt',
                                                          {'contract': u'MXN',
                                                           'quantity': 18,
                                                           'type': u'Fee'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'm2',
                                                          {'contract': u'MXN',
                                                           'quantity': 18,
                                                           'type': u'Fee'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'passive_user',
                                                          {'contract': u'MXN',
                                                           'quantity': -36,
                                                           'type': u'Fee'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'mexbt',
                                                          {'contract': u'MXN',
                                                           'quantity': 18,
                                                           'type': u'Fee'}),
                                                         {}),
                                                        ('ledger',
                                                         (u'm2',
                                                          {'contract': u'MXN',
                                                           'quantity': 18,
                                                           'type': u'Fee'}),
                                                         {}),
                                                        ('fill',
                                                         ('aggressive_user',
                                                          {'contract': 'BTC/MXN',
                                                           'fees': {u'BTC': 0, u'MXN': 36.0},
                                                           'id': 54,
                                                           'price': 600000,
                                                           'quantity': 3000000,
                                                           'side': 'SELL'
                                                          }),
                                                         {}),
                                                        ('fill',
                                                         ('passive_user',
                                                          {'contract': 'BTC/MXN',
                                                           'fees': {u'BTC': 0, u'MXN': 36.0},
                                                           'id': 50,
                                                           'price': 600000,
                                                           'quantity': 3000000,
                                                           'side': 'BUY'
                                                          }),
                                                         {})]))

    def test_safe_prices(self):
        pass


class TestWebserverExport(TestAccountant):
    def test_place_order(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'mxn')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash('28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 50000)
        self.set_permissions_group("test", 'Trade')

        # Place a sell order, we have enough cash
        result = self.webserver_export.place_order({'username': 'test',
                                                    'contract': 'BTC/MXN',
                                                    'price': 10000,
                                                    'quantity': 3000000,
                                                    'side': 'SELL'})
        self.assertTrue(result[0])
        id = result[1]
        from sputnik import models
        order = self.session.query(models.Order).filter_by(id=id).one()
        self.assertEqual(order.username, 'test')
        self.assertEqual(order.contract.ticker, 'BTC/MXN')
        self.assertEqual(order.price, 10000)
        self.assertEqual(order.quantity, 3000000)
        self.assertEqual(order.side, 'SELL')

        self.assertTrue(self.engines['BTC/MXN'].check_for_calls([('place_order',
                                                                  {'contract': 3,
                                                                   'id': 1,
                                                                   'price': 10000,
                                                                   'quantity': 3000000,
                                                                   'quantity_left': 3000000,
                                                                   'side': 1,
                                                                   'username': u'test'},
                                                                  {})]))



    def test_place_order_no_perms(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'mxn')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash('28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 50000)

        # Place a sell order, we have enough cash
        result = self.webserver_export.place_order({'username': 'test',
                                                    'contract': 'BTC/MXN',
                                                    'price': 10000,
                                                    'quantity': 3000000,
                                                    'side': 'SELL'})
        self.assertFalse(result[0])
        self.assertTupleEqual(result[1], (1, 'Trading not permitted'))

    def test_place_order_no_cash(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group("test", 'Trade')

        # Place a sell order, we have no cash
        result = self.webserver_export.place_order({'username': 'test',
                                                    'contract': 'BTC/MXN',
                                                    'price': 10000,
                                                    'quantity': 3000000,
                                                    'side': 'SELL'})
        self.assertFalse(result[0])
        self.assertTupleEqual(result[1], (0, 'Insufficient margin'))

    def test_place_order_little_cash(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'mxn')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash('28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 50000)
        self.set_permissions_group("test", 'Trade')


        # Place a sell order, we have too little cash
        result = self.webserver_export.place_order({'username': 'test',
                                                    'contract': 'BTC/MXN',
                                                    'price': 10000,
                                                    'quantity': 9000000,
                                                    'side': 'SELL'})
        self.assertFalse(result[0])
        self.assertTupleEqual(result[1], (0, 'Insufficient margin'))

    def test_place_many_orders(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.add_address("test", '28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 'mxn')
        self.set_permissions_group("test", 'Deposit')
        self.cashier_export.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 5000000)
        self.cashier_export.deposit_cash('28cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 50000)
        self.set_permissions_group("test", 'Trade')

        # Place a sell order, we have enough cash
        result = self.webserver_export.place_order({'username': 'test',
                                                    'contract': 'BTC/MXN',
                                                    'price': 10000,
                                                    'quantity': 3000000,
                                                    'side': 'SELL'})
        self.assertTrue(result[0])
        id = result[1]
        from sputnik import models
        order = self.session.query(models.Order).filter_by(id=id).one()
        self.assertEqual(order.username, 'test')
        self.assertEqual(order.contract.ticker, 'BTC/MXN')
        self.assertEqual(order.price, 10000)
        self.assertEqual(order.quantity, 3000000)
        self.assertEqual(order.side, 'SELL')

        self.assertTrue(self.engines['BTC/MXN'].check_for_calls([('place_order',
                                                                  {'contract': 3,
                                                                   'id': 1,
                                                                   'price': 10000,
                                                                   'quantity': 3000000,
                                                                   'quantity_left': 3000000,
                                                                   'side': 1,
                                                                   'username': u'test'},
                                                                  {})]))

        # Place another sell, we have insufficient cash now
        result = self.webserver_export.place_order({'username': 'test',
                                                    'contract': 'BTC/MXN',
                                                    'price': 10000,
                                                    'quantity': 3000000,
                                                    'side': 'SELL'})
        self.assertFalse(result[0])
        self.assertTupleEqual(result[1], (0, 'Insufficient margin'))

    def test_cancel_order(self):
        pass

    def test_get_permissions(self):
        pass

    def test_get_audit(self):
        pass

    def test_get_ledger_history(self):
        pass

