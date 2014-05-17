import sys
import os
from twisted.internet import defer
from test_sputnik import TestSputnik, FakeProxy, FakeSendmail
from pprint import pprint

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../tools"))


class FakeBitcoin(FakeProxy):
    received = {}
    balance = 0.0

    def getnewaddress(self):
        return defer.succeed({'result': "NEW_TEST_ADDRESS"})

    def getreceivedbyaddress(self, address, minimum_confirmations):
        if address in self.received:
            if self.received[address]['confirmations'] >= minimum_confirmations:
                return defer.succeed({'result': self.received[address]['amount']})

        return defer.suceed(0.0)

    def listreceivedbyaddress(self, minimum_confirmations):
        received = []
        from bitcoinrpc.data import AddressInfo


        for address, info in self.received.iteritems():
            if info['confirmations'] >= minimum_confirmations:
                received.append(AddressInfo(address=address,
                                            account='',
                                            amount=info['amount'],
                                            confirmations=info['confirmations']))
        return defer.succeed({'result': received})


    def getbalance(self):
        return defer.succeed({'result': self.balance})

    def sendtoaddress(self, address, amount):
        return defer.succeed("TXSUCCESS")

    # Utility functions for tester
    def receive_at_address(self, address, amount):
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
        self.balance = amount


class TestCashier(TestSputnik):
    def setUp(self):
        TestSputnik.setUp(self)

        from sputnik import cashier

        self.accountant = FakeProxy()
        self.bitcoinrpc = {'BTC': FakeBitcoin()}
        self.compropago = FakeProxy()
        self.sendmail = FakeSendmail('test-email@m2.io')
        self.cashier = cashier.Cashier(self.session, self.accountant,
                                       self.bitcoinrpc,
                                       self.compropago,
                                       cold_wallet_period=None,
                                       sendmail=self.sendmail,
                                       template_dir="../server/sputnik/admin_templates",
                                       minimum_confirmations=6)

        self.administrator_export = cashier.AdministratorExport(self.cashier)
        self.webserver_export = cashier.WebserverExport(self.cashier)
        self.accountant_export = cashier.AccountantExport(self.cashier)
        self.compropago_hook = cashier.CompropagoHook(self.cashier)
        self.bitcoin_notify = cashier.BitcoinNotify(self.cashier)


class TestWebserverExport(TestCashier):
    def test_get_new_address_already_exists(self):
        self.create_account('test')
        self.add_address(address="NEW_ADDRESS_EXISTS")
        new_address = self.webserver_export.get_new_address('test', 'BTC')
        self.assertEqual(new_address, 'NEW_ADDRESS_EXISTS')

        from sputnik import models

        address = self.session.query(models.Addresses).filter_by(username='test', active=True).one()
        self.assertEqual(address.address, 'NEW_ADDRESS_EXISTS')

    def test_get_new_address_new(self):
        self.create_account('test')
        new_address = self.webserver_export.get_new_address('test', 'BTC')
        self.assertEqual(new_address, 'NEW_TEST_ADDRESS')

        from sputnik import models

        address = self.session.query(models.Addresses).filter_by(username='test', active=True).one()
        self.assertEqual(address.address, 'NEW_TEST_ADDRESS')

    def test_get_new_address_fiat(self):
        self.create_account('test')
        new_address = self.webserver_export.get_new_address('test', 'MXN')

        from sputnik import models

        address = self.session.query(models.Addresses).filter_by(username='test', active=True).one()
        self.assertEqual(address.address, new_address)

    def test_get_current_address_exists(self):
        self.create_account('test', 'STARTING_ADDRESS')
        current_address = self.webserver_export.get_current_address('test', 'BTC')
        self.assertEqual(current_address, 'STARTING_ADDRESS')

    def test_get_current_address_not_exists(self):
        self.create_account('test')
        current_address = self.webserver_export.get_current_address('test', 'BTC')
        self.assertEqual(current_address, 'NEW_TEST_ADDRESS')

        from sputnik import models

        address = self.session.query(models.Addresses).filter_by(username='test', active=True).one()
        self.assertEqual(address.address, 'NEW_TEST_ADDRESS')

    def test_get_current_address_not_exists_fiat(self):
        self.create_account('test')
        current_address = self.webserver_export.get_current_address('test', 'MXN')

        from sputnik import models

        address = self.session.query(models.Addresses).filter_by(username='test', active=True).one()
        self.assertEqual(address.address, current_address)

    def test_get_deposit_instructions_btc(self):
        instructions = self.webserver_export.get_deposit_instructions('BTC')
        self.assertEqual(instructions, "Deposit your crypto-currency normally")

    def test_get_deposit_instructions_fiat(self):
        instructions = self.webserver_export.get_deposit_instructions('MXN')
        self.assertEqual(instructions,
                         "Mail a check to X or send a wire to Y and put this key into the comments/memo field")


class TestAdministratorExport(TestCashier):
    def test_rescan_address_with_deposit(self):
        self.create_account('test', 'TEST_ADDRESS')
        for confirmation in range(0, 6):
            self.cashier.bitcoinrpc['BTC'].receive_at_address('TEST_ADDRESS', 1.23)

        self.administrator_export.rescan_address('TEST_ADDRESS')
        self.assertTrue(self.cashier.accountant.check_for_calls([('deposit_cash', ('TEST_ADDRESS', 123000000L), {})]))

    def test_rescan_address_with_deposit_insufficient_confirms(self):
        self.create_account('test', 'TEST_ADDRESS_2')
        for confirmation in range(0, 5):
            self.cashier.bitcoinrpc['BTC'].receive_at_address('TEST_ADDRESS_2', 1.23)

        self.administrator_export.rescan_address('TEST_ADDRESS_2')
        self.assertEquals(self.cashier.accountant.log, [])

    def test_rescan_address_with_nodeposit(self):
        self.create_account('test', 'TEST_ADDRESS_3')

        self.administrator_export.rescan_address('TEST_ADDRESS_3')
        self.assertEquals(self.cashier.accountant.log, [])

    def test_process_withdrawal_online_have_cash(self):
        self.create_account('test')
        self.cashier.request_withdrawal('test', 'BTC', 'WITHDRAWAL_ADDRESS', 1000000)
        self.cashier.bitcoinrpc['BTC'].set_balance(0.01)

        from sputnik import models

        withdrawal_id = self.session.query(models.Withdrawal).filter_by(address='WITHDRAWAL_ADDRESS').one().id

        self.administrator_export.process_withdrawal(withdrawal_id, online=True)

        withdrawal = self.session.query(models.Withdrawal).filter_by(address='WITHDRAWAL_ADDRESS').one()
        self.assertTrue(self.accountant.check_for_calls([('transfer_position',
                                                          (u'BTC', 'pendingwithdrawal', 'onlinecash', 1000000,
                                                           u'WITHDRAWAL_ADDRESS'),
                                                          {})]))
        self.assertTrue(self.bitcoinrpc['BTC'].check_for_calls([('sendtoaddress', (u'WITHDRAWAL_ADDRESS', 0.01), {})]))
        self.assertFalse(withdrawal.pending)

    def test_process_withdrawal_online_no_cash(self):
        self.create_account('test')
        self.cashier.request_withdrawal('test', 'BTC', 'WITHDRAWAL_ADDRESS', 1000000)
        self.cashier.bitcoinrpc['BTC'].set_balance(0.0)

        from sputnik import models, cashier

        withdrawal_id = self.session.query(models.Withdrawal).filter_by(address='WITHDRAWAL_ADDRESS').one().id

        with self.assertRaisesRegexp(cashier.CashierException, 'Insufficient funds'):
            self.administrator_export.process_withdrawal(withdrawal_id, online=True)

        withdrawal = self.session.query(models.Withdrawal).filter_by(address='WITHDRAWAL_ADDRESS').one()

        self.assertEqual(self.accountant.log, [])
        self.assertEqual(self.bitcoinrpc['BTC'].log, [])
        self.assertTrue(withdrawal.pending)

    def test_process_withdrawal_online_fiat(self):
        self.create_account('test')
        self.cashier.request_withdrawal('test', 'MXN', 'WITHDRAWAL_ADDRESS', 1000000)

        from sputnik import models, cashier

        withdrawal_id = self.session.query(models.Withdrawal).filter_by(address='WITHDRAWAL_ADDRESS').one().id

        with self.assertRaisesRegexp(cashier.CashierException, 'No automatic withdrawals'):
            self.administrator_export.process_withdrawal(withdrawal_id, online=True)

        withdrawal = self.session.query(models.Withdrawal).filter_by(address='WITHDRAWAL_ADDRESS').one()

        self.assertEqual(self.accountant.log, [])
        self.assertEqual(self.bitcoinrpc['BTC'].log, [])
        self.assertTrue(withdrawal.pending)

    def test_process_withdrawal_offline(self):
        self.create_account('test')
        self.cashier.request_withdrawal('test', 'MXN', 'WITHDRAWAL_ADDRESS', 1000000)

        from sputnik import models

        withdrawal_id = self.session.query(models.Withdrawal).filter_by(address='WITHDRAWAL_ADDRESS').one().id

        self.administrator_export.process_withdrawal(withdrawal_id, online=False)
        withdrawal = self.session.query(models.Withdrawal).filter_by(address='WITHDRAWAL_ADDRESS').one()

        self.assertTrue(self.accountant.check_for_calls([('transfer_position',
                                                          (u'MXN',
                                                           'pendingwithdrawal',
                                                           'offlinecash',
                                                           1000000,
                                                           u'WITHDRAWAL_ADDRESS'),
                                                          {})]))

        self.assertEqual(self.bitcoinrpc['BTC'].log, [])
        self.assertFalse(withdrawal.pending)


    def test_process_withdrawal_cancel(self):
        self.create_account('test')
        self.cashier.request_withdrawal('test', 'MXN', 'WITHDRAWAL_ADDRESS', 1000000)

        from sputnik import models

        withdrawal_id = self.session.query(models.Withdrawal).filter_by(address='WITHDRAWAL_ADDRESS').one().id

        self.administrator_export.process_withdrawal(withdrawal_id, cancel=True)
        withdrawal = self.session.query(models.Withdrawal).filter_by(address='WITHDRAWAL_ADDRESS').one()

        self.assertTrue(self.accountant.check_for_calls([('transfer_position',
                                                          (u'MXN',
                                                           'pendingwithdrawal',
                                                           'test',
                                                           1000000,
                                                           u'WITHDRAWAL_ADDRESS'),
                                                          {})]))

        self.assertEqual(self.bitcoinrpc['BTC'].log, [])
        self.assertFalse(withdrawal.pending)


class TestAccountantExport(TestCashier):
    def test_request_withdrawal_btc_small(self):
        self.create_account('test')
        self.cashier.bitcoinrpc['BTC'].set_balance(1.0)
        self.accountant_export.request_withdrawal('test', 'BTC', 'WITHDRAWAL_ADDRESS', 1000000)

        from sputnik import models

        withdrawal = self.session.query(models.Withdrawal).filter_by(address='WITHDRAWAL_ADDRESS').one()
        self.assertFalse(withdrawal.pending)

        self.assertTrue(
            self.cashier.bitcoinrpc['BTC'].check_for_calls([('sendtoaddress', (u'WITHDRAWAL_ADDRESS', 0.01), {})]))
        self.assertTrue(self.cashier.accountant.check_for_calls([('transfer_position',
                                                                  (u'BTC', 'pendingwithdrawal', 'onlinecash', 1000000,
                                                                   u'WITHDRAWAL_ADDRESS'),
                                                                  {})]))

    def test_request_withdrawal_btc_larger(self):
        self.create_account('test')
        self.cashier.bitcoinrpc['BTC'].set_balance(1.0)
        self.accountant_export.request_withdrawal('test', 'BTC', 'WITHDRAWAL_ADDRESS', 50000000)

        from sputnik import models

        withdrawal = self.session.query(models.Withdrawal).filter_by(address='WITHDRAWAL_ADDRESS').one()
        self.assertTrue(withdrawal.pending)

        self.assertEqual(self.cashier.bitcoinrpc['BTC'].log, [])
        self.assertEqual(self.cashier.accountant.log, [])
        self.assertTrue(self.cashier.sendmail.check_for_calls([('send_mail',
                                                                (
                                                                    'Hello anonymous (test),\n\nYour withdrawal request of 0.50 BTC\nhas been submitted for manual processing. It may take up to 24 hours to be processed.\nPlease contact support with any questions, and reference: 1\n',),
                                                                {'subject': 'Your withdrawal request is pending',
                                                                 'to_address': u'<> anonymous'})]))

    def test_request_withdrawal_btc_past_hard_limit(self):
        self.create_account('test')
        self.cashier.bitcoinrpc['BTC'].set_balance(100.0)
        d = self.accountant_export.request_withdrawal('test', 'BTC', 'WITHDRAWAL_ADDRESS', 120000000)

        def onSuccess(result):
            from sputnik import models

            withdrawal = self.session.query(models.Withdrawal).filter_by(address='WITHDRAWAL_ADDRESS').one()
            self.assertTrue(withdrawal.pending)

            self.assertEqual(self.cashier.bitcoinrpc['BTC'].log, [])
            self.assertEqual(self.cashier.accountant.log, [])
            self.assertTrue(self.cashier.sendmail.check_for_calls([('send_mail',
                                                                    (
                                                                        'Hello anonymous (test),\n\nYour withdrawal request of 1.20 BTC\nhas been submitted for manual processing. It may take up to 24 hours to be processed.\nPlease contact support with any questions, and reference: 1\n',),
                                                                    {'subject': 'Your withdrawal request is pending',
                                                                     'to_address': u'<> anonymous'})]))

        def onFail(failure):
            self.assertFalse(True)

        d.addCallbacks(onSuccess, onFail)

    def test_request_withdrawal_fiat(self):
        self.create_account('test')
        self.accountant_export.request_withdrawal('test', 'MXN', 'WITHDRAWAL_ADDRESS', 12000)

        from sputnik import models

        withdrawal = self.session.query(models.Withdrawal).filter_by(address='WITHDRAWAL_ADDRESS').one()
        self.assertTrue(withdrawal.pending)

        self.assertEqual(self.cashier.bitcoinrpc['BTC'].log, [])
        self.assertEqual(self.cashier.accountant.log, [])
        self.assertTrue(self.cashier.sendmail.check_for_calls([('send_mail',
                                                                (
                                                                    'Hello anonymous (test),\n\nYour withdrawal request of 120.00 MXN\nhas been submitted for manual processing. It may take up to 24 hours to be processed.\nPlease contact support with any questions, and reference: 1\n',),
                                                                {'subject': 'Your withdrawal request is pending',
                                                                 'to_address': u'<> anonymous'})]))


class TestCompropagoHook(TestCashier):
    def test_render(self):
        pass


class TestBitcoinNotify(TestCashier):
    def test_render_GET_little_received(self):
        self.create_account('test', 'NEW_ADDRESS')

        for confirmation in range(0, 6):
            self.cashier.bitcoinrpc['BTC'].receive_at_address('NEW_ADDRESS', 1.23)

        self.assertEqual(self.bitcoin_notify.render_GET(None), "OK")
        self.assertTrue(self.accountant.check_for_calls([('deposit_cash', (u'NEW_ADDRESS', 123000000L), {})]))

    def test_render_GET_insufficient_confirms(self):
        self.create_account('test', 'NEW_ADDRESS')

        for confirmation in range(0, 3):
            self.cashier.bitcoinrpc['BTC'].receive_at_address('NEW_ADDRESS', 1.23)

        self.assertEqual(self.bitcoin_notify.render_GET(None), "OK")
        self.assertEqual(self.accountant.log, [])

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

        self.assertEqual(self.bitcoin_notify.render_GET(None), "OK")
        self.assertTrue(self.accountant.check_for_calls([('deposit_cash', ('SECOND_ADDRESS_FOR_TEST2', 400000000L), {}),
                                                         ('deposit_cash', ('ADDRESS_FOR_TEST3', 341240000L), {})]
        ))
