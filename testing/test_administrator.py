__author__ = 'sameer'

import sys
import os
from test_sputnik import TestSputnik, FakeProxy
from pprint import pprint

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

        self.administrator = administrator.Administrator(self.session, accountant, cashier, debug=True)
        self.webserver_export = administrator.WebserverExport(self.administrator)
        self.ticketserver_export = administrator.TicketServerExport(self.administrator)

class TestWebserverExport(TestAdministrator):
    def test_make_account(self):
        pass

    def test_change_profile(self):
        pass

    def test_reset_password_hash(self):
        pass

    def test_get_reset_token(self):
        pass

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