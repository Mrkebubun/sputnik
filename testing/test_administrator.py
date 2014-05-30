__author__ = 'sameer'

import sys
import os
from test_sputnik import TestSputnik, FakeProxy, FakeSendmail
from pprint import pprint
import re
from twisted.web.test.test_web import DummyRequest

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../tools"))




class TestAdministrator(TestSputnik):
    def setUp(self):
        TestSputnik.setUp(self)

        from sputnik import administrator
        accountant = FakeProxy()
        cashier = FakeProxy()
        zendesk_domain = 'testing'

        self.administrator = administrator.Administrator(self.session, accountant, cashier, zendesk_domain,
                                                         debug=True,
                                                         sendmail=FakeSendmail('test-email@m2.io'),
                                                         base_uri="https://localhost:8888",
                                                         template_dir="../server/sputnik/admin_templates",
                                                         user_limit=50)
        self.webserver_export = administrator.WebserverExport(self.administrator)
        self.ticketserver_export = administrator.TicketServerExport(self.administrator)

class TestWebserverExport(TestAdministrator):
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

        extra = {"salt":salt, "keylen":32, "iterations":1000}
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

        extra = {"salt":salt, "keylen":32, "iterations":1000}
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

        extra = {"salt":salt, "keylen":32, "iterations":1000}
        password = WampCraProtocol.deriveKey('test', extra)
        new_password_hash = '%s:%s' % (salt, password)

        from sputnik import administrator
        with self.assertRaisesRegexp(administrator.AdministratorException, "No such token found"):
            self.assertTrue(self.webserver_export.reset_password_hash('test', None, new_password_hash, token='bad_token'))

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

        extra = {"salt":salt, "keylen":32, "iterations":1000}
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

    def getUser(self):
        return 'admin'

class TestAdministratorWebUI(TestAdministrator):

    def setUp(self):
        TestAdministrator.setUp(self)

        from sputnik import administrator
        from twisted.web.guard import DigestCredentialFactory
        digest_factory = DigestCredentialFactory('md5', 'Sputnik Admin Interface')
        self.web_ui_factory = lambda level: administrator.AdminWebUI(self.administrator, 'admin', level, digest_factory)

    def test_root_l0(self):
        request = StupidRequest([''], path = '/')
        d = self.render_test_helper(self.web_ui_factory(0), request)
        def rendered(ignored):
            self.assertRegexpMatches(''.join(request.written), '<title>Admin Tasks</title>')

        d.addCallback(rendered)
        return d

    def test_root_l1(self):
        request = StupidRequest([''], path = '/')
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
        d = self.render_test_helper(self.web_ui_factory(0), request)
        def rendered(ignored):
            self.assertRegexpMatches(''.join(request.written), '<title>Admin Tasks</title>')

        d.addCallback(rendered)
        return d


    def test_reset_admin_password_no_prev(self):
        request = StupidRequest([''],
                                path='/reset_admin_password',
                                args={'username': ['admin'],
                                      'old_password': [''],
                                      'new_password': ['admin']})
        d = self.render_test_helper(self.web_ui_factory(0), request)
        def rendered(ignored):
            request = StupidRequest([''],
                                    path='/reset_admin_password',
                                    args={'username': ['admin'],
                                          'old_password': ['admin'],
                                          'new_password': ['test']})
            d = self.render_test_helper(self.web_ui_factory(0), request)
            def rendered(ignored):
                self.assertRegexpMatches(''.join(request.written), '<title>Admin Tasks</title>')

            d.addCallback(rendered)

        d.addCallback(rendered)
        return d


    def test_user_details(self):
        self.create_account('test')
        request = StupidRequest([''],
                                path='/user_details',
                                args={'username':['test']})
        d = self.render_test_helper(self.web_ui_factory(1), request)
        def rendered(ignored):
            self.assertRegexpMatches(''.join(request.written), '<title>%s</title>' % 'test')

        d.addCallback(rendered)
        return d

    def test_rescan_address(self):
        pass

    def test_admin(self):
        pass

    def test_contracts(self):
        pass

    def test_reset_password(self):
        pass

    def test_permission_groups(self):
        pass

    def test_change_permission_group(self):
        pass

    def test_balance_sheet(self):
        pass

    def test_ledger(self):
        pass

    def test_new_permission_group(self):
        pass

    def test_process_withdrawal(self):
        pass

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

    def test_force_reset_admin_password(self):
        pass

    def test_transfer_position(self):
        pass

    def test_adjust_position(self):
        pass

