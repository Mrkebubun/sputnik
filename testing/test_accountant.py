import sys
import os
import unittest
import StringIO
from pprint import pprint

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
        "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
        "../tools"))

db_init = """
database init
contracts add BTC
contracts add MXN
contracts add BTC/MXN
contracts modify BTC contract_type cash
contracts modify BTC denominator 100000000
contracts modify MXN contract_type cash
contracts modify MXN denominator 100
contracts modify BTC/MXN contract_type cash_pair
contracts modify BTC/MXN tick_size 100
contracts modify BTC/MXN lot_size 1000000
contracts modify BTC/MXN denominator 1

permissions add Default

accounts add mexbt
accounts add m2
accounts add remainder
accounts add marketmaker
accounts password marketmaker marketmaker
accounts add randomtrader
accounts password randomtrader randomtrader
accounts position marketmaker BTC
accounts position marketmaker MXN
accounts position randomtrader BTC
accounts position randomtrader MXN

accounts add onlinecash
accounts modify onlinecash type Asset

accounts add depositoverflow
accounts modify depositoverflow type Liability

accounts add adjustments
accounts modify adjustments type Asset

admin add admin
"""

test_init = """
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

class FakeProxy:
    def __init__(self):
        self.log = []

    def __getattr__(self, key):
        if key.startswith("__"):
            raise AttributeError
        
        def proxy_method(*args, **kwargs):
            self.log.append([key, args, kwargs])
            return None

        return proxy_method


class TestAccountant(unittest.TestCase):
    def setUp(self):
        test_config = "[database]\nuri = sqlite://"
        from sputnik import config
        config.reset()
        config.readfp(StringIO.StringIO(test_config))

        from sputnik import database, models
        self.session = database.make_session()

        import leo
        self.leo = leo.LowEarthOrbit(self.session)

        for init in [db_init, test_init]:
            for line in init.split("\n"):
                self.leo.parse(line)
            self.session.commit()

        from sputnik import accountant
        self.engines = {"BTC/MXN":FakeProxy}
        self.webserver = FakeProxy()
        self.accountant = accountant.Accountant(self.session, self.engines,
                                                self.webserver, True)
        self.cashier_export = accountant.CashierExport(self.accountant)
        self.administrator_export = accountant.AdministratorExport(self.accountant)
        self.webserver_export = accountant.WebserverExport(self.accountant)
        self.engine_export = accountant.EngineExport(self.accountant)


    def create_account(self, username, address=None, currency='btc'):
        self.leo.parse("accounts add %s" % username)
        if address is not None:
            self.leo.parse("addresses add %s %s" % (currency, address))
            self.leo.parse("addresses modify %s username %s" % (address, username))
            self.leo.parse("addresses modify %s active 1" % address)

        self.session.commit()

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

    def test_deposit_cash_too_much(self):
        from sputnik import models
        self.create_account('test', '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.set_permissions_group('test', 'Deposit')

        self.cashier_export.deposit_cash("18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv", 100000000)
        position = self.session.query(models.Position).filter_by(
            username="test").one()
        self.assertEqual(position.position, self.accountant.deposit_limits['btc'])
        self.assertEqual(position.position, position.position_calculated)

        # Make sure the overflow position gets the cash
        overflow_position = self.session.query(models.Position).filter_by(
            username="depositoverflow").one()
        self.assertEqual(overflow_position.position, 100000000-self.accountant.deposit_limits['btc'])
        self.assertEqual(overflow_position.position_calculated, overflow_position.position)

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

        pprint(["Webserver Calls", self.webserver.log])


