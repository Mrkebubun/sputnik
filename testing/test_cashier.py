import sys
import os
from test_sputnik import TestSputnik, FakeProxy
from pprint import pprint

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../tools"))


class TestCashier(TestSputnik):
    def setUp(self):
        TestSputnik.setUp(self)

        from sputnik import cashier

        self.accountant = FakeProxy()
        self.bitcoinrpc = FakeProxy()
        self.compropago = FakeProxy()
        self.cashier = cashier.Cashier(self.session, self.accountant,
                                          self.bitcoinrpc,
                                          self.compropago)

        self.administrator_export = cashier.AdministratorExport(self.cashier)
        self.accountant_export = cashier.AccountantExport(self.cashier)
        self.compropago_hook = cashier.CompropagoHook(self.cashier)
        self.bitcoin_notify = cashier.BitcoinNotify(self.cashier)


class TestAdministratorExport(TestCashier):
    def test_rescan_address(self):
        pass

    def test_process_withdrawal(self):
        pass

class TestAccountantExport(TestCashier):
    def test_request_withdrawal(self):
        pass

class TestCompropagoHook(TestCashier):
    def test_render(self):
        pass

class TestBitcoinNotify(TestCashier):
    def test_render_GET(self):
        pass
