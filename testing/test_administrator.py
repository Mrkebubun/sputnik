__author__ = 'sameer'

import sys
import os
from test_sputnik import TestSputnik, FakeComponent, FakeSendmail
from pprint import pprint
import re
from twisted.web.test.test_web import DummyRequest
from twisted.internet import defer
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../tools"))


class FakeAccountant(FakeComponent):
    name = "accountant"

    def get_balance_sheet(self):
        self._log_call("get_balance_sheet")
        return defer.succeed({})


class FakeEngine(FakeComponent):
    name = "engine"

    def get_order_book(self):
        self._log_call('get_order_book')
        from sputnik import util

        order_book = {'BUY': {'1': {'errors': "",
                                    'id': 1,
                                    'price': 100,
                                    'quantity': 1,
                                    'quantity_left': 1,
                                    'timestamp': util.dt_to_timestamp(datetime.utcnow()),
                                    'username': None},
                              '3': {'errors': "",
                                    'id': 1,
                                    'price': 95,
                                    'quantity': 2,
                                    'quantity_left': 1,
                                    'timestamp': util.dt_to_timestamp(datetime.utcnow()),
                                    'username': None}},
                      'SELL': {'2': {'errors': "",
                                     'id': 2,
                                     'price': 105,
                                     'quantity': 1,
                                     'quantity_left': 1,
                                     'timestamp': util.dt_to_timestamp(datetime.utcnow()),
                                     'username': None}}}
        return defer.succeed(order_book)


class TestAdministrator(TestSputnik):
    def setUp(self):
        TestSputnik.setUp(self)

        from sputnik import administrator
        from sputnik import accountant
        from sputnik import cashier
        from sputnik import engine2

        accountant = accountant.AdministratorExport(FakeAccountant())
        cashier = cashier.AdministratorExport(FakeComponent())
        engines = {"BTC/MXN": FakeEngine(),
                   "NETS2014": FakeEngine()}
        zendesk_domain = 'testing'

        self.administrator = administrator.Administrator(self.session, accountant, cashier,
                                                         engines,
                                                         zendesk_domain,
                                                         debug=True,
                                                         sendmail=FakeSendmail('test-email@m2.io'),
                                                         base_uri="https://localhost:8888",
                                                         template_dir="../server/sputnik/admin_templates",
                                                         user_limit=50,
                                                         bs_cache_update_period=None)
        self.webserver_export = administrator.WebserverExport(self.administrator)
        self.ticketserver_export = administrator.TicketServerExport(self.administrator)

class TestInternal(TestAdministrator):
    def setUp(self):
        TestAdministrator.setUp(self)
        fees_init = """
fees add LiqRebate 100 -50
fees add NoFee 0 0
fees add HeavyFee 200 200

accounts set marketmaker fees LiqRebate
accounts set randomtrader fees HeavyFee
accounts set m2 fees NoFee

contracts set BTC/MXN fees 50
contracts set NETS2015 fees 350
"""
        self.run_leo(fees_init)

    def test_check_fee_groups(self):
        fees = self.administrator.get_fee_groups()
        fee_problems = self.administrator.check_fee_groups(fees)
        self.assertEqual(fee_problems[0]['aggressive_group'].name, 'NoFee')
        self.assertEqual(fee_problems[0]['passive_group'].name, 'LiqRebate')
        self.assertEqual(fee_problems[0]['total_factor'], -50)

    def test_get_order_book(self):
        # Create one order that is in the order book and one that is not
        from sputnik import models, util

        user = None
        contract = util.get_contract(self.session, 'BTC/MXN')

        in_book_order_1 = models.Order(user, contract, 1, 100, 'BUY')
        in_book_order_1.accepted = True
        in_book_order_1.dispatched = True
        in_book_order_2 = models.Order(user, contract, 1, 105, 'SELL')
        in_book_order_2.is_cancelled = True
        in_book_order_2.accepted = True
        in_book_order_2.dispatched = True
        in_book_order_3 = models.Order(user, contract, 2, 95, 'BUY')
        in_book_order_3.accepted = True
        in_book_order_3.dispatched = True
        not_in_book_order = models.Order(user, contract, 1, 110, 'SELL')
        not_in_book_order.accepted = True
        not_in_book_order.dispatched = True
        self.session.add_all([in_book_order_1, in_book_order_2, in_book_order_3, not_in_book_order])
        self.session.commit()

        d = self.administrator.get_order_book('BTC/MXN')

        def success(order_book):
            self.assertTrue(FakeComponent.check(
                                {'BUY': {'1': {'errors': '',
                                               'id': 1,
                                               'price': 100,
                                               'quantity': 1,
                                               'quantity_left': 1,
                                               'username': None},
                                         '3': {'errors': 'DB quantity_left: 0.00',
                                               'id': 1,
                                               'price': 95,
                                               'quantity': 2,
                                               'quantity_left': 1,
                                               'username': None}},
                                 'SELL': {'2': {'errors': 'Not in DB',
                                                'id': 2,
                                                'price': 105,
                                                'quantity': 1,
                                                'quantity_left': 1,
                                                'username': None},
                                          '4': {'contract': u'BTC/MXN',
                                                'errors': 'Not In Book',
                                                'id': 4,
                                                'is_cancelled': False,
                                                'price': 110,
                                                'quantity': 1,
                                                'quantity_left': 1,
                                                'side': u'SELL',
                                                'username': None
                                          }}}, order_book))

        d.addCallback(success)
        return d


class TestWebserverExport(TestAdministrator):
    def test_get_audit(self):
        audit = self.webserver_export.get_audit()
        for side in ['Asset', 'Liability']:
            for currency in audit[side].keys():
                total = sum([float(x[1]) for x in audit[side][currency]['positions']])
                self.assertAlmostEqual(float(audit[side][currency]['total_fmt']), total)

    def test_make_account_success(self):
        self.add_address(address='new_address_without_user')
        self.assertTrue(self.webserver_export.make_account('new_user', 'new_user_password_hash'))

        from sputnik import models

        user = self.session.query(models.User).filter_by(username='new_user').one()
        self.assertEqual(user.username, 'new_user')
        self.assertEqual(user.password, 'new_user_password_hash')

        # Addresses are assigned at get_current_address, not on account creation

    def test_make_account_no_address(self):
        # should suceed because we don't require that addresseses exist when we do make_Account anymore
        self.assertTrue(self.webserver_export.make_account('new_user', 'new_user_password_hash'))

    def test_make_account_taken(self):
        self.add_address(address='new_address_without_user')
        self.assertTrue(self.webserver_export.make_account('new_user', 'new_user_password_hash'))

        from sputnik import models

        user = self.session.query(models.User).filter_by(username='new_user').one()
        self.assertEqual(user.username, 'new_user')
        self.assertEqual(user.password, 'new_user_password_hash')

        self.add_address(address='second_new_address_without_user')
        from sputnik import administrator

        with self.assertRaisesRegexp(administrator.AdministratorException, 'Username is already taken'):
            self.webserver_export.make_account('new_user', 'new_user_password_hash')

    def test_many_accounts(self):
        from sputnik import administrator

        user_limit = self.administrator.user_limit

        # Make a ton of users, ignore exceptions
        for i in range(0, user_limit):
            self.add_address(address='address_%d' % i)
            try:
                self.webserver_export.make_account('user_%d' % i, 'test_password')
            except administrator.AdministratorException:
                pass

        # Now it should fail
        self.add_address(address='address_%d' % user_limit)
        with self.assertRaisesRegexp(administrator.AdministratorException, 'User limit reached'):
            self.webserver_export.make_account('user_%d' % user_limit, 'test_password')


    def test_change_profile(self):
        self.create_account('test')
        self.webserver_export.change_profile('test', {'nickname': 'user_nickname',
                                                      'email': 'email@m2.io'})
        from sputnik import models

        user = self.session.query(models.User).filter_by(username='test').one()
        self.assertEqual(user.nickname, 'user_nickname')
        self.assertEqual(user.email, 'email@m2.io')

    def test_reset_password_hash(self):
        self.create_account('test', password='null')

        from sputnik import models
        from autobahn.wamp1.protocol import WampCraProtocol

        user = self.session.query(models.User).filter_by(username='test').one()
        [salt, old_password_hash] = user.password.split(':')

        extra = {"salt": salt, "keylen": 32, "iterations": 1000}
        password = WampCraProtocol.deriveKey('test', extra)
        new_password_hash = '%s:%s' % (salt, password)

        self.assertTrue(self.webserver_export.reset_password_hash('test', old_password_hash, new_password_hash))
        user = self.session.query(models.User).filter_by(username='test').one()
        self.assertEqual(user.password, "%s:%s" % (salt, new_password_hash))

    def test_reset_password_hash_bad(self):
        self.create_account('test', password='null')

        from sputnik import models
        from autobahn.wamp1.protocol import WampCraProtocol

        user = self.session.query(models.User).filter_by(username='test').one()
        [salt, old_password_hash] = user.password.split(':')

        extra = {"salt": salt, "keylen": 32, "iterations": 1000}
        password = WampCraProtocol.deriveKey('test', extra)
        new_password_hash = '%s:%s' % (salt, password)

        from sputnik import administrator

        with self.assertRaisesRegexp(administrator.AdministratorException, "Password does not match"):
            self.webserver_export.reset_password_hash('test', "bad_old_hash", new_password_hash)

    def test_reset_password_hash_bad_token(self):
        self.create_account('test', password='null')

        from sputnik import models
        from autobahn.wamp1.protocol import WampCraProtocol

        user = self.session.query(models.User).filter_by(username='test').one()
        [salt, old_password_hash] = user.password.split(':')

        extra = {"salt": salt, "keylen": 32, "iterations": 1000}
        password = WampCraProtocol.deriveKey('test', extra)
        new_password_hash = '%s:%s' % (salt, password)

        from sputnik import administrator

        with self.assertRaisesRegexp(administrator.AdministratorException, "No such token found"):
            self.assertTrue(
                self.webserver_export.reset_password_hash('test', None, new_password_hash, token='bad_token'))

    def test_get_reset_token_success(self):
        self.create_account('test')
        self.assertTrue(self.webserver_export.get_reset_token('test'))

        # Look for the email
        message = self.administrator.sendmail.log[0][1][0]
        match = re.search('#function=change_password_token&username=test&token=(.*)$', message)
        self.assertIsNotNone(match)
        token_str = match.group(1)

        # A token was created
        from sputnik import models

        token = self.session.query(models.ResetToken).filter_by(username='test').one()
        self.assertEqual(token.username, 'test')
        self.assertEqual(token.token, token_str)

    def test_reset_password_hash_token(self):
        self.create_account('test', password='null')
        self.assertTrue(self.webserver_export.get_reset_token('test'))

        # Look for the email
        message = self.administrator.sendmail.log[0][1][0]
        match = re.search('#function=change_password_token&username=test&token=(.*)$', message)
        self.assertIsNotNone(match)
        token_str = match.group(1)

        # A token was created
        from sputnik import models

        token = self.session.query(models.ResetToken).filter_by(username='test').one()
        self.assertEqual(token.username, 'test')
        self.assertEqual(token.token, token_str)

        from autobahn.wamp1.protocol import WampCraProtocol

        user = self.session.query(models.User).filter_by(username='test').one()
        [salt, old_password_hash] = user.password.split(':')

        extra = {"salt": salt, "keylen": 32, "iterations": 1000}
        password = WampCraProtocol.deriveKey('test', extra)
        new_password_hash = '%s:%s' % (salt, password)

        self.assertTrue(self.webserver_export.reset_password_hash('test', None, new_password_hash, token=token_str))
        user = self.session.query(models.User).filter_by(username='test').one()
        self.assertEqual(user.password, "%s:%s" % (salt, new_password_hash))

    def test_get_reset_token_no_user(self):
        # Should fail silently
        self.assertTrue(self.webserver_export.get_reset_token('test'))

        # No mail should have been sent
        self.assertEqual(len(self.administrator.sendmail.log), 0)

        # No reset tokens should be created
        from sputnik import models

        self.assertEqual(self.session.query(models.ResetToken).count(), 0)

    def test_register_support_ticket(self):
        self.create_account('test')
        nonce = self.webserver_export.request_support_nonce('test', 'Compliance')
        self.webserver_export.register_support_ticket('test', nonce, 'Compliance', 'KEY')

        from sputnik import models

        ticket = self.session.query(models.SupportTicket).filter_by(username='test', nonce=nonce).one()
        self.assertEqual(ticket.nonce, nonce)
        self.assertEqual(ticket.type, 'Compliance')
        self.assertEqual(ticket.foreign_key, 'KEY')

    def test_request_support_nonce(self):
        self.create_account('test')
        nonce = self.webserver_export.request_support_nonce('test', 'Compliance')

        from sputnik import models

        ticket = self.session.query(models.SupportTicket).filter_by(username='test', nonce=nonce).one()
        self.assertEqual(ticket.nonce, nonce)
        self.assertEqual(ticket.type, 'Compliance')
        self.assertIsNone(ticket.foreign_key)


class TestTicketServerExport(TestAdministrator):
    def test_check_support_nonce(self):
        self.create_account('test')
        nonce = self.webserver_export.request_support_nonce('test', 'Compliance')
        self.assertTrue(self.ticketserver_export.check_support_nonce('test', nonce, 'Compliance'))

    def test_check_support_nonce_bad(self):
        self.create_account('test')
        from sputnik import administrator

        with self.assertRaisesRegexp(administrator.AdministratorException, 'Invalid support nonce'):
            self.ticketserver_export.check_support_nonce('test', 'bad_nonce', 'Compliance')

    def test_register_support_ticket(self):
        self.create_account('test')
        nonce = self.webserver_export.request_support_nonce('test', 'Compliance')
        self.ticketserver_export.register_support_ticket('test', nonce, 'Compliance', 'KEY')

        from sputnik import models

        ticket = self.session.query(models.SupportTicket).filter_by(username='test', nonce=nonce).one()
        self.assertEqual(ticket.nonce, nonce)
        self.assertEqual(ticket.type, 'Compliance')
        self.assertEqual(ticket.foreign_key, 'KEY')

# Not quite a Dummy
class StupidRequest(DummyRequest):
    clientproto = 'HTTP/1.1'
    code = 123
    sentLength = None

    def __init__(self, postpath, session=None, path=None, args=None):
        DummyRequest.__init__(self, postpath, session=session)
        self.path = path
        self.args = args
        self.redirect_url = None

    def getUser(self):
        return 'admin'

    def redirect(self, url):
        self.redirect_url = url


class TestAdministratorWebUI(TestAdministrator):
    def setUp(self):
        TestAdministrator.setUp(self)

        from sputnik import administrator
        from twisted.web.guard import DigestCredentialFactory

        digest_factory = DigestCredentialFactory('md5', 'Sputnik Admin Interface')
        self.web_ui_factory = lambda level: administrator.AdminWebUI(self.administrator, 'admin', level, digest_factory)

    def test_root_l0(self):
        request = StupidRequest([''], path='/')
        d = self.render_test_helper(self.web_ui_factory(0), request)

        def rendered(ignored):
            self.assertRegexpMatches(''.join(request.written), '<title>Admin Tasks</title>')

        d.addCallback(rendered)
        return d

    def test_root_l1(self):
        request = StupidRequest([''], path='/')
        d = self.render_test_helper(self.web_ui_factory(1), request)

        def rendered(ignored):
            self.assertRegexpMatches(''.join(request.written), '<title>User List</title>')

        d.addCallback(rendered)
        return d

    def test_reset_admin_password_no_prev(self):
        request = StupidRequest([''],
                                path='/reset_admin_password',
                                args={'username': ['admin'],
                                      'old_password': [''],
                                      'new_password': ['admin']})
        admin_ui = self.web_ui_factory(0)
        d = self.render_test_helper(admin_ui, request)

        def rendered(ignored):
            self.assertRegexpMatches(request.redirect_url, 'admin')
            from sputnik import models

            admin_user = self.session.query(models.AdminUser).filter_by(username='admin').one()
            self.assertEqual(admin_user.password_hash, admin_ui.calc_ha1('admin', username='admin'))

        d.addCallback(rendered)
        return d

    def test_reset_admin_password_no_prev(self):
        request = StupidRequest([''],
                                path='/reset_admin_password',
                                args={'username': ['admin'],
                                      'old_password': [''],
                                      'new_password': ['admin']})
        admin_ui = self.web_ui_factory(0)
        d = self.render_test_helper(admin_ui, request)

        def rendered(ignored):
            request = StupidRequest([''],
                                    path='/reset_admin_password',
                                    args={'username': ['admin'],
                                          'old_password': ['admin'],
                                          'new_password': ['test']})
            d = self.render_test_helper(self.web_ui_factory(0), request)

            def rendered(ignored):
                self.assertRegexpMatches(request.redirect_url, 'admin')
                from sputnik import models

                admin_user = self.session.query(models.AdminUser).filter_by(username='admin').one()
                self.assertEqual(admin_user.password_hash, admin_ui.calc_ha1('test', username='admin'))

            d.addCallback(rendered)

        d.addCallback(rendered)
        return d


    def test_user_details(self):
        self.create_account('test')
        request = StupidRequest([''],
                                path='/user_details',
                                args={'username': ['test']})
        d = self.render_test_helper(self.web_ui_factory(1), request)

        def rendered(ignored):
            self.assertRegexpMatches(''.join(request.written), '<title>%s</title>' % 'test')

        d.addCallback(rendered)
        return d

    def test_user_orders(self):
        self.create_account('test')
        request = StupidRequest([''], path='/user_orders',
                                args={'username': ['test'], 'page': ['0']})
        d = self.render_test_helper(self.web_ui_factory(1), request)

        def rendered(ignored):
            self.assertRegexpMatches(''.join(request.written), 'Orders for %s' % 'test')

        d.addCallback(rendered)
        return d

    def test_user_postings(self):
        self.create_account('test')
        request = StupidRequest([''], path='/user_postings',
                                args={'username': ['test'], 'page': ['0'],
                                      'ticker': ['BTC']})
        d = self.render_test_helper(self.web_ui_factory(1), request)

        def rendered(ignored):
            match = '<table class="table table-striped table-hover" id="postings_BTC">'
            self.assertRegexpMatches(''.join(request.written), match)

        d.addCallback(rendered)
        return d

    def test_rescan_address(self):
        self.create_account('test', 'address_test')
        request = StupidRequest([''],
                                path='/rescan_address',
                                args={'address': ['address_test'],
                                      'username': ['test']})
        d = self.render_test_helper(self.web_ui_factory(1), request)

        def rendered(ignored):
            self.assertRegexpMatches(request.redirect_url, 'user_details')
            self.assertTrue(
                self.administrator.cashier.component.check_for_calls([('rescan_address', ('address_test',), {})]))


        d.addCallback(rendered)
        return d

    def test_order_book(self):
        request = StupidRequest([''],
                                path='/order_book',
                                args={'ticker': ['BTC/MXN']})

        d = self.render_test_helper(self.web_ui_factory(5), request)

        def rendered(ignored):
            self.assertRegexpMatches(''.join(request.written), '<title>BTC/MXN</title>')

        d.addCallback(rendered)
        return d

    def test_admin(self):
        request = StupidRequest([''],
                                path='/admin')
        d = self.render_test_helper(self.web_ui_factory(1), request)

        def rendered(ignored):
            self.assertRegexpMatches(''.join(request.written), '<title>Admin Tasks</title>')


        d.addCallback(rendered)
        return d

    def test_contracts(self):
        request = StupidRequest([''],
                                path='/contracts')
        d = self.render_test_helper(self.web_ui_factory(1), request)

        def rendered(ignored):
            self.assertRegexpMatches(''.join(request.written), '<title>Contracts</title>')


        d.addCallback(rendered)
        return d

    def test_reset_password(self):
        self.create_account('test')

        request = StupidRequest([''],
                                path='/reset_password',
                                args={'username': ['test'],
                                      'new_password': ['new_pass']})

        d = self.render_test_helper(self.web_ui_factory(2), request)

        def rendered(ignored):
            self.assertRegexpMatches(request.redirect_url, 'user_details')
            from sputnik import models

            user = self.session.query(models.User).filter_by(username='test').one()
            [salt, hash] = user.password.split(':')

            extra = {"salt": salt, "keylen": 32, "iterations": 1000}
            from autobahn.wamp1.protocol import WampCraProtocol

            password = WampCraProtocol.deriveKey('new_pass', extra)
            self.assertEqual(hash, password)

        d.addCallback(rendered)
        return d

    def test_permission_groups(self):
        request = StupidRequest([''],
                                path='/permission_groups')
        d = self.render_test_helper(self.web_ui_factory(2), request)

        def rendered(ignored):
            self.assertRegexpMatches(''.join(request.written), '<title>Permissions</title>')


        d.addCallback(rendered)
        return d


    def test_change_permission_group(self):
        self.create_account('test')
        from sputnik import models

        groups = self.session.query(models.PermissionGroup).all()
        import random

        new_group = random.choice(groups)
        new_id = new_group.id

        request = StupidRequest([''], path='/change_permission_group',
                                args={'username': ['test'],
                                      'id': [new_id]})
        d = self.render_test_helper(self.web_ui_factory(2), request)

        def rendered(ignored):
            self.assertRegexpMatches(request.redirect_url, 'user_details')
            self.assertTrue(
                self.administrator.accountant.component.check_for_calls(
                    [('change_permission_group', ('test', new_id), {})]))

        d.addCallback(rendered)
        return d


    def test_ledger(self):
        pass

    def test_new_permission_group(self):
        request = StupidRequest([''],
                                path='/new_permission_group',
                                args={'name': ['New Test Group'],
                                      'permissions': ['trade', 'deposit']})
        d = self.render_test_helper(self.web_ui_factory(4), request)

        def rendered(ignored):
            self.assertRegexpMatches(request.redirect_url, 'permission_groups')

            from sputnik import models

            group = self.session.query(models.PermissionGroup).filter_by(name='New Test Group').one()

            self.assertTrue(group.deposit)
            self.assertFalse(group.withdraw)
            self.assertTrue(group.trade)
            self.assertFalse(group.login)

        d.addCallback(rendered)
        return d

    def test_process_withdrawal(self):
        self.create_account('test')
        request = StupidRequest([''],
                                path='/process_withdrawal',
                                args={'username': ['test'],
                                      'id': ['5'],
                                      'online': True})
        d = self.render_test_helper(self.web_ui_factory(4), request)

        def rendered(ignored):
            self.assertRegexpMatches(request.redirect_url, 'user_details')
            self.assertTrue(self.administrator.cashier.component.check_for_calls(
                [('process_withdrawal', (5,), {'cancel': False, 'online': True})]))

        d.addCallback(rendered)
        return d

    def test_withdrawals(self):
        pass

    def test_deposits(self):
        pass

    def test_manual_deposit(self):
        pass

    def test_admin_list(self):
        pass

    def test_new_admin_user(self):
        pass

    def test_set_admin_level(self):
        pass

    def test_admin_password(self):
        pass

    def test_transfer_position(self):
        pass

    def test_adjust_position(self):
        pass

    def test_balance_sheet(self):
        request = StupidRequest([''],
                                path='/balance_sheet')
        d = self.render_test_helper(self.web_ui_factory(3), request)

        def rendered(ignored):
            self.assertRegexpMatches(''.join(request.written), '<title>Balance Sheet</title>')


        d.addCallback(rendered)
        return d
