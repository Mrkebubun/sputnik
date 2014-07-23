import sys
import os

from twisted.internet.defer import maybeDeferred
from twisted.internet import task
from pprint import pprint

from test_sputnik import TestSputnik, FakeProxy

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../tools"))

from sputnik import ledger
from sputnik import models


class TestLedger(TestSputnik):
    def setUp(self):
        TestSputnik.setUp(self)
        self.webserver = FakeProxy()
        self.ledger = ledger.Ledger(self.session, self.webserver)
        self.export = ledger.AccountantExport(self.ledger)
        self.clock = task.Clock()

    def test_post_sequentially(self):
        post1 = {"uid": "foo", "count": 2, "type": "Trade", "user": "customer",
                 "contract": "MXN", "quantity": 5, "direction": "debit", "note": "test_debit"}
        post2 = {"uid": "foo", "count": 2, "type": "Trade", "user": "customer",
                 "contract": "MXN", "quantity": 5, "direction": "credit", "note": "test_credit"}
        d1 = self.export.post(post1)
        return self.export.post(post2)

    def test_post_results_agree(self):
        post1 = {"uid": "foo", "count": 2, "type": "Trade", "user": "customer",
                 "contract": "MXN", "quantity": 5, "direction": "debit", "note": 'debit'}
        post2 = {"uid": "foo", "count": 2, "type": "Trade", "user": "customer",
                 "contract": "MXN", "quantity": 5, "direction": "credit", "note": "credit"}
        d1 = self.export.post(post1)
        d2 = self.export.post(post2)
        return self.assertEqual(self.successResultOf(d1),
                                self.successResultOf(d2))

    def test_post_simultaneously(self):
        post1 = {"uid": "foo", "count": 2, "type": "Trade", "user": "customer",
                 "contract": "MXN", "quantity": 5, "direction": "debit", "note": 'debit'}
        post2 = {"uid": "foo", "count": 2, "type": "Trade", "user": "customer",
                 "contract": "MXN", "quantity": 5, "direction": "credit", "note": 'credit'}
        return self.export.post(post1, post2)

    def test_database_commit(self):
        post1 = {"uid": "foo", "count": 2, "type": "Trade", "user": "customer",
                 "contract": "MXN", "quantity": 5, "direction": "debit", "note": "debit"}
        post2 = {"uid": "foo", "count": 2, "type": "Trade", "user": "customer",
                 "contract": "MXN", "quantity": 5, "direction": "credit", "note": "credit"}
        d = self.export.post(post1, post2)

        def dbtest(arg):
            postings = self.ledger.session.query(models.Posting).all()
            self.assertEqual(len(postings), 2)
            journals = self.ledger.session.query(models.Journal).all()
            self.assertEqual(len(journals), 1)
            p1 = postings[0]
            p2 = postings[1]
            journal = journals[0]
            self.assertEqual(p1.journal_id, journal.id)
            self.assertEqual(p2.journal_id, journal.id)
            self.assertEqual(abs(p1.quantity), 5)
            self.assertEqual(p1.quantity + p2.quantity, 0)
            self.assertTrue(self.webserver.check_for_calls([('transaction',
                                                             (u'customer',
                                                              {'contract': u'MXN',
                                                               'quantity': -5,
                                                               'type': 'Trade'}),
                                                             {}),
                                                            ('transaction',
                                                             (u'customer',
                                                              {'contract': u'MXN',
                                                               'quantity': 5,
                                                               'type': 'Trade'}),
                                                             {})]))

        return d.addCallback(dbtest)

    def test_count_mismatch(self):
        post1 = {"uid": "foo", "count": 2, "type": "Trade", "user": "customer",
                 "contract": "MXN", "quantity": 5, "direction": "debit", "note": "debit"}
        post2 = {"uid": "foo", "count": 1, "type": "Trade", "user": "customer",
                 "contract": "MXN", "quantity": 5, "direction": "credit", "note": "credit"}
        d1 = self.export.post(post1)
        d1.addErrback(lambda x: None)
        d2 = self.assertFailure(self.export.post(post2),
                                ledger.LedgerException)
        return self.assertEqual(self.successResultOf(d2),
                                ledger.COUNT_MISMATCH)

    def test_type_mismatch(self):
        post1 = {"uid": "foo", "count": 2, "type": "Trade", "user": "customer",
                 "contract": "MXN", "quantity": 5, "direction": "debit", "note": "debit"}
        post2 = {"uid": "foo", "count": 2, "type": "Deposit", "user": "customer",
                 "contract": "MXN", "quantity": 5, "direction": "credit", "note": "credit"}
        d1 = self.export.post(post1)
        d1.addErrback(lambda x: None)
        d2 = self.assertFailure(self.export.post(post2),
                                ledger.LedgerException)
        return self.assertEqual(self.successResultOf(d2),
                                ledger.TYPE_MISMATCH)

    def test_quantity_mismatch(self):
        post1 = {"uid": "foo", "count": 2, "type": "Trade", "user": "customer",
                 "contract": "MXN", "quantity": 5, "direction": "debit", "note": 'debit'}
        post2 = {"uid": "foo", "count": 2, "type": "Trade", "user": "customer",
                 "contract": "MXN", "quantity": 1, "direction": "credit", "note": 'credit'}
        d1 = self.export.post(post1)
        d1.addErrback(lambda x: None)
        d2 = self.assertFailure(self.export.post(post2),
                                ledger.LedgerException)
        return self.assertEqual(self.successResultOf(d2),
                                ledger.QUANTITY_MISMATCH)

    def test_timeout(self):
        post1 = {"uid": "foo", "count": 2, "type": "Trade", "user": "customer",
                 "contract": "MXN", "quantity": 5, "direction": "debit", "note": 'debit'}
        d1 = self.assertFailure(self.export.post(post1),
                                ledger.LedgerException)
        group = self.ledger.pending["foo"]
        group.callLater = self.clock.callLater
        group.setTimeout(1)
        self.clock.advance(2)

        return self.assertEqual(self.successResultOf(d1),
                                ledger.GROUP_TIMEOUT)

    def test_get_balance_sheet(self):
        self.create_account("test", '18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv')
        self.accountant.deposit_cash('18cPi8tehBK7NYKfw3nNbPE4xTL8P8DJAv', 100000)
        balance_sheet = self.administrator_export.get_balance_sheet()
        for side in ['assets', 'liabilities']:
            self.assertEqual(balance_sheet[side]['BTC']['total'], 100000)
            for currency in balance_sheet[side].keys():
                total = sum([x['position'] for x in balance_sheet[side][currency]['positions_raw']])
                self.assertEqual(balance_sheet[side][currency]['total'], total)