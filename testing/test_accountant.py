import sys
import os
import unittest
import StringIO

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

class TestDeposit(unittest.TestCase):
    def setUp(self):
        test_config = "[database]\nuri = sqlite://"
        from sputnik import config
        config.reset()
        config.readfp(StringIO.StringIO(test_config))

        from sputnik import database, models
        self.session = database.make_session()

        import leo
        self.leo = leo.LowEarthOrbit(self.session)
        for line in db_init.split("\n"):
            self.leo.parse(line)
        self.session.commit()

        from sputnik import accountant
        self.engines = {"BTC/MXN":FakeProxy}
        self.webserver = FakeProxy()
        self.accountant = accountant.Accountant(self.session, self.engines,
                                                self.webserver, True)
        self.cashier = accountant.CashierExport(self.accountant)

    def test_deposit_permission_allowed(self):
        from sputnik import models
        self.leo.parse("accounts add test")
        self.leo.parse("permissions add Deposit")
        self.leo.parse("permissions modify Deposit deposit 1")
#        self.leo.parse("accounts modify test permission Deposit")
        self.leo.parse("addresses add btc 18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv")
        self.leo.parse("addresses modify 18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv username test")
        self.leo.parse("addresses modify 18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv active 1")
        self.session.commit()

        user = self.session.query(models.User).filter_by(username="test").one()
        group = self.session.query(models.PermissionGroup).filter_by(name="Deposit").one()
        user.permissions = group
        self.session.merge(user)
        self.session.commit()

        self.cashier.deposit_cash("18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv", 10)
        position = self.session.query(models.Position).filter_by(
            username="test").one()
        self.assertEqual(position.position, 10)

    def test_deposit_permission_denied(self):
        from sputnik import models
        self.leo.parse("accounts add test")
        self.leo.parse("accounts modify test permission Deposit")
        self.leo.parse("addresses add btc 18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv")
        self.leo.parse("addresses modify 18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv username test")
        self.leo.parse("addresses modify 18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv active 1")
        self.session.commit()

        self.cashier.deposit_cash("18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv", 10)
        position = self.session.query(models.Position).filter_by(
            username="test").one()
        self.assertEqual(position.position, 0)

