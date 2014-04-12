import sys
import os

from twisted.internet.defer import maybeDeferred

from test_sputnik import TestSputnik, FakeProxy

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../tools"))

from sputnik import ledger

class TestLedger(TestSputnik):
    def setUp(self):
        TestSputnik.setUp(self)
        self.ledger = ledger.Ledger(self.session)
        self.export = ledger.AccountantExport(self.ledger)

    def test_post_sequential_first(self):
        post1 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":5, "side":"buy"}
        post2 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":-5, "side":"sell"}
        self.export.post(post1)
        return self.export.post(post2)

    def test_post_sequential_second(self):
        post1 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":5, "side":"buy"}
        post2 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":-5, "side":"sell"}
        self.export.post(post1)
        return self.export.post(post2)

    def test_post_simultaneous(self):
        post1 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":5, "side":"buy"}
        post2 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":-5, "side":"sell"}
        return self.export.post(post1, post2)

    def test_fail_count(self):
        post1 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":5, "side":"buy"}
        post2 = {"uid":"foo", "count":1, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":-5, "side":"sell"}
        d1 = self.export.post(post1)
        d1.addErrback(lambda x: None)
        d2 = self.assertFailure(self.export.post(post2), ledger.LedgerException)
        return self.assertEqual(self.successResultOf(d2), ledger.COUNT_MISMATCH)

    def test_fail_type(self):
        post1 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":5, "side":"buy"}
        post2 = {"uid":"foo", "count":2, "type":"Deposit", "user":"customer",
                 "contract":"BTC/MXN", "quantity":-5, "side":"sell"}
        d1 = self.export.post(post1)
        d1.addErrback(lambda x: None)
        d2 = self.assertFailure(self.export.post(post2), ledger.LedgerException)
        return self.assertEqual(self.successResultOf(d2), ledger.TYPE_MISMATCH)

    def test_fail_contract(self):
        post1 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC", "quantity":5, "side":"buy"}
        post2 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":-5, "side":"sell"}
        d1 = self.export.post(post1)
        d1.addErrback(lambda x: None)
        d2 = self.assertFailure(self.export.post(post2), ledger.LedgerException)
        return self.assertEqual(self.successResultOf(d2), ledger.CONTRACT_MISMATCH)

    def test_fail_quantity(self):
        post1 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":5, "side":"buy"}
        post2 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":-1, "side":"sell"}
        d1 = self.export.post(post1)
        d1.addErrback(lambda x: None)
        d2 = self.assertFailure(self.export.post(post2), ledger.LedgerException)
        return self.assertEqual(self.successResultOf(d2), ledger.QUANTITY_MISMATCH)
