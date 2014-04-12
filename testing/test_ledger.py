import sys
import os

from twisted.internet.defer import maybeDeferred
from twisted.internet import task

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
        self.clock = task.Clock()

    def test_post_sequentially(self):
        post1 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":5, "side":"buy"}
        post2 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":-5, "side":"sell"}
        d1 = self.export.post(post1)
        return self.export.post(post2)

    def test_post_results_agree(self):
        post1 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":5, "side":"buy"}
        post2 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":-5, "side":"sell"}
        d1 = self.export.post(post1)
        d2 = self.export.post(post2)
        return self.assertEqual(self.successResultOf(d1),
                self.successResultOf(d2))

    def test_post_simultaneously(self):
        post1 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":5, "side":"buy"}
        post2 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":-5, "side":"sell"}
        return self.export.post(post1, post2)

    def test_count_mismatch(self):
        post1 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":5, "side":"buy"}
        post2 = {"uid":"foo", "count":1, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":-5, "side":"sell"}
        d1 = self.export.post(post1)
        d1.addErrback(lambda x: None)
        d2 = self.assertFailure(self.export.post(post2),
                ledger.LedgerException)
        return self.assertEqual(self.successResultOf(d2),
                ledger.COUNT_MISMATCH)

    def test_type_mismatch(self):
        post1 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":5, "side":"buy"}
        post2 = {"uid":"foo", "count":2, "type":"Deposit", "user":"customer",
                 "contract":"BTC/MXN", "quantity":-5, "side":"sell"}
        d1 = self.export.post(post1)
        d1.addErrback(lambda x: None)
        d2 = self.assertFailure(self.export.post(post2),
                ledger.LedgerException)
        return self.assertEqual(self.successResultOf(d2),
                ledger.TYPE_MISMATCH)

    def test_contract_mismatch(self):
        post1 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC", "quantity":5, "side":"buy"}
        post2 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":-5, "side":"sell"}
        d1 = self.export.post(post1)
        d1.addErrback(lambda x: None)
        d2 = self.assertFailure(self.export.post(post2),
                ledger.LedgerException)
        return self.assertEqual(self.successResultOf(d2),
                ledger.CONTRACT_MISMATCH)

    def test_quantity_mismatch(self):
        post1 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":5, "side":"buy"}
        post2 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":-1, "side":"sell"}
        d1 = self.export.post(post1)
        d1.addErrback(lambda x: None)
        d2 = self.assertFailure(self.export.post(post2),
                ledger.LedgerException)
        return self.assertEqual(self.successResultOf(d2),
                ledger.QUANTITY_MISMATCH)

    def test_timeout(self):
        post1 = {"uid":"foo", "count":2, "type":"Trade", "user":"customer",
                 "contract":"BTC/MXN", "quantity":5, "side":"buy"}
        d1 = self.assertFailure(self.export.post(post1),
                ledger.LedgerException)
        group = self.ledger.pending["foo"]
        group.callLater = self.clock.callLater
        group.setTimeout(1)
        self.clock.advance(2)

        return self.assertEqual(self.successResultOf(d1),
                ledger.GROUP_TIMEOUT)

