#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

import sys
import os
from twisted.internet import defer
from test_sputnik import TestSputnik, FakeComponent, FakeSendmail, FakeBitgo
from pprint import pprint
from twisted.web.test.test_web import DummyRequest
from sputnik.exception import CashierException

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../tools"))


class FakeBitcoin(FakeComponent):
    received = {}
    balance = 0.0

    def getnewaddress(self):
        self._log_call("getnewaddress")
        return defer.succeed({'result': "msj42CCGruhRsFrGATiUuh25dtxYtnpbTx"})

    def getreceivedbyaddress(self, address, minimum_confirmations):
        self._log_call("getreceivedbyaddress")
        if address in self.received:
            if self.received[address]['confirmations'] >= minimum_confirmations:
                return defer.succeed({'result': self.received[address]['amount']})

        return defer.succeed({'result': 0.0})

    def listreceivedbyaddress(self, minimum_confirmations):
        self._log_call("listreceivedbyaddress", minimum_confirmations)
        received = []

        for address, info in self.received.iteritems():
            if info['confirmations'] >= minimum_confirmations:
                received.append({'address': address,
                                 'account': '',
                                 'amount': info['amount'],
                                 'confirmations': info['confirmations']})

        return defer.succeed({'result': received})


    def getbalance(self):
        self._log_call("getbalance")
        return defer.succeed({'result': self.balance})

    def sendtoaddress(self, address, amount):
        self._log_call("sendtoaddress", address, amount)
        return defer.succeed({'result': "TXSUCCESS"})

    def gettransaction(self, txid):
        self._log_call("gettransaction", txid)
        if txid == "TXSUCCESS":
            return defer.succeed({'result': {'fee': 0.01}})

    # Utility functions for tester
    def receive_at_address(self, address, amount):
        self._log_call("receive_at_address", address, amount)
        if address in self.received:
            if self.received[address]['amount'] == amount:
                self.received[address]['confirmations'] += 1
            else:
                self.received[address]['amount'] = amount
                self.received[address]['confirmations'] = 1
        else:
            self.received[address] = {'amount': amount,
                                      'confirmations': 1
            }

    def set_balance(self, amount):
        self._log_call("set_balance", amount)
        self.balance = amount

class TestCashier(TestSputnik):
    def setUp(self):
        TestSputnik.setUp(self)

        from sputnik import cashier
        from sputnik import accountant

        self.accountant = accountant.CashierExport(FakeComponent("accountant"))
        self.bitcoinrpc = {'BTC': FakeBitcoin()}
        self.compropago = FakeComponent()
        self.bitgo = FakeBitgo()
        self.sendmail = FakeSendmail('test-email@m2.io')
        from tempfile import mkstemp
        import json
        keyfile = mkstemp(prefix="bitgo_key")[1]
        with open(keyfile, "w") as f:
            json.dump({'passphrase': 'NULL'}, f)

        self.cashier = cashier.Cashier(self.session, self.accountant,
                                       self.bitcoinrpc,
                                       self.compropago,
                                       cold_wallet_period=None,
                                       sendmail=self.sendmail,
                                       template_dir="../server/sputnik/admin_templates",
                                       minimum_confirmations=6,
                                       bitgo=self.bitgo,
                                       bitgo_private_key_file=keyfile,
                                       alerts=FakeComponent("alerts"))

        self.administrator_export = cashier.AdministratorExport(self.cashier)
        self.webserver_export = cashier.WebserverExport(self.cashier)
        self.accountant_export = cashier.AccountantExport(self.cashier)
        self.compropago_hook = cashier.CompropagoHook(self.cashier)
        self.bitcoin_notify = cashier.BitcoinNotify(self.cashier)


class TestWebserverExport(TestCashier):
    def test_get_new_address_already_exists(self):
        self.create_account('test')
        self.add_address(address="muXGTbVYgDcLcpetQg777SmbSbRsk4kpqk")
        d = self.webserver_export.get_new_address('test', 'BTC')


        def onSuccess(new_address):
            self.assertEqual(new_address, 'muXGTbVYgDcLcpetQg777SmbSbRsk4kpqk')

            from sputnik import models

            address = self.session.query(models.Addresses).filter_by(username='test', active=True).one()
            self.assertEqual(address.address, 'muXGTbVYgDcLcpetQg777SmbSbRsk4kpqk')

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)
        return d


    def test_get_new_address_new(self):
        self.create_account('test')
        d = self.webserver_export.get_new_address('test', 'BTC')

        def onSuccess(new_address):
            self.assertEqual(new_address, 'msj42CCGruhRsFrGATiUuh25dtxYtnpbTx')

            from sputnik import models

            address = self.session.query(models.Addresses).filter_by(username='test', active=True).one()
            self.assertEqual(address.address, 'msj42CCGruhRsFrGATiUuh25dtxYtnpbTx')

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_get_new_address_fiat(self):
        self.create_account('test')
        d = self.webserver_export.get_new_address('test', 'MXN')

        def onSuccess(new_address):
            from sputnik import models

            address = self.session.query(models.Addresses).filter_by(username='test', active=True).one()
            self.assertEqual(address.address, new_address)

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_get_current_address_exists(self):
        self.create_account('test', 'STARTING_ADDRESS')
        d = self.webserver_export.get_current_address('test', 'BTC')

        def onSuccess(current_address):
            self.assertEqual(current_address, 'STARTING_ADDRESS')

        def onFail(failure):
            self.assertTrue(False)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_get_current_address_not_exists(self):
        self.create_account('test')
        d = self.webserver_export.get_current_address('test', 'BTC')

        def onSuccess(current_address):
            self.assertEqual(current_address, 'msj42CCGruhRsFrGATiUuh25dtxYtnpbTx')

            from sputnik import models

            address = self.session.query(models.Addresses).filter_by(username='test', active=True).one()
            self.assertEqual(address.address, 'msj42CCGruhRsFrGATiUuh25dtxYtnpbTx')

        def onFail(failure):
            self.assertTrue(False)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_get_current_address_not_exists_fiat(self):
        self.create_account('test')
        d = self.webserver_export.get_current_address('test', 'MXN')

        def onSuccess(current_address):
            from sputnik import models

            address = self.session.query(models.Addresses).filter_by(username='test', active=True).one()
            self.assertEqual(address.address, current_address)

        def onFail(failure):
            self.assertTrue(False)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_get_deposit_instructions(self):
        instructions = self.webserver_export.get_deposit_instructions('BTC')
        self.assertEqual(instructions,  u'<p>Please send your crypto-currency to this address</p>')


class TestAdministratorExport(TestCashier):
    def test_transfer_from_hot_wallet_to_offlinecash(self):
        self.cashier.bitcoinrpc['BTC'].set_balance(0.01)

        d = self.administrator_export.transfer_from_hot_wallet('BTC', 1000, 'offlinecash')
        def onSuccess(result):
            self.assertTrue(self.accountant.component.check_for_calls([('transfer_position',
                                                                        ('onlinecash',
                                                                         'BTC',
                                                                         'credit',
                                                                         1000000L,
                                                                         u'n2JvYcXqkHAKUNj6X4iG3xFzX3moCpHujj: TXSUCCESS',
                                                                        ),
                                                                        {}),
                                                                       ('transfer_position',
                                                                        ('customer',
                                                                         'BTC',
                                                                         'debit',
                                                                         1000000L,
                                                                         u'n2JvYcXqkHAKUNj6X4iG3xFzX3moCpHujj: TXSUCCESS',
                                                                        ),
                                                                        {}),
                                                                       ('transfer_position',
                                                                        ('onlinecash',
                                                                         'BTC',
                                                                         'credit',
                                                                         1000,
                                                                         'n2JvYcXqkHAKUNj6X4iG3xFzX3moCpHujj: TXSUCCESS'),
                                                                        {}),
                                                                       ('transfer_position',
                                                                        ('offlinecash',
                                                                         'BTC',
                                                                         'debit',
                                                                         1000,
                                                                         'n2JvYcXqkHAKUNj6X4iG3xFzX3moCpHujj: TXSUCCESS'),
                                                                        {})]))
            self.assertEqual(self.bitgo.component.log, [])
            self.assertTrue(self.bitcoinrpc['BTC'].check_for_calls([('set_balance', (0.01,), {}),
                                                                    ('getbalance', (), {}),
                                                                    ('sendtoaddress', ('n2JvYcXqkHAKUNj6X4iG3xFzX3moCpHujj', 1e-05), {})]))


        def onFail(failure):
            self.assertTrue(False)

        d.addCallbacks(onSuccess, onFail)

    def test_transfer_from_hot_wallet_to_multisigcash(self):
        self.cashier.bitcoinrpc['BTC'].set_balance(0.01)

        d = self.administrator_export.transfer_from_hot_wallet('BTC', 1000, 'multisigcash')
        def onSuccess(result):
            self.assertTrue(self.accountant.component.check_for_calls([('transfer_position',
                                                                        ('onlinecash',
                                                                         'BTC',
                                                                         'credit',
                                                                         1000,
                                                                         'myDu5UC7aCWXTmfJPQKC72gNCDStu9voeo: TXSUCCESS'),
                                                                        {}),
                                                                       ('transfer_position',
                                                                        ('multisigcash',
                                                                         'BTC',
                                                                         'debit',
                                                                         1000,
                                                                         'myDu5UC7aCWXTmfJPQKC72gNCDStu9voeo: TXSUCCESS'),
                                                                        {})]))
            self.assertEqual(self.bitgo.component.log, [])
            self.assertTrue(self.bitcoinrpc['BTC'].check_for_calls([('set_balance', (0.01,), {}),
                                                                    ('getbalance', (), {}),
                                                                    ('sendtoaddress', ('myDu5UC7aCWXTmfJPQKC72gNCDStu9voeo', 1e-05), {})]))


        def onFail(failure):
            self.assertTrue(False)

        d.addCallbacks(onSuccess, onFail)

    def test_transfer_from_multisig_wallet_to_offlinecash(self):

        d = self.administrator_export.transfer_from_multisig_wallet('BTC', 1000, 'offlinecash', multisig={'otp': '000000',
                                                                                                          'token': 'TOKEN'})

        def onSuccess(result):
            self.assertTrue(self.accountant.component.check_for_calls(
                [('transfer_position',
                  ('multisigcash',
                   'BTC',
                   'credit',
                   1000000,
                   u'n2JvYcXqkHAKUNj6X4iG3xFzX3moCpHujj: TXSUCCESS',
                   ),
                  {}),
                 ('transfer_position',
                  ('customer',
                   'BTC',
                   'debit',
                   1000000,
                   u'n2JvYcXqkHAKUNj6X4iG3xFzX3moCpHujj: TXSUCCESS',
                   ),
                  {}),
                 ('transfer_position',
                  ('multisigcash',
                   'BTC',
                   'credit',
                   1000,
                   u'n2JvYcXqkHAKUNj6X4iG3xFzX3moCpHujj: TXSUCCESS',
                  ),
                  {}),
                 ('transfer_position',
                  ('offlinecash',
                   'BTC',
                   'debit',
                   1000,
                   u'n2JvYcXqkHAKUNj6X4iG3xFzX3moCpHujj: TXSUCCESS',
                  ),
                  {})]))
            self.assertTrue(self.bitgo.component.check_for_calls([('unlock', ('000000',), {})]))
            self.assertEqual(self.bitcoinrpc['BTC'].log, [])
            d = self.bitgo.wallets.get('myDu5UC7aCWXTmfJPQKC72gNCDStu9voeo')

            def _cb(wallet):
                self.assertTrue(wallet.check_for_calls([('sendCoins',
                                                         (),
                                                         {'address': u'n2JvYcXqkHAKUNj6X4iG3xFzX3moCpHujj', 'amount': 1000,
                                                          'passphrase': u'NULL'})]
                ))

            d.addCallback(_cb)
            return d


        def onFail(failure):
            self.assertTrue(False)

        d.addCallbacks(onSuccess, onFail)

    def test_transfer_from_multisig_wallet_to_onlinecash(self):

        d = self.administrator_export.transfer_from_multisig_wallet('BTC', 1000, 'onlinecash', multisig={'otp': '000000',
                                                                                                          'token': 'TOKEN'})

        def onSuccess(result):
            self.assertTrue(self.accountant.component.check_for_calls([('transfer_position',
                                                              ('multisigcash',
                                                               'BTC',
                                                               'credit',
                                                               1000000,
                                                               'msj42CCGruhRsFrGATiUuh25dtxYtnpbTx: TXSUCCESS',
                                                              ),
                                                              {}),
                                                             ('transfer_position',
                                                              ('customer',
                                                               'BTC',
                                                               'debit',
                                                               1000000,
                                                               'msj42CCGruhRsFrGATiUuh25dtxYtnpbTx: TXSUCCESS',
                                                              ),
                                                              {})]))
            self.assertTrue(self.bitgo.component.check_for_calls([('unlock', ('000000',), {})]))
            self.assertEqual(self.bitcoinrpc['BTC'].log, [('getnewaddress', (), {})])
            d = self.bitgo.wallets.get('myDu5UC7aCWXTmfJPQKC72gNCDStu9voeo')

            def _cb(wallet):
                self.assertTrue(wallet.check_for_calls([('sendCoins',
                                                         (),
                                                         {'address': u'msj42CCGruhRsFrGATiUuh25dtxYtnpbTx', 'amount': 1000,
                                                          'passphrase': u'NULL'})]
                ))

            d.addCallback(_cb)
            return d


        def onFail(failure):
            self.assertTrue(False)

        d.addCallbacks(onSuccess, onFail)
    def test_rescan_address_with_deposit(self):
        self.create_account('test', 'mm2wh34gqqchF2jNqJ7MGXFRrMtMX6pDaA')
        for confirmation in range(0, 6):
            self.cashier.bitcoinrpc['BTC'].receive_at_address('mm2wh34gqqchF2jNqJ7MGXFRrMtMX6pDaA', 1.23)

        d = self.administrator_export.rescan_address('mm2wh34gqqchF2jNqJ7MGXFRrMtMX6pDaA')

        def onSuccess(result):
            self.assertTrue(result)
            self.assertTrue(self.accountant.component.check_for_calls([('deposit_cash', ("test", 'mm2wh34gqqchF2jNqJ7MGXFRrMtMX6pDaA', 123000000L), {})]))

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_rescan_address_with_deposit_insufficient_confirms(self):
        self.create_account('test', 'mqJmQC7jP41Gyac5K1dMRQfLCqBWisNpZZ')
        for confirmation in range(0, 5):
            self.cashier.bitcoinrpc['BTC'].receive_at_address('mqJmQC7jP41Gyac5K1dMRQfLCqBWisNpZZ', 1.23)

        d = self.administrator_export.rescan_address('mqJmQC7jP41Gyac5K1dMRQfLCqBWisNpZZ')

        def onSuccess(result):
            self.assertTrue(result)
            self.assertEquals(self.accountant.component.log, [])

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_rescan_address_with_nodeposit(self):
        self.create_account('test', 'mkoQqsBvwFUUruWPkprTEfcf63mau3Twvp')

        d = self.administrator_export.rescan_address('mkoQqsBvwFUUruWPkprTEfcf63mau3Twvp')

        def onSuccess(result):
            self.assertTrue(result)
            self.assertEquals(self.accountant.component.log, [])

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_process_withdrawal_bad_address(self):
        self.create_account('test')
        d = self.cashier.request_withdrawal('test', 'BTC', 'BAD_ADDRESS', 1000000)

        def onSuccess(withdrawal_id):
            self.cashier.bitcoinrpc['BTC'].set_balance(0.01)

            d = self.administrator_export.process_withdrawal(withdrawal_id, online=True, admin_username='test_admin')
            def onFail(failure):
                self.assertEqual(failure.value.args, ("exceptions/cashier/invalid_address", ))

            def onSuccess(result):
                self.assertFalse(True)

            d.addCallbacks(onSuccess, onFail)
            return d

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_process_withdrawal_online_have_cash(self):
        self.create_account('test')
        d = self.cashier.request_withdrawal('test', 'BTC', 'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M', 1000000)

        def onSuccess(withdrawal_id):
            self.cashier.bitcoinrpc['BTC'].set_balance(0.01)

            from sputnik import models

            d = self.administrator_export.process_withdrawal(withdrawal_id, online=True, admin_username='test_admin')

            def onSuccess(txid):
                withdrawal = self.session.query(models.Withdrawal).filter_by(id=withdrawal_id).one()
                self.assertTrue(self.accountant.component.check_for_calls([('transfer_position',
                                                                            ('onlinecash',
                                                                             u'BTC',
                                                                             'credit',
                                                                             1000000L,
                                                                             u'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M: TXSUCCESS (test_admin)',
                                                                             ),
                                                                            {}),
                                                                           ('transfer_position',
                                                                            ('customer',
                                                                             u'BTC',
                                                                             'debit',
                                                                             1000000L,
                                                                             u'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M: TXSUCCESS (test_admin)',
                                                                             ),
                                                                            {}),
                                                                           ('transfer_position',
                                                                            ('pendingwithdrawal',
                                                                             u'BTC',
                                                                             'debit',
                                                                             1000000,
                                                                             u'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M: TXSUCCESS (test_admin)'),
                                                                            {}),
                                                                           ('transfer_position',
                                                                            ('onlinecash',
                                                                             u'BTC',
                                                                             'credit',
                                                                             1000000,
                                                                             'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M: TXSUCCESS (test_admin)'),
                                                                            {})]))
                self.assertFalse(withdrawal.pending)

            def onFail(failure):
                self.assertTrue(False)

            d.addCallbacks(onSuccess, onFail)
            return d

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_process_withdrawal_online_no_cash(self):
        self.create_account('test')
        d = self.cashier.request_withdrawal('test', 'BTC', 'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M', 1000000)

        def onSuccess(withdrawal_id):
            self.cashier.bitcoinrpc['BTC'].set_balance(0.0)

            d = self.administrator_export.process_withdrawal(withdrawal_id, online=True, admin_username='test_admin')

            def onSuccess(result):
                self.assertTrue(False)

            def onFail(failure):
                self.assertEqual(failure.value.args, ("exceptions/cashier/insufficient_funds",))
                from sputnik import models

                withdrawal = self.session.query(models.Withdrawal).filter_by(id=withdrawal_id).one()

                self.assertEqual(self.accountant.component.log, [])
                self.assertTrue(self.bitcoinrpc['BTC'].component.check_for_calls([('getbalance', (), {}), ('set_balance', (0.0,), {}), ('getbalance', (), {})]))
                self.assertTrue(withdrawal.pending)

            d.addCallbacks(onSuccess, onFail)
            return d

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)

    def test_process_withdrawal_online_fiat(self):
        self.create_account('test')

        d = self.cashier.request_withdrawal('test', 'MXN', 'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M', 100000000)

        def onSuccess(withdrawal_id):
            from sputnik import cashier

            d = self.administrator_export.process_withdrawal(withdrawal_id, online=True, admin_username='test_admin')

            def onFail(failure):
                self.assertEqual(failure.value.args[0], "exceptions/cashier/no_automatic_withdrawal")
                from sputnik import models

                withdrawal = self.session.query(models.Withdrawal).filter_by(id=withdrawal_id).one()

                self.assertEqual(self.accountant.component.log, [])
                self.assertEqual(self.bitcoinrpc['BTC'].component.log, [])
                self.assertTrue(withdrawal.pending)

            def onSuccess(result):
                self.assertTrue(False)

            d.addCallbacks(onSuccess, onFail)
            return d

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_process_withdrawal_offline(self):
        self.create_account('test')
        d = self.cashier.request_withdrawal('test', 'MXN', 'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M', 100000000)

        def onSuccess(withdrawal_id):
            d = self.administrator_export.process_withdrawal(withdrawal_id, online=False, admin_username='test_admin')

            def onSuccess(txid):
                from sputnik import models

                withdrawal = self.session.query(models.Withdrawal).filter_by(id=withdrawal_id).one()
                self.assertTrue(self.accountant.component.check_for_calls([('transfer_position',
                                                                  ('pendingwithdrawal',
                                                                   u'MXN',
                                                                   'debit',
                                                                   100000000,
                                                                   u'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M: offline (test_admin)'),
                                                                  {}),
                                                                 ('transfer_position',
                                                                  ('offlinecash',
                                                                   u'MXN',
                                                                   'credit',
                                                                   100000000,
                                                                   'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M: offline (test_admin)'),
                                                                  {})]))

                self.assertEqual(self.bitcoinrpc['BTC'].component.log, [])
                self.assertFalse(withdrawal.pending)

            def onFail(failure):
                self.assertFalse(True)

            d.addCallbacks(onSuccess, onFail)
            return d

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)
        return d


    def test_process_withdrawal_cancel(self):
        self.create_account('test')
        d = self.cashier.request_withdrawal('test', 'MXN', 'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M', 100000000)

        def onSuccess(withdrawal_id):
            d = self.administrator_export.process_withdrawal(withdrawal_id, cancel=True, admin_username='test_admin')

            def onSuccess(txid):
                from sputnik import models

                withdrawal = self.session.query(models.Withdrawal).filter_by(id=withdrawal_id).one()
                self.assertTrue(self.accountant.component.check_for_calls([('transfer_position',
                                                                  ('pendingwithdrawal',
                                                                   u'MXN',
                                                                   'debit',
                                                                   100000000,
                                                                   u'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M: cancel (test_admin)'),
                                                                  {}),
                                                                 ('transfer_position',
                                                                  (u'test',
                                                                   u'MXN',
                                                                   'credit',
                                                                   100000000,
                                                                   'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M: cancel (test_admin)'),
                                                                  {})]
                ))

                self.assertEqual(self.bitcoinrpc['BTC'].component.log, [])
                self.assertFalse(withdrawal.pending)

            def onFail(failure):
                self.assertFalse(True)

            d.addCallbacks(onSuccess, onFail)
            return d

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)
        return d


class TestAccountantExport(TestCashier):
    def test_request_withdrawal_btc_small(self):
        self.create_account('test')
        self.cashier.bitcoinrpc['BTC'].set_balance(1.0)
        d = self.accountant_export.request_withdrawal('test', 'BTC', 'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M', 1000000)

        def onSuccess(withdrawal_id):
            from sputnik import models

            withdrawal = self.session.query(models.Withdrawal).filter_by(id=withdrawal_id).one()
            self.assertFalse(withdrawal.pending)
            self.assertTrue(self.accountant.component.check_for_calls([('transfer_position',
                                                              ('pendingwithdrawal',
                                                               u'BTC',
                                                               'debit',
                                                               1000000,
                                                               u'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M: TXSUCCESS',),
                                                              {}),
                                                             ('transfer_position',
                                                              ('onlinecash',
                                                               u'BTC',
                                                               'credit',
                                                               1000000,
                                                               'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M: TXSUCCESS',),
                                                              {})]))

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_request_withdrawal_btc_larger(self):
        self.create_account('test')
        self.cashier.bitcoinrpc['BTC'].set_balance(1.0)
        d = self.accountant_export.request_withdrawal('test', 'BTC', 'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M', 50000000)

        def onSuccess(withdrawal_id):
            from sputnik import models

            withdrawal = self.session.query(models.Withdrawal).filter_by(id=withdrawal_id).one()
            self.assertTrue(withdrawal.pending)

            self.assertTrue(self.cashier.bitcoinrpc['BTC'].component.check_for_calls([('set_balance', (1.0,), {}), ('getbalance', (), {})]))
            self.assertEqual(self.cashier.accountant.component.log, [])
            self.assertTrue(self.cashier.sendmail.component.check_for_calls([('send_mail',
                                                                    (
                                                                        'Hello anonymous (test),\n\nYour withdrawal request of 0.50 BTC\nhas been submitted for manual processing. It may take up to 24 hours to be processed.\nPlease contact support with any questions, and reference: 1\n',),
                                                                    {'subject': 'Your withdrawal request is pending',
                                                                     'to_address': u'<> anonymous'})]))

        def onFail(failure):
            self.assertTrue(False)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_request_withdrawal_btc_past_hard_limit(self):
        self.create_account('test')
        self.cashier.bitcoinrpc['BTC'].set_balance(100.0)
        d = self.accountant_export.request_withdrawal('test', 'BTC', 'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M', 120000000)

        def onSuccess(withdrawal_id):
            from sputnik import models

            withdrawal = self.session.query(models.Withdrawal).filter_by(id=withdrawal_id).one()
            self.assertTrue(withdrawal.pending)

            self.assertTrue(self.cashier.bitcoinrpc['BTC'].component.check_for_calls([('set_balance', (100.0,), {})]))
            self.assertEqual(self.cashier.accountant.component.log, [])
            self.assertTrue(self.cashier.sendmail.component.check_for_calls([('send_mail',
                                                                    (
                                                                        'Hello anonymous (test),\n\nYour withdrawal request of 1.20 BTC\nhas been submitted for manual processing. It may take up to 24 hours to be processed.\nPlease contact support with any questions, and reference: 1\n',),
                                                                    {'subject': 'Your withdrawal request is pending',
                                                                     'to_address': u'<> anonymous'})]))

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_request_withdrawal_fiat(self):
        self.create_account('test')
        d = self.accountant_export.request_withdrawal('test', 'MXN', 'mzJP8hzfZLs8B5Vx3DLfCQ8sJH3ViuJQ5M', 1200000)

        def onSuccess(withdrawal_id):
            from sputnik import models

            withdrawal = self.session.query(models.Withdrawal).filter_by(id=withdrawal_id).one()
            self.assertTrue(withdrawal.pending)

            self.assertEqual(self.cashier.bitcoinrpc['BTC'].component.log, [])
            self.assertEqual(self.cashier.accountant.component.log, [])
            self.assertTrue(self.cashier.sendmail.component.check_for_calls([('send_mail',
                                                                    (
                                                                        'Hello anonymous (test),\n\nYour withdrawal request of 120.00 MXN\nhas been submitted for manual processing. It may take up to 24 hours to be processed.\nPlease contact support with any questions, and reference: 1\n',),
                                                                    {'subject': 'Your withdrawal request is pending',
                                                                     'to_address': u'<> anonymous'})]))

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)
        return d


class TestCompropagoHook(TestCashier):
    def test_render(self):
        pass


class TestBitcoinNotify(TestCashier):
    """http://stackoverflow.com/questions/5210889/how-to-test-twisted-web-resource-with-trial

    """

    def test_render_GET_little_received(self):
        self.create_account('test', 'NEW_ADDRESS')

        for confirmation in range(0, 6):
            self.cashier.bitcoinrpc['BTC'].receive_at_address('NEW_ADDRESS', 1.23)

        request = DummyRequest([''])
        d = self.render_test_helper(self.bitcoin_notify, request)

        def rendered(ignored):
            self.assertEquals(request.responseCode, 200)
            self.assertEquals("".join(request.written), "OK")
            self.assertTrue(self.accountant.component.check_for_calls([('deposit_cash', ("test", u'NEW_ADDRESS', 123000000L), {})]))

        d.addCallback(rendered)
        return d


    def test_render_GET_insufficient_confirms(self):
        self.create_account('test', 'NEW_ADDRESS')

        for confirmation in range(0, 3):
            self.cashier.bitcoinrpc['BTC'].receive_at_address('NEW_ADDRESS', 1.23)

        request = DummyRequest([''])
        d = self.render_test_helper(self.bitcoin_notify, request)

        def rendered(ignored):
            self.assertEquals(request.responseCode, 200)
            self.assertEquals("".join(request.written), "OK")
            self.assertEqual(self.accountant.component.log, [])

        d.addCallback(rendered)
        return d

    def test_render_GET_various_received(self):
        self.create_account('test', 'ADDRESS_FOR_TEST')
        self.create_account('test2', 'ADDRESS_FOR_TEST2')
        self.create_account('test3', 'ADDRESS_FOR_TEST3')
        self.add_address('test2', 'SECOND_ADDRESS_FOR_TEST2')

        for confirmation in range(0, 3):
            self.cashier.bitcoinrpc['BTC'].receive_at_address('ADDRESS_FOR_TEST', 1.23)
            self.cashier.bitcoinrpc['BTC'].receive_at_address('ADDRESS_FOR_TEST2', 0.2233)

        for confirmation in range(0, 6):
            self.cashier.bitcoinrpc['BTC'].receive_at_address('ADDRESS_FOR_TEST3', 3.4124)
            self.cashier.bitcoinrpc['BTC'].receive_at_address('SECOND_ADDRESS_FOR_TEST2', 4.0)

        request = DummyRequest([''])
        d = self.render_test_helper(self.bitcoin_notify, request)

        def rendered(ignored):
            self.assertEqual(request.responseCode, 200)
            self.assertEqual("".join(request.written), "OK")
            self.assertTrue(
                self.accountant.component.check_for_calls([('deposit_cash', ("test2", 'SECOND_ADDRESS_FOR_TEST2', 400000000L), {}),
                                                 ('deposit_cash', ("test3", 'ADDRESS_FOR_TEST3', 341240000L), {})]
                ))

        d.addCallback(rendered)
        return d
