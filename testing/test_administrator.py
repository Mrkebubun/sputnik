__author__ = 'sameer'

import sys
import os
from test_sputnik import TestSputnik, FakeProxy, FakeSendmail
from pprint import pprint
import re

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
                                                         template_dir="../server/sputnik/admin_templates")
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


        address = self.session.query(models.Addresses).filter_by(address='new_address_without_user').one()
        self.assertEqual(address.username, 'new_user')

    def test_make_account_no_address(self):
        # should fail
        from sputnik import administrator
        with self.assertRaisesRegexp(administrator.AdministratorException, 'out of addresses'):
            self.webserver_export.make_account('new_user', 'new_user_password_hash')

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
        # force a smaller user limit
        administrator.USER_LIMIT = 50

        user_limit = administrator.USER_LIMIT

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
        pass

    def test_get_reset_token_success(self):
        self.create_account('test')
        self.assertTrue(self.webserver_export.get_reset_token('test'))

        # Look for the email
        message = self.administrator.sendmail.log[0][0]
        match = re.search('#function=change_password_token&username=test&token=(.*)$', message)
        self.assertIsNotNone(match)
        token_str = match.group(1)

        # A token was created
        from sputnik import models
        token = self.session.query(models.ResetToken).filter_by(username='test').one()
        self.assertEqual(token.username, 'test')
        self.assertEqual(token.token, token_str)

    def test_get_reset_token_no_user(self):
        # Should fail silently
        self.assertTrue(self.webserver_export.get_reset_token('test'))

        # No mail should have been sent
        self.assertEqual(len(self.administrator.sendmail.log), 0)

        # No reset tokens should be created
        from sputnik import models
        self.assertEqual(self.session.query(models.ResetToken).count(), 0)

    def test_register_support_ticket(self):
        pass

    def test_get_permissions(self):
        pass

    def test_request_support_nonce(self):
        pass

class TestTicketServerExport(TestAdministrator):
    def test_check_support_nonce(self):
        pass

    def test_register_support_ticket(self):
        pass