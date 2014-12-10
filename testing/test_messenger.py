__author__ = 'sameer'

import sys, os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../tools"))

from twisted.trial import unittest
from twisted.internet import reactor, task
from sputnik import messenger
from test_sputnik import TestSputnik, FakeComponent
from pprint import pprint
from twisted.internet.defer import inlineCallbacks
from datetime import datetime

class TestMessenger(TestSputnik):
    def setUp(self):
        TestSputnik.setUp(self)
        sendmail = FakeComponent('sendmail')
        nexmo = FakeComponent('nexmo')
        self.messenger = messenger.Messenger(sendmail, nexmo, template_dir="../server/sputnik/admin_templates")

    @inlineCallbacks
    def test_email_only(self):
        self.create_account('test')
        user = self.get_user('test')
        user.email = 'test@m2.io'
        user.phone = None
        user.preference = 'email'
        result = yield self.messenger.send_message(user, 'Reset password', 'reset_password',
                                                   token='test_token', base_uri='http://test.com',
                                                   expiration=datetime.utcnow())
        self.assertTrue(result[0][0])
        message = self.messenger.sendmail.log[0]
        self.assertEqual(message[0], 'send_mail')
        self.assertSubstring('http://test.com/#function=change_password_token&username=test&token=test_token',
                             message[1][0])
        self.assertEqual(message[2]['subject'], 'Reset password')

    @inlineCallbacks
    def test_sms_only(self):
        self.create_account('test')
        user = self.get_user('test')
        user.email = None
        user.phone = '1231'
        user.preference = 'sms'
        result = yield self.messenger.send_message(user, 'Reset password', 'reset_password',
                                                   token='test_token', base_uri='http://test.com',
                                                   expiration=datetime.utcnow())
        self.assertTrue(result[0][0])
        message = self.messenger.nexmo.log[0]
        self.assertEqual(message[0], 'sms')
        self.assertSubstring('http://test.com/#function=change_password_token&username=test&token=test_token',
                             message[1][1])

    @inlineCallbacks
    def test_email_and_sms(self):
        self.create_account('test')
        user = self.get_user('test')
        user.email = 'test@m2.io'
        user.phone = '1231'
        user.preference = 'both'
        result = yield self.messenger.send_message(user, 'Reset password', 'reset_password',
                                                   token='test_token', base_uri='http://test.com',
                                                   expiration=datetime.utcnow())
        self.assertTrue(result[0][0])
        self.assertTrue(result[1][0])

        message = self.messenger.nexmo.log[0]
        self.assertEqual(message[0], 'sms')
        self.assertSubstring('http://test.com/#function=change_password_token&username=test&token=test_token',
                             message[1][1])

        message = self.messenger.sendmail.log[0]
        self.assertEqual(message[0], 'send_mail')
        self.assertSubstring('http://test.com/#function=change_password_token&username=test&token=test_token',
                             message[1][0])
        self.assertEqual(message[2]['subject'], 'Reset password')
