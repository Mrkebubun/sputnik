#!/usr/bin/python

"""
The administrator modifies database objects. It is allowed to access User
    objects. For other objects it delegates to appropriate services. This
    ensures there are no race conditions.

The interface is exposed with ZMQ RPC running under Twisted. Many of the RPC
    calls block, but performance is not crucial here.

"""

import sys, os
import collections
from datetime import datetime
import json
import copy
import string
import pickle
import time
import Crypto.Random.random
from dateutil import parser
import cgi

from twisted.web.resource import Resource, IResource
from twisted.web.server import Site
from twisted.web.guard import HTTPAuthSessionWrapper, DigestCredentialFactory
from twisted.web.server import NOT_DONE_YET
from twisted.web.util import redirectTo
from twisted.internet.task import LoopingCall
from zope.interface import implements
from twisted.internet import reactor, defer
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log
from twisted.cred.portal import IRealm, Portal
from twisted.cred.checkers import ICredentialsChecker
from twisted.cred.credentials import IUsernameDigestHash
from twisted.cred import error as credError
from twisted.cred._digest import calcHA1
from jinja2 import Environment, FileSystemLoader
import sqlalchemy.orm.exc
from sqlalchemy import func
from sqlalchemy.orm.exc import NoResultFound
from dateutil import parser
from datetime import timedelta
from autobahn.wamp.auth import derive_key, compute_totp
from twisted.web.static import File

import config
import database
import models
from util import ChainedOpenSSLContextFactory
import util
from messenger import Messenger, Sendmail, Nexmo
from watchdog import watchdog

from accountant import AccountantProxy

from exception import *

from zmq_util import export, router_share_async, dealer_proxy_async, push_proxy_async, ComponentExport
from rpc_schema import schema
from dateutil import relativedelta
from zendesk import Zendesk
from blockscore import BlockScore
from ticketserver import TicketServer
from bitgo import BitGo
import base64
from Crypto.Random.random import getrandbits
import urllib
from decimal import Decimal

USERNAME_TAKEN = AdministratorException("exceptions/administrator/username_taken")
NO_SUCH_USER = AdministratorException("exceptions/administrator/no_such_user")
PASSWORD_MISMATCH = AdministratorException("exceptions/administrator/password_mismatch")
INVALID_TOKEN = AdministratorException("exceptions/administrator/invalid_token")
EXPIRED_TOKEN = AdministratorException("exceptions/administrator/expired_token")
TICKET_EXISTS = AdministratorException("exceptions/administrator/ticket_exists")
USER_LIMIT_REACHED = AdministratorException("exceptions/administrator/user_limit_reached")
ADMIN_USERNAME_TAKEN = AdministratorException("exceptions/administrator/admin_username_taken")
INVALID_SUPPORT_NONCE = AdministratorException("exceptions/administrator/invalid_support_nonce")
SUPPORT_NONCE_USED = AdministratorException("exceptions/administrator/support_nonce_used")
INVALID_CURRENCY_QUANTITY = AdministratorException("exceptions/administrator/invalid_currency_quantity")
INVALID_REQUEST = AdministratorException("exceptions/administrator/invalid_request")
INSUFFICIENT_PERMISSIONS = AdministratorException("exceptions/administrator/insufficient_permissions")
NO_USERNAME_SPECIFIED = AdministratorException("exceptions/administrator/no_username_specified")
INVALID_QUANTITY = AdministratorException("exceptions/administrator/invalid_quantity")
CONTRACT_NOT_ACTIVE = AdministratorException("exceptions/administrator/contract_not_active")
MALICIOUS_LOOKING_INPUT = AdministratorException("exceptions/administrator/malicious_looking_input")
TOTP_NOT_ENABLED = AdministratorException("exceptions/administrator/totp_not_enabled")
TOTP_ALREADY_ENABLED = AdministratorException("exceptions/administrator/totp_already_enabled")
BITGO_TOKEN_INVALID = AdministratorException("exceptions/administrator/bitgo_token_invalid")
KEY_FILE_EXISTS = AdministratorException("exceptions/bitgo/key_file_exists")

from util import session_aware


class Administrator:
    """
    The main administrator class. This makes changes to the database.
    """

    def __init__(self, session, accountant, cashier, engines,
                 zendesk_domain, accountant_slow, webserver,
                 debug=False, base_uri=None, messenger=None,
                 template_dir='admin_templates',
                 user_limit=500,
                 bitgo=None,
                 bitgo_private_key_file=None,
                 bs_cache_update_period=86400,
                 testnet=True):
        """Set up the administrator

        :param session: the sqlAlchemy session
        :param accountant: The exposed fns on the accountant
        :type accountant: dealer_proxy_async
        :param cashier: The exposed fns on the cashier
        :type cashier: dealer_proxy_async
        :param debug: Are we going to permit weird things like position adjusts?
        :type debug: bool
        """
        self.session = session
        self.accountant = accountant
        self.accountant_slow = accountant_slow
        self.webserver = webserver
        self.cashier = cashier
        self.engines = engines
        self.zendesk_domain = zendesk_domain
        self.debug = debug
        self.template_dir = template_dir
        self.jinja_env = Environment(loader=FileSystemLoader(template_dir))
        self.base_uri = base_uri
        self.messenger = messenger
        self.user_limit = user_limit
        self.page_size = 10
        self.bitgo = bitgo
        self.bitgo_private_key_file = bitgo_private_key_file
        self.bitgo_tokens = {}
        self.testnet = testnet

        self.load_bs_cache()
        # Initialize the balance sheet cache
        if bs_cache_update_period is not None:
            self.bs_updater = LoopingCall(self.update_bs_cache)
            self.bs_updater.start(bs_cache_update_period, now=True)
        else:
            self.update_bs_cache()

    def bitgo_oauth_clear(self, admin_user):
        if admin_user in self.bitgo_tokens:
            del self.bitgo_tokens[admin_user]

    @inlineCallbacks
    def bitgo_oauth_token(self, code, admin_user):
        token_result = yield self.bitgo.authenticateWithAuthCode(code)
        self.bitgo_tokens[admin_user] = (token_result['access_token'].encode('utf-8'),
                                         datetime.utcfromtimestamp(token_result['expires_at']))

    def get_bitgo_token(self, admin_user):
        now = datetime.utcnow()
        if admin_user in self.bitgo_tokens and self.bitgo_tokens[admin_user][1] > now:
            return self.bitgo_tokens[admin_user][0]
        else:
            return None

    def make_account(self, username, password):
        """Makes a user account with the given password

        :param username: The new username
        :type username: str
        :param password: The new password hash with salt
        :type password: str
        :returns: bool
        :raises: USER_LIMIT_REACHED, USERNAME_TAKEN, OUT_OF_ADDRESSES
        """
        if self.malicious_looking(username):
            raise MALICIOUS_LOOKING_INPUT

        user_count = self.session.query(models.User).count()
        if user_count > self.user_limit:
            log.err("User limit reached")
            raise USER_LIMIT_REACHED

        existing = self.session.query(models.User).filter_by(
            username=username).first()
        if existing:
            log.err("Account creation failed: %s username is taken" % username)
            raise USERNAME_TAKEN

        user = models.User(username, password)
        user.email = username
        self.session.add(user)

        contracts = self.session.query(models.Contract).filter_by(
            contract_type='cash')
        for contract in contracts:
            position = models.Position(user, contract)
            self.session.add(position)

        self.session.commit()

        # Send registration mail
        self.messenger.send_message(user, "Welcome!", 'registration', 'misc', base_uri=self.base_uri)

        log.msg("Account created for %s" % username)
        return True


    def malicious_looking(self, w):
        """

        :param w:
        :returns: bool
        """
        return any(x in w for x in '<>&')

    def change_profile(self, username, profile):
        """Changes the profile of a user

        :param username: The user
        :type username: str
        :param profile: The profile details to use
        :type profile: dict
        :returns:
        :raises: NO_SUCH_USER
        """
        user = self.session.query(models.User).filter_by(
            username=username).one()
        if not user:
            raise NO_SUCH_USER

        # Don't permit changing email
        #user.email = profile.get("email", user.email)
        user.nickname = profile.get("nickname", user.nickname)
        user.locale = profile.get("locale", user.locale)
        user.phone = profile.get("phone", user.phone)

        if self.malicious_looking(profile.get('email', '')) or self.malicious_looking(profile.get('nickname', '')):
            raise MALICIOUS_LOOKING_INPUT

        # User notifications
        if 'notifications' in profile:
            # Remove notifications not in profile from db
            for notification in user.notifications:
                if notification.type in profile['notifications']:
                    if notification.method not in profile['notifications'][notification.type]:
                            self.session.delete(notification)

            # Add notifications in the profile that are not in db
            for type, methods in profile['notifications'].iteritems():
                notifications = [n.method for n in user.notifications if n.type == type]
                for method in [m for m in methods if m not in notifications]:
                    new_notification = models.Notification(username, type, method)
                    self.session.add(new_notification)

        self.session.commit()
        log.msg("Profile changed for %s to %s/%s - %s" % (user.username, user.email, user.nickname, user.notifications))
        return True

    def get_profile(self, username):
        user = self.session.query(models.User).filter_by(username=username).one()
        if not user:
            raise NO_SUCH_USER

        notifications = {}
        for notification in user.notifications:
            if notification.type not in notifications:
                notifications[notification.type] = [notification.method]
            else:
                notifications[notification.type].append(notification.method)

        profile = {'email': user.email,
                   'nickname': user.nickname,
                   'locale': user.locale,
                   'audit_secret': user.audit_secret,
                   'notifications': notifications
        }
        return profile

    def get_new_api_credentials(self, username, expiration):
        user = self.session.query(models.User).filter_by(username=username).one()
        if not user:
            raise NO_SUCH_USER

        user.api_key = base64.b64encode(("%064X" % getrandbits(256)).decode("hex"))
        user.api_expiration = util.timestamp_to_dt(expiration)
        user.api_secret = base64.b64encode(("%064X" % getrandbits(256)).decode("hex"))

        self.session.commit()
        return {'key': user.api_key, 'secret': user.api_secret, 'expiration': util.dt_to_timestamp(user.api_expiration)}

    def check_and_update_api_nonce(self, username, nonce):
        user = self.session.query(models.User).filter_by(username=username).one()
        if not user:
            raise NO_SUCH_USER

        if nonce <= user.api_nonce:
            return False
        else:
            user.api_nonce = nonce
            self.session.commit()
            return True

    def check_token(self, username, input_token):
        """Check to see if a password reset token is valid

        :param username: The user it is for
        :type username: str
        :param input_token: the token we are checking
        :type input_token: str
        :returns: models.ResetToken
        :raises: INVALID_TOKEN, EXPIRED_TOKEN
        """
        token_good = False
        found_tokens = self.session.query(models.ResetToken).filter_by(token=input_token, username=username).all()
        if not len(found_tokens):
            raise INVALID_TOKEN
        for token in found_tokens:
            if token.expiration > datetime.utcnow() and not token.used:
                token_good = True
                break

        if not token_good:
            raise EXPIRED_TOKEN

        return token

    def reset_password_plaintext(self, username, new_password):
        """Reset's a user's password to the given plaintext

        :param username: the user
        :type username: str
        :param new_password: the new password, in the clear
        :type new_password: str
        :returns: bool
        :raises: NO_SUCH_USER
        """
        user = self.session.query(models.User).filter_by(username=username).one()
        if not user:
            raise NO_SUCH_USER

        alphabet = string.digits + string.lowercase
        num = Crypto.Random.random.getrandbits(64)
        salt = ""
        while num != 0:
            num, i = divmod(num, len(alphabet))
            salt = alphabet[i] + salt

        password = derive_key(new_password, salt, iterations=1000, keylen=32)
        user.password = "%s:%s" % (salt, password)
        self.session.add(user)
        self.session.commit()
        return True

    def reset_password_hash(self, username, old_password_hash, new_password_hash, token=None):
        """Reset a user's password, make sure the old password or the token gets checked

        :param username: The user
        :type username: str
        :param old_password_hash: The old password hash if we don't have a token
        :type old_password_hash: str
        :param new_password_hash: The new password hash using the same salt as the old one
        :type new_password_hash: str
        :param token: The reset token which we can use to eliminate the old pw check
        :type token: str
        :returns: bool
        :raises: NO_SUCH_USER, FAILED_PASSWORD_CHANGE
        """
        try:
            user = self.session.query(models.User).filter_by(username=username).one()
        except sqlalchemy.orm.exc.NoResultFound:
            raise NO_SUCH_USER

        if user.password != old_password_hash and token is None:
            raise PASSWORD_MISMATCH
        elif user.password != old_password_hash:
            # Check token
            token = self.check_token(username, token)
            token.used = True
            self.session.add(token)

        user.password = new_password_hash

        self.session.add(user)
        self.session.commit()
        return True

    def get_reset_token(self, username, hours_to_expiry=2):
        """Get a reset token for a user, send him a mail with the token

        :param username: the user
        :type username: str
        :param hours_to_expiry: how long will this token be valid
        :type hours_to_expiry: int
        :returns: bool
        """
        try:
            user = self.session.query(models.User).filter(models.User.username == username).one()
        except sqlalchemy.orm.exc.NoResultFound:
            # If we have no user, we will silently fail because we don't want to
            # create a username oracle
            # We should log this though
            log.msg("get_reset_token: No such user %s" % username)
            return True

        token = models.ResetToken(username, hours_to_expiry)
        self.session.add(token)
        self.session.commit()

        log.msg("Created token: %s" % token)
        self.messenger.send_message(user, 'Reset password link enclosed', 'reset_password', 'misc',
                                    token=token.token, expiration=token.expiration.strftime("%Y-%m-%d %H:%M:%S %Z"),
                                    base_uri=self.base_uri)

        return True

    def enable_totp(self, username):
        """Initiates process to enable TOTP for account. Returns the TOTP secret.

        :param username: the account username
        :type username: str
        :returns: str
        :raises: NO_SUCH_USER, TOTP_ALREADY_ENABLED
        """
        user = self.session.query(models.User).filter_by(
            username=username).one()
        if not user:
            raise NO_SUCH_USER

        if user.totp_enabled:
            raise TOTP_ALREADY_ENABLED

        secret = base64.b32encode("".join(
            chr(getrandbits(8)) for i in range(16)))
        user.totp_secret = secret
        self.session.commit()
        return secret

    def verify_totp(self, username, otp):
        """Verifies the user has saved the TOTP secret.

        :param username: the account username
        :type username: str
        :param otp: an otp code
        :type username: str
        :returns: bool
        :raises: NO_SUCH_USER, TOTP_NOT_ENABLED, TOTP_ALREADY_ENABLED
        """
        user = self.session.query(models.User).filter_by(
            username=username).one()
        if not user:
            raise NO_SUCH_USER

        if not user.totp_secret:
            raise TOTP_NOT_ENABLED

        if user.totp_enabled:
            raise TOTP_ALREADY_ENABLED

        if self._check_totp(user, otp):
            user.totp_enabled = True
            self.session.commit()
            return True

        return False

    def disable_totp(self, username, otp):
        """Disables TOTP for an account.

        :param username: the account username
        :type username: str
        :param otp: an otp code
        :type username: str
        :returns: bool
        :raises: NO_SUCH_USER, TOTP_NOT_ENABLED
        """
        user = self.session.query(models.User).filter_by(
            username=username).one()
        if not user:
            raise NO_SUCH_USER
        
        if not user.totp_enabled:
            raise TOTP_NOT_ENABLED
        
        if self._check_totp(user, otp):
            user.totp_secret = None
            user.totp_enabled = False
            self.session.commit()
            return True

        return False

    def check_totp(self, username, otp):
        """Checks to make sure the OTP is valid and updates database so the token cannot be reused. Returns verification success. If OTP is not enabled, returns True.

        :param username: the account username
        :type username: str
        :param otp: an otp code
        :type username: str
        :returns: bool
        :raises: NO_SUCH_USER
        """
        user = self.session.query(models.User).filter_by(
            username=username).one()
        if not user:
            raise NO_SUCH_USER
        
        if not user.totp_enabled or not user.totp_secret:
            return True
        
        return self._check_totp(user, otp)

    @session_aware
    def _check_totp(self, user, otp):
        """Checks to make sure the OTP is valid and updates database so the token cannot be reused. Returns verification success. This method is safe to use internally.

        :param user: the User object
        :type username: str
        :param otp: an otp code
        :type username: str
        :returns: bool
        """
        secret = bytes(user.totp_secret)
        now = time.time() // 30
        for i in range(-1, 2):
            if user.totp_last >= now + i:
                # token reuse is not allowed
                continue
            if compute_totp(secret, i) == otp:
                user.totp_last = now + i
                self.session.commit()
                return True

        return False

    def expire_all(self):
        """Use this to expire all objects in the session, because other processes may have updated things in the db

        """
        self.session.expire_all()

    def get_users(self):
        """Give us an array of all the users

        :returns: list -- list of models.User
        """
        users = self.session.query(models.User)
        return users

    def get_admin_users(self):
        """Give us an array of all the admin users

        :returns: list -- list of models.AdminUser
        """
        admin_users = self.session.query(models.AdminUser)
        return admin_users

    def get_user(self, username):
        """Give us the details of a particular user

        :param username: the user
        :type username: str
        :returns: models.User
        """
        user = self.session.query(models.User).filter_by(username=username).one()

        return user

    def mail_statements(self, period, now=None):
        self.expire_all()

        if now is None:
            now = datetime.utcnow()

        if period == "daily":
            yesterday = now - timedelta(days=1)
            yesterday_bod = datetime(yesterday.year, yesterday.month, yesterday.day)
            today_bod = datetime(now.year, now.month, now.day)
            yesterday_eod = today_bod - timedelta(microseconds=1)

            from_timestamp = util.dt_to_timestamp(yesterday_bod)
            to_timestamp = util.dt_to_timestamp(yesterday_eod)
        elif period == "weekly":
            recent_sunday = now + relativedelta.relativedelta(weekday=relativedelta.SU(-1))
            second_recent_sunday = now + relativedelta.relativedelta(weekday=relativedelta.SU(-2))
            last_week_start = datetime(second_recent_sunday.year, second_recent_sunday.month, second_recent_sunday.day)
            this_week_start = datetime(recent_sunday.year, recent_sunday.month, recent_sunday.day)
            last_week_end = this_week_start - timedelta(microseconds=1)

            from_timestamp = util.dt_to_timestamp(last_week_start)
            to_timestamp = util.dt_to_timestamp(last_week_end)
        elif period == "monthly":
            last_month = now + relativedelta.relativedelta(months=-1)
            last_month_bom = datetime(last_month.year, last_month.month, 1)
            this_month_bom = datetime(now.year, now.month, 1)
            last_month_eom = this_month_bom - timedelta(microseconds=1)

            from_timestamp = util.dt_to_timestamp(last_month_bom)
            to_timestamp = util.dt_to_timestamp(last_month_eom)
        else:
            raise AdministratorException("Period not supported: %s" % period)

        users = self.session.query(models.User)
        user_list = []

        for user in users:
            if period in [notification.type for notification in user.notifications if notification.method == "email"]:
                self.mail_statement(user.username, from_timestamp, to_timestamp, period)
                user_list.append(user.username)

        return user_list

    @util.timed
    def mail_statement(self, username, from_timestamp=None, to_timestamp=None, period=None):
        now = datetime.utcnow()
        user = self.get_user(username)

        if to_timestamp is None:
            end = now
        else:
            end = util.timestamp_to_dt(to_timestamp)

        if from_timestamp is None:
            start = end + relativedelta.relativedelta(months=-1)
        else:
            start = util.timestamp_to_dt(from_timestamp)

        if period is None:
            period = "monthly"

        log.msg("mailing statement for %s from %s to %s" % (username, start, end))

        # Get beginning balances
        balances = self.session.query(func.sum(models.Posting.quantity).label("balance"),
                                      func.max(models.Journal.timestamp).label("max_timestamp"),
                                      models.Contract).filter(models.Posting.username == username).filter(
                                        models.Journal.id==models.Posting.journal_id).filter(
                                        models.Posting.contract_id==models.Contract.id).filter(
                                        models.Journal.timestamp < start).group_by(models.Contract)


        transaction_info = collections.defaultdict(list)
        beginning_balance_info = collections.defaultdict(int)
        totals_by_type = collections.defaultdict(lambda: collections.defaultdict(int))
        totals_by_type_fmt = collections.defaultdict(dict)
        details = {}

        # get all positions
        positions = self.session.query(models.Position).filter_by(username=username)
        for position in positions:
            contract = position.contract

            # Find the balance in balances
            running_balance = 0
            for balance in balances:
                if balance.Contract == contract:
                    running_balance = balance.balance
                    break

            details[contract.ticker] = {
                'transactions': [],
                'totals_by_type': collections.defaultdict(int),
                'totals_by_type_fmt': {},
                'beginning_balance': running_balance,
                'beginning_balance_fmt': util.quantity_fmt(contract, running_balance),
                'ending_balance': running_balance,
                'ending_balance_fmt': util.quantity_fmt(contract, running_balance)
            }
            # Get transactions during period
            transactions = self.session.query(models.Posting, models.Journal).filter(
                models.Journal.id==models.Posting.journal_id).filter(
                models.Journal.timestamp >= start).filter(
                models.Journal.timestamp <= end).filter(models.Posting.username==username).filter(
                models.Posting.contract_id == contract.id).order_by(
                models.Journal.timestamp)

            for transaction in transactions:
                running_balance += transaction.Posting.quantity
                details[contract.ticker]['totals_by_type'][transaction.Journal.type] += transaction.Posting.quantity

                if transaction.Posting.quantity < 0:
                    if user.type == 'Asset':
                        direction = 'credit'
                    else:
                        direction = 'debit'
                else:
                    if user.type == 'Asset':
                        direction = 'debit'
                    else:
                        direction = 'credit'

                details[contract.ticker]['transactions'].append({'contract': contract.ticker,
                                                                         'timestamp': transaction.Journal.timestamp,
                                                                         'quantity': abs(transaction.Posting.quantity),
                                                                         'quantity_fmt': util.quantity_fmt(
                                                                             contract,
                                                                             abs(transaction.Posting.quantity)),
                                                                         'direction': direction,
                                                                         'balance': running_balance,
                                                                         'balance_fmt': util.quantity_fmt(
                                                                             contract, running_balance),
                                                                         'note': transaction.Posting.note,
                                                                         'type': transaction.Journal.type
                })
                details[contract.ticker]['ending_balance'] = running_balance
                details[contract.ticker]['ending_balance_fmt'] = util.quantity_fmt(contract, running_balance)

            for type, total in details[contract.ticker]['totals_by_type'].iteritems():
                details[contract.ticker]['totals_by_type_fmt'][type] = util.quantity_fmt(contract, total)

        self.messenger.send_message(user, 'Your statement', 'transaction_statement',
                                              period,
                           start=start,
                           end=end,
                           details=details)


    def request_support_nonce(self, username, type):
        """Get a nonce so we can submit a support ticket

        :param username: The user
        :type username: str
        :param type: The type of ticket
        :type type: str
        :returns: str -- the nonce for the user
        """
        ticket = models.SupportTicket(username, type)
        self.session.add(ticket)
        self.session.commit()
        return ticket.nonce

    def check_support_nonce(self, username, nonce, type):
        """Checks to see if a support nonce is valid for the user and type

        :param username: the user
        :type username: str
        :param nonce: The nonce we are checking
        :type nonce: str
        :param type: the type of the ticket
        :type type: str
        :returns: dict -- the user's username, email, and nickname
        :raises: INVALID_SUPPORT_NONCE, SUPPORT_NONCE_USED
        """
        log.msg("Checking nonce for %s: %s/%s" % (username, nonce, type))
        try:
            ticket = self.session.query(models.SupportTicket).filter_by(username=username, nonce=nonce, type=type).one()
        except NoResultFound:
            raise INVALID_SUPPORT_NONCE

        if ticket.foreign_key is not None:
            raise SUPPORT_NONCE_USED

        return {'username': ticket.user.username,
                'email': ticket.user.email,
                'nickname': ticket.user.nickname}

    def register_support_ticket(self, username, nonce, type, foreign_key):
        """Register a support ticket where the nonce was stored

        :param username: the user
        :type username: str
        :param nonce: the nonce
        :type nonce: str
        :param type: The type of ticket
        :type type: str
        :param foreign_key: the key which lets us access the ticket on the support interface
        :type foreign_key: str
        :returns: bool
        """
        if self.check_support_nonce(username, nonce, type):
            ticket = self.session.query(models.SupportTicket).filter_by(username=username, nonce=nonce, type=type).one()
            ticket.foreign_key = foreign_key
            self.session.add(ticket)
            self.session.commit()
            log.msg("Registered foreign key: %s for %s" % (foreign_key, username))
            return True

    def set_admin_level(self, username, level):
        """Sets the level of control that the admin user has

        :param username: the admin user
        :type username: str
        :param level: the new level we want
        :type level: int
        :returns: bool
        """
        user = self.session.query(models.AdminUser).filter_by(username=username).one()
        user.level = level
        self.session.add(user)
        self.session.commit()
        return True

    def new_admin_user(self, username, password_hash, level):
        """Create a new admin user with a certain password_hash

        :param username: the new  username
        :type username: str
        :param password_hash: the password hash for the new user
        :type password_hash: str
        :param level: the new user's admin level
        :type level: int
        :returns: bool
        """

        if self.session.query(models.AdminUser).filter_by(username=username).count() > 0:
            raise ADMIN_USERNAME_TAKEN

        user = models.AdminUser(username, password_hash, level)
        self.session.add(user)
        self.session.commit()
        log.msg("Admin user %s created" % username)
        return True

    def reset_admin_password(self, username, old_password_hash, new_password_hash):
        """Reset the admin password ensuring we knew the old password

        :param username: The admin user
        :type username: str
        :param old_password_hash: the old password hash
        :type old_password_hash: str
        :param new_password_hash: the new hash
        :type new_password_hash: str
        :returns: bool
        :raises: FAILED_PASSWORD_CHANGE, NO_SUCH_USER
        """
        try:
            user = self.session.query(models.AdminUser).filter_by(username=username).one()
        except NoResultFound:
            raise NO_SUCH_USER

        # If the pw is blank, don't check
        if user.password_hash != "":
            if user.password_hash != old_password_hash:
                raise PASSWORD_MISMATCH

        user.password_hash = new_password_hash
        self.session.add(user)
        self.session.commit()
        log.msg("Admin user %s has password reset" % username)
        return True

    def force_reset_admin_password(self, username, new_password_hash):
        """Change an admin password even if we don't know the old password

        :param username: The admin user
        :type username: str
        :param new_password_hash: the new password hash
        :type new_password_hash: str
        :returns: bool
        :raises: NO_SUCH_USER
        """
        try:
            user = self.session.query(models.AdminUser).filter_by(username=username).one()
        except NoResultFound:
            raise NO_SUCH_USER

        user.password_hash = new_password_hash
        self.session.add(user)
        self.session.commit()
        log.msg("Admin user %s has password force reset" % username)
        return True

    def get_positions(self, username=None):
        """Get all the positions that exist, if username is set, get positions for that user only

        :returns: list -- models.Position
        """
        if username is None:
            positions = self.session.query(models.Position)
        else:
            positions = self.session.query(models.Position).filter_by(username=username)
        return positions

    def get_position(self, user, ticker):
        contract = self.get_contract(ticker)
        position = self.session.query(models.Position).filter_by(user=user, contract=contract).one()
        return position

    def get_order_book(self, ticker):
        d = self.engines[ticker].get_order_book()

        def reconcile_with_db(order_book):
            contract = self.get_contract(ticker)
            self.session.expire_all()
            orders = self.session.query(models.Order).filter_by(
                contract=contract, is_cancelled=False, accepted=True,
                dispatched=True).filter(models.Order.quantity_left > 0)
            ordermap = {}
            for order in orders:
                id_str = str(order.id)
                ordermap[id_str] = order
                if id_str not in order_book[order.side]:
                    order_book[order.side][id_str] = order.to_webserver()
                    order_book[order.side][id_str]['username'] = order.username
                    order_book[order.side][id_str]['errors'] = 'Not In Book'
                else:
                    if order.quantity_left != order_book[order.side][id_str]['quantity_left']:
                        order_book[order.side][id_str]['errors'] = 'DB quantity_left: %s' % util.quantity_fmt(contract,
                                                                                                              order.quantity_left)

            for side, orders in order_book.iteritems():
                for id, order in orders.iteritems():
                    order['timestamp'] = util.timestamp_to_dt(order['timestamp'])
                    if id not in ordermap:
                        order['errors'] = "Not in DB"
                    order["quantity_fmt"] = util.quantity_fmt(contract, order['quantity'])
                    order["quantity_left_fmt"] = util.quantity_fmt(contract, order['quantity_left'])
                    order["price_fmt"] = util.price_fmt(contract, order['price'])

            return order_book


        d.addCallback(reconcile_with_db)
        return d

    def get_margins(self):
        users = self.get_users()
        deferreds = []
        BTC = self.get_contract('BTC')
        for user in users.filter_by(type='Liability'):
            def fmt(margin):
                margin['low_margin_fmt'] = util.quantity_fmt(BTC, margin['low_margin'])
                margin['high_margin_fmt'] = util.quantity_fmt(BTC, margin['high_margin'])
                margin['cash_position_fmt'] = util.quantity_fmt(BTC, margin['cash_position'])
                return margin

            d = self.accountant_slow.get_margin(user.username)
            d.addCallback(fmt)
            deferreds.append(d)

        def process_all(results):
            all_margins = []
            for result in results:
                if result[0]:
                    all_margins.append(result[1])
                else:
                    log.err("Trouble with get_margin: %s" % result[1])

            return all_margins

        dl = defer.DeferredList(deferreds)
        dl.addCallback(process_all)
        return dl

    def cancel_order(self, username, id):
        return self.accountant.cancel_order(username, id)

    def get_journal(self, journal_id):
        """Get a journal given its id

        :param journal_id: the id of the journal we want
        :type journal_id: int
        :returns: models.Journal
        """
        journal = self.session.query(models.Journal).filter_by(id=journal_id).one()
        return journal

    def adjust_position(self, username, ticker, quantity_ui, admin_username):
        """Adjust the position for a user

        :param username: the user we are adjusting
        :type username: str
        :param ticker: the ticker of the contract
        :type ticker: str
        :param quantity_ui: the delta in user friendly units
        :type quantity_ui: int
        """
        contract = util.get_contract(self.session, ticker)
        quantity = util.quantity_to_wire(contract, quantity_ui)

        log.msg("Calling adjust position for %s: %s/%d" % (username, ticker, quantity))
        return self.accountant.adjust_position(username, ticker, quantity, admin_username)

    def clear_first_error(self, failure):
        failure.trap(defer.FirstError)
        return failure.value.args[0]

    def get_current_address(self, username, ticker):
        return self.cashier.get_current_address(username, ticker)

    @inlineCallbacks
    def transfer_from_multisig_wallet(self, ticker, quantity_ui, destination="offlinecash", multisig={}):
        contract = util.get_contract(self.session, ticker)
        quantity = util.quantity_to_wire(contract, quantity_ui)
        result = yield self.cashier.transfer_from_multisig_wallet(ticker, quantity, multisig=multisig, destination=destination)
        returnValue(result)

    @inlineCallbacks
    def transfer_from_hot_wallet(self, ticker, quantity_ui, destination="offlinecash"):
        contract = util.get_contract(self.session, ticker)
        quantity = util.quantity_to_wire(contract, quantity_ui)
        result = yield self.cashier.transfer_from_hot_wallet(ticker, quantity, destination=destination)
        returnValue(result)

    def transfer_position(self, ticker, from_user, to_user, quantity_ui, note):
        """Transfer a position from one user to another

        :param ticker: the contract
        :type ticker: str
        :param from_user: the user we are taking from
        :type from_user: str
        :param to_user: the user we are transferring to
        :type to_user: str
        :param quantity_ui: how much are we transferring in user friendly units
        :type quantity_ui: int
        """
        contract = util.get_contract(self.session, ticker)
        quantity = util.quantity_to_wire(contract, quantity_ui)

        log.msg("Transferring %d of %s from %s to %s" % (
            quantity, ticker, from_user, to_user))
        uid = util.get_uid()
        if not from_user or not to_user:
            raise NO_USERNAME_SPECIFIED
        
        d1 = self.accountant.transfer_position(from_user, ticker, 'debit', quantity, note, uid)
        d2 = self.accountant.transfer_position(to_user, ticker, 'credit', quantity, note, uid)
        return defer.gatherResults([d1, d2], consumeErrors=True).addErrback(self.clear_first_error)
    
    def mtm_futures(self):
        futures = self.session.query(models.Contract).filter_by(contract_type="futures",
                                                                active=True)
        for contract in futures:
            self.session.expire(contract)

        return defer.DeferredList([self.clear_contract(contract.ticker) for contract in futures if not contract.expired])

    def notify_expired(self):
        contracts = self.session.query(models.Contract).filter(models.Contract.contract_type.in_(["futures", "prediction"])).filter_by(active=True)
        for contract in contracts:
            self.session.expire(contract)
        expired_list = [contract for contract in contracts if contract.expired]
        if len(expired_list):
            # Send expiration message
            t = self.jinja_env.get_template('expired_contracts.email')
            content = t.render(expired_list=expired_list).encode('utf-8')

            # Now email
            log.msg("Sending mail: %s" % content)
            self.sendmail.send_mail(content, to_address=self.sendmail.from_address,
                                        subject='Expired contracts')

    def clear_contract(self, ticker, price_ui=None):
        contract = util.get_contract(self.session, ticker)

        if price_ui is not None:
            price = util.price_to_wire(contract, price_ui)
        else:
            price = None

        uid = util.get_uid()

        # Don't try to clear if the contract is not active
        if not contract.active:
            raise CONTRACT_NOT_ACTIVE

        d = defer.DeferredList(self.accountant_slow.clear_contract(None, ticker, price, uid))

        # If the contract is expired, mark it inactive or reset it
        if contract.expired:
            if contract.period is None:
                def mark_inactive(result):
                    try:
                        contract.active = False
                        self.session.commit()
                    except Exception as e:
                        self.session.rollback()
                        raise e

                d.addCallback(mark_inactive)
            else:
                def adjust_expiration(result):
                    try:
                        contract.expiration += contract.period
                        self.session.commit()
                    except Exception as e:
                        self.session.rollback()
                        raise e

                    self.accountant.reload_contract(None, ticker)
                    self.webserver.reload_contract(ticker)

                d.addCallback(adjust_expiration)

        return d

    def manual_deposit(self, address, quantity_ui, admin_username):
        address_db = self.session.query(models.Addresses).filter_by(address=address).one()
        quantity = util.quantity_to_wire(address_db.contract, quantity_ui)
        if quantity % address_db.contract.lot_size != 0:
            log.err("Manual deposit for invalid quantity: %d" % quantity)
            raise INVALID_CURRENCY_QUANTITY

        log.msg("Manual deposit of %d to %s" % (quantity, address))
        return self.accountant.deposit_cash(address_db.username, address, quantity, total=False, admin_username=admin_username)

    def get_balance_sheet(self):
        """Gets the balance sheet

        :returns: dict -- the balance sheet
        """
        return copy.deepcopy(self.bs_cache)

    def load_bs_cache(self):
        try:
            with open('/tmp/balance_sheet_cache.pickle', 'r') as f:
                self.bs_cache = pickle.load(f)
                log.msg("Loaded balance sheet")
        except IOError:
            self.bs_cache = {}

    def dump_bs_cache(self):
        with open('/tmp/balance_sheet_cache.pickle', 'w') as f:
            pickle.dump(self.bs_cache, f)
            log.msg("Saved balance sheet")

    @util.timed
    def update_bs_cache(self):
        now = datetime.utcnow()
        timestamp = util.dt_to_timestamp(now)

        balance_sheet = {'Asset': collections.defaultdict(lambda: {'positions_by_user': {},
                                                                   'total': 0,
                                                                   'positions_raw': []}),
                         'Liability': collections.defaultdict(lambda: {'positions_by_user': {},
                                                                       'total': 0,
                                                                       'positions_raw': []})}

        # # Build the balance sheet from scratch with a single query
        # if 'timestamp' in self.bs_cache:
        #     bs_query = self.session.query(models.Posting.username,
        #                                   models.Posting.contract_id,
        #                                   func.sum(models.Posting.quantity).label('position'),
        #                                   func.max(models.Journal.timestamp).label('last_timestamp')).filter(
        #         models.Journal.id == models.Posting.journal_id).filter(
        #         models.Journal.timestamp > util.timestamp_to_dt(self.bs_cache['timestamp'])).group_by(
        #         models.Posting.username,
        #         models.Posting.contract_id)
        #
        #     # Copy the cached balance sheet over, without losing any defaultdict-ness, also update the hashes
        #     for side in ["Asset", "Liability"]:
        #         if side in self.bs_cache:
        #             for contract in self.bs_cache[side]:
        #                 for username, position_details in self.bs_cache[side][contract]['positions_by_user'].iteritems():
        #                     user = self.get_user(username)
        #                     position_details['hash'] = user.user_hash(timestamp)
        #                     balance_sheet[side][contract]['positions_by_user'][username] = position_details
        #
        # else:
        bs_query = self.session.query(models.Posting.username,
                                      models.Posting.contract_id,
                                      func.sum(models.Posting.quantity).label('position')).group_by(
            models.Posting.username,
            models.Posting.contract_id)

        for row in bs_query:
            user = self.get_user(row.username)
            contract = self.get_contract(row.contract_id)
            if row.username in balance_sheet[user.type][contract.ticker]['positions_by_user']:
                position = balance_sheet[user.type][contract.ticker]['positions_by_user'][row.username][
                               'position'] + row.position
            else:
                position = row.position

            position_details = {'username': row.username,
                                'hash': user.user_hash(timestamp),
                                'position': position,
                                'position_fmt': util.quantity_fmt(contract, position),
                                'timestamp': timestamp}

            balance_sheet[user.type][contract.ticker]['positions_by_user'][row.username] = position_details

        for side, sheet in balance_sheet.iteritems():
            for ticker, details in sheet.iteritems():
                contract = self.get_contract(ticker)

                details['total'] = sum(
                    [r['position'] for r in balance_sheet[side][ticker]['positions_by_user'].values()])
                details['positions_raw'] = balance_sheet[side][ticker]['positions_by_user'].values()
                details['contract'] = contract.ticker
                details['total_fmt'] = util.quantity_fmt(contract, details['total'])

        balance_sheet['timestamp'] = timestamp
        self.bs_cache = {}
        for side, sheet in balance_sheet.iteritems():
            if isinstance(sheet, collections.defaultdict):
                self.bs_cache[side] = dict(sheet)
            else:
                self.bs_cache[side] = sheet

        self.dump_bs_cache()

    def get_audit(self):
        """Gets the audit, which is the balance sheet but scrubbed of usernames

        :returns: dict -- the audit
        """

        balance_sheet = self.get_balance_sheet()
        for side in ["Asset", "Liability"]:
            for ticker, details in balance_sheet[side].iteritems():
                details['positions'] = []
                for position in details['positions_raw']:
                    details['positions'].append((position['hash'], position['position_fmt']))
                del details['positions_raw']
                del details['positions_by_user']
                del details['total']

        return balance_sheet

    def get_permission_groups(self):
        """Get all the permission groups

        :returns: list -- models.PermissionGroup
        """
        permission_groups = self.session.query(models.PermissionGroup)
        return permission_groups

    def get_fee_groups(self):
        fee_groups = self.session.query(models.FeeGroup).all()
        return fee_groups

    def check_fee_groups(self, fee_groups):
        fee_problems = []
        for aggressive_group in fee_groups:
            for passive_group in fee_groups:
                total_factor = aggressive_group.aggressive_factor + passive_group.passive_factor
                if total_factor < 0:
                    fee_problems.append({'aggressive_group': aggressive_group,
                                         'passive_group': passive_group,
                                         'total_factor': total_factor})
        return fee_problems

    def get_contracts(self):
        contracts = self.session.query(models.Contract).filter_by(active=True)
        return contracts

    def get_contract(self, ticker):
        contract = util.get_contract(self.session, ticker)
        return contract

    def edit_contract(self, ticker, args):
        contract = self.get_contract(ticker)
        for key, value in args.iteritems():
            setattr(contract, key, value)

        self.session.commit()
        self.webserver.reload_contract(ticker)
        self.accountant.reload_contract(None, ticker)

    def get_withdrawals(self):
        withdrawals = self.session.query(models.Withdrawal)
        return withdrawals

    def get_deposits(self):
        addresses = self.session.query(models.Addresses).filter(models.Addresses.username != None)
        return addresses

    @util.timed
    def get_orders(self, user, page=0):
        all_orders = self.session.query(models.Order).filter_by(user=user)
        order_count = all_orders.count()
        order_pages = int(order_count / self.page_size) + 1
        if page < 0:
            page = 0
        orders = all_orders.order_by(models.Order.timestamp.desc()).offset(self.page_size * page).limit(self.page_size)
        return orders, order_pages

    @util.timed
    def get_postings(self, user, contract, page=0):
        import time

        last = time.time()

        all_postings = self.session.query(models.Posting).filter_by(
            username=user.username).filter_by(
            contract_id=contract.id)

        now = time.time()
        log.msg("Elapsed: %0.2fms" % ((now - last) * 1000))
        last = now

        postings_count = all_postings.count()

        now = time.time()
        log.msg("Elapsed: %0.2fms" % ((now - last) * 1000))
        last = now

        postings_pages = int(postings_count / self.page_size) + 1
        if page < 0:
            page = 0

        postings = all_postings.join(models.Posting.journal).order_by(models.Journal.timestamp.desc()).offset(
            self.page_size * page).limit(self.page_size)

        now = time.time()
        log.msg("Elapsed: %0.2fms" % ((now - last) * 1000))

        return postings, postings_pages

    def change_permission_group(self, username, id):
        """Change the permission group for a user

        :param username: The user we are changing
        :type username: str
        :param id: the id of the new permission group
        :type id: int
        """
        log.msg("Changing permission group for %s to %d" % (username, id))
        return self.accountant.change_permission_group(username, id)

    def change_fee_group(self, username, id):
        """Change the permission group for a user

        :param username: The user we are changing
        :type username: str
        :param id: the id of the new permission group
        :type id: int
        """
        log.msg("Changing fee group for %s to %d" % (username, id))
        return self.accountant.change_fee_group(username, id)

    def modify_fee_group(self, id, name, aggressive_factor, passive_factor, withdraw_factor, deposit_factor):
        """Change the permission group for a user

        :param username: The user we are changing
        :type username: str
        :param id: the id of the new permission group
        :type id: int
        """
        log.msg("Modifying fee group %d" % id)

        try:
            group = self.session.query(models.FeeGroup).filter_by(id=id).one()
            group.name = name
            group.aggressive_factor = aggressive_factor
            group.passive_factor = passive_factor
            group.withdraw_factor = withdraw_factor
            group.deposit_factor = deposit_factor
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            raise e

        self.accountant.reload_fee_group(None, group.id)

    def new_fee_group(self, name, aggressive_factor, passive_factor, withdraw_factor, deposit_factor):
        try:
            log.msg("Creating new fee group: %s" % name)
            fee_group = models.FeeGroup(name, aggressive_factor, passive_factor, withdraw_factor, deposit_factor)
            self.session.add(fee_group)
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            log.err("Error: %s" % e)
            raise e

    def new_permission_group(self, name, permissions):
        """Create a new permission group

        :param name: the new group's name
        :type name: str
        """

        try:
            log.msg("Creating new permission group %s" % name)
            permission_group = models.PermissionGroup(name, permissions)
            self.session.add(permission_group)
            self.session.commit()
        except Exception as e:
            log.err("Error: %s" % e)
            self.session.rollback()
            raise e

    def process_withdrawal(self, id, online=False, cancel=False, admin_username=None, multisig={}):
        return self.cashier.process_withdrawal(id, online=online, cancel=cancel, admin_username=admin_username, multisig=multisig)

    def liquidate_all(self, username):
        self.accountant_slow.liquidate_all(username)
        
    def liquidate_position(self, username, ticker):
        self.accountant_slow.liquidate_position(username, ticker)
        
    @inlineCallbacks
    def initialize_multisig(self, ticker, public_key, multisig={}):
        # Create wallet with the given public_key
        if os.path.exists(self.bitgo_private_key_file):
            raise KEY_FILE_EXISTS

        self.bitgo.token = multisig['token'].encode('utf-8')
        # Generate a passphrase
        passphrase = base64.b64encode(("%016X" % getrandbits(64)).decode("hex"))
        result = yield self.bitgo.wallets.createWalletWithKeychains(passphrase=passphrase, label="sputnik", backup_xpub=public_key)

        # Save the encrypted xpriv to the local storage

        with open(self.bitgo_private_key_file, "wb") as f:
            key_data = {'passphrase': passphrase,
                        'encryptedXprv': result['userKeychain']['encryptedXprv']}
            json.dump(key_data, f)

        # Get deposit address
        address = result['wallet'].id

        # Save deposit address
        try:
            contract = util.get_contract(self.session, ticker)
            contract.multisig_wallet_address = address
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            log.err("Unable to save new deposit address for multisig")
            log.err(e)

        returnValue(address)

class AdminAPI(Resource):
    isLeaf = True

    def __init__(self, administrator, avatarId, avatarLevel):
        self.administrator = administrator
        self.avatarId = avatarId
        self.avatarLevel = avatarLevel

    def log(self, request, data):
        """Log the request

        """
        log.msg(
            self.avatarId,
            request.getClientIP(),
            request.getUser(),
            request.method,
            request.uri,
            request.clientproto,
            request.code,
            request.sentLength or "-",
            request.getHeader("referer") or "-",
            request.getHeader("user-agent") or "-",
            json.dumps(request.args),
            data)

    def process_request(self, request, data=None):
        if self.avatarLevel < 4:
            raise INSUFFICIENT_PERMISSIONS

        resources = {'/api/withdrawals': self.withdrawals,
                     '/api/deposits': self.deposits,
                     '/api/process_withdrawal': self.process_withdrawal,
                     '/api/manual_deposit': self.manual_deposit,
                     '/api/rescan_address': self.rescan_address,
                     '/api/clear_contract': self.clear_contract,
        }
        if request.path in resources:
            return resources[request.path](request, data)
        else:
            raise INVALID_REQUEST

    def withdrawals(self, request, data):
        withdrawals = self.administrator.get_withdrawals()
        return defer.succeed([w.dict for w in withdrawals if w.pending])

    def deposits(self, request, data):
        deposits = self.administrator.get_deposits()
        return defer.succeed([d.dict for d in deposits])

    def rescan_address(self, request, data):
        self.administrator.rescan_address(data['address'])
        return defer.succeed(None)

    def clear_contract(self, request, data):
        if 'price' not in data:
            d = self.administrator.clear_contract(data['ticker'])
        else:
            d = self.administrator.clear_contract(data['ticker'], Decimal(data['price']))

        def process_done(result):
            request.write(json.dumps({'result': True}))
            request.finish()

        d.addCallback(process_done)
        return NOT_DONE_YET

    def process_withdrawal(self, request, data):
        if 'cancel' in data:
            cancel = data['cancel']
            if cancel is True:
                online = False
        else:
            cancel = False
            if 'online' in data:
                online = data['online']
            else:
                online = False

        multisig = data.get('multisig', {})

        return self.administrator.process_withdrawal(int(data['id']), online=online, cancel=cancel,
                                              admin_username=self.avatarId, multisig=multisig)

    def manual_deposit(self, request, data):
        return self.administrator.manual_deposit(data['address'], Decimal(data['quantity']), self.avatarId)

    def render(self, request):
        data = request.content.read()
        self.log(request, data)
        request.setHeader('content-type', 'application/json')
        try:
            if request.method == "GET":
                d = self.process_request(request)
            else:
                parsed_data = json.loads(data)
                d = self.process_request(request, data=parsed_data)

            def process_result(result):
                final_result = {'success': True, 'result': result}
                return final_result

            def process_error(failure):
                failure.trap(SputnikException)
                log.err(failure)
                return {'success': False, 'error': failure.value.args}

            def deliver_result(result):
                request.write(json.dumps(result, sort_keys=True, indent=4, separators=(',', ': ')))
                request.finish()

            d.addCallback(process_result).addErrback(process_error).addCallback(deliver_result)
            return NOT_DONE_YET
        except AdministratorException as e:
            log.err(e)
            result = {'success': False, 'error': e.args}
            return json.dumps(result, sort_keys=True,
                              indent=4, separators=(',', ': '))

class AdminWebUI(Resource):
    isLeaf = False

    def __init__(self, administrator, avatarId, avatarLevel, digest_factory, base_uri):
        """The web Resource that front-ends the administrator

        :param administrator: the actual administrator
        :type administrator: dealer_proxy_async
        :param avatarId: The admin user that is logging in
        :type avatarId: str
        :param avatarLevel: what is this admin user's level
        :type avatarLevel: int
        :param digest_factory: The factory that tells us about auth details
        """

        self.administrator = administrator
        self.avatarId = avatarId
        self.avatarLevel = avatarLevel
        self.jinja_env = Environment(loader=FileSystemLoader(self.administrator.component.template_dir),
                                     autoescape=True)
        self.digest_factory = digest_factory
        self.base_uri = base_uri
        Resource.__init__(self)

    def check_referer(self, request):
        # If we have a raw GET with no args, we don't need to check referer
        if request.method == "GET" and not request.args:
            return True

        # for bitgo oauth:
        if request.path == '/bitgo_oauth_redirect':
            return True
        else:
            if self.base_uri:
                referer = request.getHeader("referer")
                if referer is None or not referer.startswith(self.base_uri):
                    log.err("Referer check failed: %s" % referer)
                    return False
                else:
                    return True
            else:
                return True


    def calc_ha1(self, password, username=None):
        """Calculate the HA1 for a password so we can store it in the DB

        :param password: the plaintext password
        :type password: str
        :param username: the user to consider, if None, use the avatarId
        :type username: str
        :returns: str
        """

        if username is None:
            username = self.avatarId

        realm = self.digest_factory.digest.authenticationRealm
        return calcHA1('md5', username, realm, password, None, None)

    def getChild(self, path, request):
        """return myself

        """
        return self

    def log(self, request):
        """Log the request

        """
        log.msg(
            self.avatarId,
            request.getClientIP(),
            request.getUser(),
            request.method,
            request.uri,
            request.clientproto,
            request.code,
            request.sentLength or "-",
            request.getHeader("referer") or "-",
            request.getHeader("user-agent") or "-",
            json.dumps(request.args))

    def render(self, request):
        """Render the request

        """
        self.log(request)
        # Which paths don't require a referer check
        if not self.check_referer(request):
            return redirectTo('/', request)

        resources = [
                    # Level 0
                    { '/': self.admin,
                      '/reset_admin_password': self.reset_admin_password
                    },
                    # Level 1
                     {'/': self.user_list,
                      '/user_details': self.user_details,
                      '/user_orders': self.user_orders,
                      '/user_postings': self.user_postings,
                      '/rescan_address': self.rescan_address,
                      '/admin': self.admin,
                      '/contracts': self.contracts,
                      '/mail_statement': self.mail_statement,
                     },
                    # Level 2
                     {'/reset_password': self.reset_password,
                      '/permission_groups': self.permission_groups,
                      '/change_permission_group': self.change_permission_group,
                      '/fee_groups': self.fee_groups,
                     },
                    # Level 3
                     {'/balance_sheet': self.balance_sheet,
                      '/ledger': self.ledger,
                      '/new_permission_group': self.new_permission_group,
                      '/edit_contract': self.edit_contract,
                      '/change_fee_group': self.change_fee_group,
                      '/new_fee_group': self.new_fee_group,
                      '/modify_fee_group': self.modify_fee_group,
                     },
                    # Level 4
                     {
                      '/process_withdrawal': self.process_withdrawal,
                      '/withdrawals': self.withdrawals,
                      '/deposits': self.deposits,
                      '/order_book': self.order_book,
                      '/manual_deposit': self.manual_deposit,
                      '/cancel_order': self.cancel_order,
                      '/margins': self.margins
                     },
                    # Level 5
                     {'/admin_list': self.admin_list,
                      '/new_admin_user': self.new_admin_user,
                      '/set_admin_level': self.set_admin_level,
                      '/force_reset_admin_password': self.force_reset_admin_password,
                      '/transfer_position': self.transfer_position,
                      '/adjust_position': self.adjust_position,
                      '/liquidate_all': self.liquidate_all,
                      '/liquidate_position': self.liquidate_position,
                      '/wallets': self.wallets,
                      '/transfer_from_hot_wallet': self.transfer_from_hot_wallet,
                      '/transfer_from_multisig_wallet': self.transfer_from_multisig_wallet,
                      '/bitgo_oauth_get': self.bitgo_oauth_get,
                      '/bitgo_oauth_clear': self.bitgo_oauth_clear,
                      '/bitgo_oauth_redirect': self.bitgo_oauth_redirect,
                      '/initialize_multisig': self.initialize_multisig,
                      '/clear_contract': self.clear_contract}]
        
        resource_list = {}
        for level in range(0, self.avatarLevel + 1):
            resource_list.update(resources[level])
        try:

            try:
                resource = resource_list[request.path]
            except KeyError:
                return self.invalid_request(request)

            try:
                return resource(request)
            except ValueError:
                raise INVALID_QUANTITY

        except SputnikException as e:
            return self.error_request(request, e.args)

    def invalid_request(self, request):
        log.err("Invalid request received: %s" % request)
        t = self.jinja_env.get_template("invalid_request.html")
        return t.render().encode('utf-8')

    def margins(self, request):
        d = self.administrator.get_margins()
        def show_margins(margins):
            t = self.jinja_env.get_template('margins.html')
            rendered = t.render(margins=margins)
            request.write(rendered.encode('utf-8'))
            request.finish()

        d.addCallback(show_margins)
        return NOT_DONE_YET

    def sputnik_error_callback(self, failure, request):
        failure.trap(SputnikException)
        log.err("SputnikException in deferred for request: %s" % request)
        log.err(failure)
        msg = self.error_request(request, failure.value.args)
        request.write(msg)
        request.finish()

    def generic_error_callback(self, failure, request):
        log.err("UNHANDLED ERROR in deferred for request: %s" % request)
        log.err(failure)
        msg = self.error_request(request, ("exceptions/administrator/generic_error",))
        request.write(msg)
        request.finish()

    def error_request(self, request, error):
        log.err("Error %s received for request %s" % (error, request))
        t = self.jinja_env.get_template("error.html")
        return t.render(error=error).encode('utf-8')

    def bitgo_oauth_get(self, request, wallet_id=None):
        params = { 'client_id': self.administrator.component.bitgo.client_id,
                   'redirect_uri': self.base_uri + '/bitgo_oauth_redirect'}
        if 'wallet_id' in request.args:
            wallet_id = request.args['wallet_id'][0]

        if wallet_id is None:
            params['scope'] = "wallet_create"
        else:
            params['scope'] = "wallet_spend:%s wallet_view:%s" % (wallet_id, wallet_id)

        bitgo_uri = self.administrator.component.bitgo.endpoint + '/oauth/authorize'
        params_encoded = urllib.urlencode(params)
        return redirectTo(bitgo_uri + '?' + params_encoded, request)

    def bitgo_oauth_clear(self, request):
        self.administrator.bitgo_oauth_clear(self.avatarId)
        return redirectTo('/wallets', request)

    def bitgo_oauth_redirect(self, request):
        code = request.args['code'][0]

        def _cb(result):
            request.write(redirectTo('/wallets', request))
            request.finish()

        d = self.administrator.bitgo_oauth_token(code, self.avatarId)
        d.addCallback(_cb).addErrback(self.sputnik_error_callback, request).addErrback(self.generic_error_callback, request)
        return NOT_DONE_YET

    def initialize_multisig(self, request):
        ticker = request.args['contract'][0]

        public_key = request.args['public_key'][0]

        token = self.administrator.get_bitgo_token(self.avatarId)
        if token is None:
            raise BITGO_TOKEN_INVALID

        d = self.administrator.initialize_multisig(ticker, public_key, {'token': token})
        def _cb(result):
            # Reauth to get view and spend permissions on the wallet we just created
            request.write(self.bitgo_oauth_get(request, wallet_id=result))
            request.finish()

        d.addCallback(_cb).addErrback(self.sputnik_error_callback, request).addErrback(self.generic_error_callback, request)
        return NOT_DONE_YET


    def process_withdrawal(self, request):
        if 'cancel' in request.args:
            cancel = True
            online = False
        else:
            cancel = False
            if 'online' in request.args:
                online = True
            else:
                online = False

        if 'multisig' in request.args:
            if self.administrator.get_bitgo_token(self.avatarId) is None:
                raise BITGO_TOKEN_INVALID

            multisig = {'otp': request.args['otp'][0],
                        'token': self.administrator.get_bitgo_token(self.avatarId)}
        else:
            multisig = {}

        d = self.administrator.process_withdrawal(int(request.args['id'][0]), online=online, cancel=cancel,
                                                  admin_username=self.avatarId, multisig=multisig)
        def _cb(result, request):
            request.write(redirectTo("/user_details?username=%s" % request.args['username'][0], request))
            request.finish()

        d.addCallback(_cb, request).addErrback(self.sputnik_error_callback, request).addErrback(self.generic_error_callback, request)
        return NOT_DONE_YET

    def mail_statement(self, request):
        self.administrator.expire_all()

        self.administrator.mail_statement(request.args['username'][0])
        return redirectTo("/user_details?username=%s" % request.args['username'][0], request)
    
    def permission_groups(self, request):
        """Get the permission groups page

        """
        self.administrator.expire_all()
        permission_groups = self.administrator.get_permission_groups()
        t = self.jinja_env.get_template('permission_groups.html')
        return t.render(permission_groups=permission_groups).encode('utf-8')

    def wallets(self, request):
        """Get the permission groups page

        """
        contracts = self.administrator.get_contracts()
        onlinecash = {position.contract.ticker: position for position in self.administrator.get_positions(username="onlinecash")}
        offlinecash = {position.contract.ticker: position for position in self.administrator.get_positions(username="offlinecash")}
        multisigcash = {position.contract.ticker: position for position in self.administrator.get_positions(username="multisigcash")}
        bitgo_auth = self.administrator.get_bitgo_token(self.avatarId) is not None

        @inlineCallbacks
        def get_addresses():
            offlinecash_addresses = {}
            for ticker in offlinecash.keys():
                offlinecash_addresses[ticker] = yield self.administrator.get_current_address('offlinecash', ticker)
            returnValue(offlinecash_addresses)

        def _cb(offlinecash_addresses):
            t = self.jinja_env.get_template('wallets.html')
            request.write(t.render(contracts=contracts, onlinecash=onlinecash, offlinecash=offlinecash,
                            offlinecash_addresses=offlinecash_addresses, bitgo_auth=bitgo_auth,
                            debug=self.administrator.component.debug,
                            multisigcash=multisigcash,
                            use_production="false" if self.administrator.component.testnet else "true").encode('utf-8'))
            request.finish()

        d = get_addresses()
        d.addCallback(_cb).addErrback(self.sputnik_error_callback, request).addErrback(self.generic_error_callback, request)
        return NOT_DONE_YET

    def transfer_from_hot_wallet(self, request):
        ticker = request.args['contract'][0]
        destination = request.args['destination'][0]
        quantity_ui = Decimal(request.args['quantity'][0])
        d = self.administrator.transfer_from_hot_wallet(ticker, quantity_ui, destination)
        def _cb(ignored):
            request.write(redirectTo("/wallets", request))
            request.finish()

        d.addCallback(_cb).addErrback(self.sputnik_error_callback, request).addErrback(self.generic_error_callback, request)
        return NOT_DONE_YET

    def transfer_from_multisig_wallet(self, request):
        ticker = request.args['contract'][0]
        destination = request.args['destination'][0]
        quantity_ui = Decimal(request.args['quantity'][0])
        if self.administrator.get_bitgo_token(self.avatarId) is None:
            raise BITGO_TOKEN_INVALID

        multisig = {'token': self.administrator.get_bitgo_token(self.avatarId),
                    'otp': request.args['otp'][0]}
        d = self.administrator.transfer_from_multisig_wallet(ticker, quantity_ui, destination, multisig=multisig)
        def _cb(ignored):
            request.write(redirectTo("/wallets", request))
            request.finish()

        d.addCallback(_cb).addErrback(self.sputnik_error_callback, request).addErrback(self.generic_error_callback, request)
        return NOT_DONE_YET

    def new_permission_group(self, request):
        """Create a new permission group and then return the permission groups page

        """
        if 'permissions' in request.args:
            permissions = request.args['permissions']
        else:
            permissions = []
        self.administrator.new_permission_group(request.args['name'][0], permissions)
        return redirectTo('/permission_groups', request)


    def change_permission_group(self, request):
        """Change a user's permission group and then return the user details page

        """
        username = request.args['username'][0]
        id = int(request.args['id'][0])
        d = self.administrator.change_permission_group(username, id)
        def _cb(result, request):
            request.write(redirectTo("/user_details?username=%s" % request.args['username'][0], request))
            request.finish()

        d.addCallback(_cb, request).addErrback(self.sputnik_error_callback, request).addErrback(self.generic_error_callback, request)
        return NOT_DONE_YET

    def fee_groups(self, request):
        fee_groups = self.administrator.get_fee_groups()
        fee_group_problems = self.administrator.check_fee_groups(fee_groups)
        t = self.jinja_env.get_template('fee_groups.html')
        return t.render(fee_groups=fee_groups, fee_group_problems=fee_group_problems).encode('utf-8')

    def change_fee_group(self, request):
        username = request.args['username'][0]
        id = int(request.args['id'][0])
        d = self.administrator.change_fee_group(username, id)
        def _cb(result, request):
            request.write(redirectTo("/user_details?username=%s" % request.args['username'][0], request))
            request.finish()

        d.addCallback(_cb, request).addErrback(self.sputnik_error_callback, request).addErrback(self.generic_error_callback, request)
        return NOT_DONE_YET

    def modify_fee_group(self, request):
        id = int(request.args['id'][0])
        name = request.args['name'][0]
        aggressive_factor = int(request.args['aggressive_factor'][0])
        passive_factor = int(request.args['passive_factor'][0])
        withdraw_factor = int(request.args['withdraw_factor'][0])
        deposit_factor = int(request.args['deposit_factor'][0])
        self.administrator.modify_fee_group(id, name, aggressive_factor, passive_factor, withdraw_factor, deposit_factor)
        return redirectTo('/fee_groups', request)

    def new_fee_group(self, request):
        name = request.args['name'][0]
        aggressive_factor = int(request.args['aggressive_factor'][0])
        passive_factor = int(request.args['passive_factor'][0])
        withdraw_factor = int(request.args['withdraw_factor'][0])
        deposit_factor = int(request.args['deposit_factor'][0])
        self.administrator.new_fee_group(name, aggressive_factor, passive_factor, withdraw_factor, deposit_factor)
        return redirectTo('/fee_groups', request)

    def contracts(self, request):
        contracts = self.administrator.get_contracts()
        t = self.jinja_env.get_template('contracts.html')
        return t.render(contracts=contracts, debug=self.administrator.component.debug).encode('utf-8')

    def edit_contract(self, request):
        ticker = request.args['ticker'][0]
        args = {}
        for key in ["description", "full_description", "cold_wallet_address", "multisig_wallet_address",
                    "deposit_instructions"]:
            if key in request.args:
                args[key] = request.args[key][0].decode('utf-8')

        for key in ["fees", "hot_wallet_limit", "deposit_base_fee", "deposit_bps_fee", "withdraw_base_fee",
                    "withdraw_bps_fee"]:
            if key in request.args:
                args[key] = int(request.args[key][0])

        if "expiration" in request.args:
            args['expiration'] = parser.parse(request.args['expiration'][0])

        if "period" in request.args:
            try:
                args['period'] = timedelta(days=int(request.args['period'][0]))
            except ValueError:
                log.msg("%s not a valid period" % request.args['period'][0])

        self.administrator.edit_contract(ticker, args)
        return redirectTo('/contracts', request)

    def clear_contract(self, request):
        if 'price' in request.args:
            d = self.administrator.clear_contract(request.args['ticker'][0], Decimal(request.args['price'][0]))
        else:
            d = self.administrator.clear_contract(request.args['ticker'][0])

        def clearing_done(result):
            request.write(redirectTo('/contracts', request).encode('utf-8'))
            request.finish()

        d.addCallback(clearing_done)
        return NOT_DONE_YET

    def liquidate_all(self, request):
        self.administrator.liquidate_all(request.args['username'][0])
        return redirectTo('/margins', request)

    def liquidate_position(self, request):
        self.administrator.liquidate_position(request.args['username'][0], request.args['ticker'][0])
        return redirectTo('/user_details?username=%s' % request.args['username'][0], request)

    def withdrawals(self, request):
        withdrawals = self.administrator.get_withdrawals()
        t = self.jinja_env.get_template('withdrawals.html')
        return t.render(withdrawals=withdrawals).encode('utf-8')

    def deposits(self, request):
        deposits = self.administrator.get_deposits()
        t = self.jinja_env.get_template('deposits.html')
        return t.render(deposits=deposits).encode('utf-8')

    def order_book(self, request):
        ticker = request.args['ticker'][0]
        d = self.administrator.get_order_book(ticker)

        def got_order_book(order_book):
            t = self.jinja_env.get_template('order_book.html')
            rendered = t.render(ticker=ticker, order_book=order_book)
            request.write(rendered.encode('utf-8'))
            request.finish()

        d.addCallback(got_order_book).addErrback(self.sputnik_error_callback, request).addErrback(self.generic_error_callback, request)
        return NOT_DONE_YET

    def cancel_order(self, request):
        id = int(request.args['id'][0])
        username = request.args['username'][0]
        d = self.administrator.cancel_order(username, id)

        def _cb(result, request):
            request.write(redirectTo("/order_book?ticker=%s" % request.args['ticker'][0], request))
            request.finish()

        d.addCallback(_cb, request).addErrback(self.sputnik_error_callback, request).addErrback(self.generic_error_callback, request)
        return NOT_DONE_YET

    def ledger(self, request):
        """Show use the details of a single jounral entry

        """
        self.administrator.expire_all()
        journal_id = request.args['id'][0]
        journal = self.administrator.get_journal(journal_id)
        t = self.jinja_env.get_template('ledger.html')
        return t.render(journal=journal).encode('utf-8')

    def user_list(self, request):
        """Give us a list of all the users

        """
        # We dont need to expire here because the user_list doesn't show
        # anything that is modified by anyone but the administrator
        users = self.administrator.get_users()
        t = self.jinja_env.get_template('user_list.html')
        return t.render(users=users).encode('utf-8')

    def reset_password(self, request):
        """Reset someone's password with the given plaintext

        """
        self.administrator.reset_password_plaintext(request.args['username'][0], request.args['new_password'][0])
        return redirectTo("/user_details?username=%s" % request.args['username'][0], request)

    def reset_admin_password(self, request):
        """Reset an administrator password if we know the old password

        """
        self.administrator.reset_admin_password(self.avatarId, self.calc_ha1(request.args['old_password'][0]),
                                                self.calc_ha1(request.args['new_password'][0]))
        return redirectTo('/admin', request)

    def force_reset_admin_password(self, request):
        """Reset an administrator password even if we don't know the old password

        """
        self.administrator.force_reset_admin_password(request.args['username'][0], self.calc_ha1(request.args['password'][0],
                                                                                           username=
                                                                                           request.args['username'][0]))

        return redirectTo('/admin_list', request)

    def admin(self, request):
        """Give me the page where I can edit my admin password

        """
        t = self.jinja_env.get_template('admin.html')
        return t.render(username=self.avatarId).encode('utf-8')

    @util.timed
    def user_orders(self, request):
        user = self.administrator.get_user(request.args['username'][0])
        page = int(request.args['page'][0])
        orders, order_pages = self.administrator.get_orders(user, page)
        t = self.jinja_env.get_template('user_orders.html')
        rendered = t.render(user=user, orders=orders, order_pages=order_pages, orders_page=page,
                            min_range=max(page - 10, 0), max_range=min(order_pages, page + 10))
        return rendered.encode('utf-8')

    @util.timed
    def user_postings(self, request):
        user = self.administrator.get_user(request.args['username'][0])
        page = int(request.args['page'][0])
        contract = self.administrator.get_contract(request.args['ticker'][0])
        position = self.administrator.get_position(user, contract)
        postings, posting_pages = self.administrator.get_postings(user, contract, page=page)
        t = self.jinja_env.get_template('user_postings.html')
        postings_by_ticker = {contract.ticker: {'postings': postings,
                                                'posting_pages': posting_pages,
                                                'page': page,
                                                'min_range': max(page - 10, 0),
                                                'max_range': min(posting_pages, page + 10)}}
        rendered = t.render(user=user, position=position, postings_by_ticker=postings_by_ticker)
        return rendered.encode('utf-8')


    @util.timed
    def user_details(self, request):
        """Show all the details for a particular user

        """
        # We are getting trades and positions which things other than the administrator
        # are modifying, so we need to do an expire here
        self.administrator.expire_all()

        user = self.administrator.get_user(request.args['username'][0])
        permission_groups = self.administrator.get_permission_groups()
        zendesk_domain = self.administrator.component.zendesk_domain

        if 'orders_page' in request.args:
            orders_page = int(request.args['orders_page'][0])
        else:
            orders_page = 0

        orders, order_pages = self.administrator.get_orders(user, page=orders_page)
        fee_groups = self.administrator.get_fee_groups()

        t = self.jinja_env.get_template('user_details.html')
        rendered = t.render(user=user,
                            zendesk_domain=zendesk_domain,
                            fee_groups=fee_groups,
                            debug=self.administrator.component.debug, permission_groups=permission_groups,
                            orders=orders, order_pages=order_pages, orders_page=orders_page,
                            min_range=max(orders_page - 10, 0), max_range=min(order_pages, orders_page + 10))
        return rendered.encode('utf-8')

    def adjust_position(self, request):
        """Adjust a user's position then go back to his detail page

        """
        d = self.administrator.adjust_position(request.args['username'][0], request.args['contract'][0],
                                           Decimal(request.args['quantity'][0]), self.avatarId)
        def _cb(result, request):
            request.write(redirectTo("/user_details?username=%s" % request.args['username'][0], request))
            request.finish()

        d.addCallback(_cb, request).addErrback(self.sputnik_error_callback, request).addErrback(self.generic_error_callback, request)
        return NOT_DONE_YET

    def transfer_position(self, request):
        """Transfer a position from a user and go back to his details page

        """

        d = self.administrator.transfer_position(request.args['contract'][0], request.args['from_user'][0],
                                             request.args['to_user'][0], Decimal(request.args['quantity'][0]),
                                             "%s (%s)" % (request.args['note'][0], self.avatarId))
        def _cb(result, request):
            request.write(redirectTo("/user_details?username=%s" % request.args['username'][0], request))
            request.finish()

        d.addCallback(_cb, request).addErrback(self.sputnik_error_callback, request).addErrback(self.generic_error_callback, request)
        return NOT_DONE_YET

    def rescan_address(self, request):
        """Send a message to the cashier to rescan an address

        """
        self.administrator.rescan_address(request.args['address'][0])
        return redirectTo("/user_details?username=%s" % request.args['username'][0], request)

    def manual_deposit(self, request):
        """Tell the cashier that an address received a certain amount of money

        """
        d = self.administrator.manual_deposit(request.args['address'][0], Decimal(request.args['quantity'][0]), self.avatarId)
        def _cb(result, request):
            request.write(redirectTo("/user_details?username=%s" % request.args['username'][0], request))
            request.finish()

        d.addCallback(_cb, request).addErrback(self.sputnik_error_callback, request).addErrback(self.generic_error_callback, request)
        return NOT_DONE_YET

    def admin_list(self, request):
        """List all the admin users

        """
        admin_users = self.administrator.get_admin_users()
        t = self.jinja_env.get_template('admin_list.html')
        return t.render(admin_users=admin_users).encode('utf-8')

    def new_admin_user(self, request):
        """Create a new admin user, then return list of admin users

        """
        self.administrator.new_admin_user(request.args['username'][0], self.calc_ha1(request.args['password'][0],
                                                                                     username=request.args['username'][
                                                                                         0]),
                                          int(request.args['level'][0]))
        return redirectTo('/admin_list', request)

    def set_admin_level(self, request):
        """Set the level of a certain admin user, and then return the list of admin users

        """
        self.administrator.set_admin_level(request.args['username'][0], int(request.args['level'][0]))
        return redirectTo('/admin_list', request)

    def balance_sheet(self, request):
        """Display the full balance sheet of the system

        """

        balance_sheet = self.administrator.get_balance_sheet()

        t = self.jinja_env.get_template('balance_sheet.html')
        rendered = t.render(balance_sheet=balance_sheet, timestamp=util.timestamp_to_dt(balance_sheet['timestamp']))
        return rendered.encode('utf-8')


class AdminWebExport(ComponentExport):
    def __init__(self, administrator):
        self.administrator = administrator
        ComponentExport.__init__(self, administrator)

    @session_aware
    def bitgo_oauth_token(self, code, admin_user):
        return self.administrator.bitgo_oauth_token(code, admin_user)

    @session_aware
    def bitgo_oauth_clear(self, admin_user):
        return self.administrator.bitgo_oauth_clear(admin_user)

    @session_aware
    def get_margins(self):
        return self.administrator.get_margins()

    @session_aware
    def get_withdrawals(self):
        return self.administrator.get_withdrawals()

    @session_aware
    def get_deposits(self):
        return self.administrator.get_deposits()

    @session_aware
    def rescan_address(self, address):
        return self.administrator.cashier.rescan_address(address)

    @session_aware
    def process_withdrawal(self, id, online, cancel, admin_username, multisig):
        return self.administrator.process_withdrawal(id, online, cancel, admin_username=admin_username, multisig=multisig)

    @session_aware
    def expire_all(self):
        return self.administrator.expire_all()

    @session_aware
    def new_permission_group(self, name, permissions):
        return self.administrator.new_permission_group(name, permissions)

    @session_aware
    def change_permission_group(self, username, id):
        return self.administrator.change_permission_group(username, id)

    @session_aware
    def get_fee_groups(self):
        return self.administrator.get_fee_groups()

    @session_aware
    def check_fee_groups(self, fee_groups):
        return self.administrator.check_fee_groups(fee_groups)

    @session_aware
    def change_fee_group(self, username, id):
        return self.administrator.change_fee_group(username, id)

    @session_aware
    def modify_fee_group(self, id, name, aggressive_factor, passive_factor, withdraw_factor, deposit_factor):
        return self.administrator.modify_fee_group(id, name, aggressive_factor, passive_factor, withdraw_factor, deposit_factor)

    @session_aware
    def new_fee_group(self, name, aggressive_factor, passive_factor, withdraw_factor, deposit_factor):
        return self.administrator.new_fee_group(name, aggressive_factor, passive_factor, withdraw_factor, deposit_factor)

    @session_aware
    def get_contracts(self):
        return self.administrator.get_contracts()

    @session_aware
    def edit_contract(self, ticker, args):
        return self.administrator.edit_contract(ticker, args)

    @session_aware
    def clear_contract(self, ticker, price_ui=None):
        return self.administrator.clear_contract(ticker, price_ui=price_ui)

    @session_aware
    def get_order_book(self, ticker):
        return self.administrator.get_order_book(ticker)

    @session_aware
    def cancel_order(self, username, id):
        return self.administrator.cancel_order(username, id)

    @session_aware
    def get_journal(self, id):
        return self.administrator.get_journal(id)

    @session_aware
    def get_users(self):
        return self.administrator.get_users()

    @session_aware
    def reset_password_plaintext(self, username, new_password):
        return self.administrator.reset_password_plaintext(username, new_password)

    @session_aware
    def reset_admin_password(self, username, old_password_hash, new_password_hash):
        return self.administrator.reset_admin_password(username, old_password_hash=old_password_hash,
                                                       new_password_hash=new_password_hash)

    @session_aware
    def get_user(self, username):
        return self.administrator.get_user(username)

    @session_aware
    def get_positions(self, username=None):
        return self.administrator.get_positions(username=username)

    @session_aware
    def get_current_address(self, username, ticker):
        return self.administrator.get_current_address(username, ticker)

    @session_aware
    def transfer_from_hot_wallet(self, ticker, quantity_ui, destination):
        return self.administrator.transfer_from_hot_wallet(ticker, quantity_ui, destination)

    @session_aware
    def transfer_from_multisig_wallet(self, ticker, quantity_ui, destination, multisig):
        return self.administrator.transfer_from_multisig_wallet(ticker, quantity_ui, destination, multisig)

    @session_aware
    def new_admin_user(self, username, password_hash, level):
        return self.administrator.new_admin_user(username, password_hash, level)

    @session_aware
    def set_admin_level(self, username, level):
        return self.administrator.set_admin_level(username, level)

    @session_aware
    def get_permission_groups(self):
        return self.administrator.get_permission_groups()

    @session_aware
    def transfer_position(self, ticker, from_user, to_user, quantity_ui, note):
        return self.administrator.transfer_position(ticker, from_user, to_user, quantity_ui, note)

    @session_aware
    def adjust_position(self, username, ticker, quantity, admin_username):
        return self.administrator.adjust_position(username, ticker, quantity, admin_username=admin_username)

    @session_aware
    def get_contract(self, ticker):
        return self.administrator.get_contract(ticker)

    @session_aware
    def get_orders(self, user, page):
        return self.administrator.get_orders(user, page)

    @session_aware
    def manual_deposit(self, address, quantity, admin_username):
        return self.administrator.manual_deposit(address, quantity, admin_username=admin_username)

    @session_aware
    def force_reset_admin_password(self, username, password_hash):
        return self.administrator.force_reset_admin_password(username, password_hash)

    @session_aware
    def get_balance_sheet(self):
        return self.administrator.get_balance_sheet()

    @session_aware
    def get_admin_users(self):
        return self.administrator.get_admin_users()

    @session_aware
    def get_position(self, user, contract):
        return self.administrator.get_position(user, contract)

    @session_aware
    def get_postings(self, user, contract, page):
        return self.administrator.get_postings(user, contract, page)

    @session_aware
    def get_bitgo_token(self, admin_user):
        return self.administrator.get_bitgo_token(admin_user)

    @session_aware
    def initialize_multisig(self, ticker, public_key, multisig={}):
        return self.administrator.initialize_multisig(ticker, public_key, multisig)

class PasswordChecker(object):
    """Checks admin users passwords against the hash stored in the db

    """
    implements(ICredentialsChecker)
    credentialInterfaces = (IUsernameDigestHash,)

    def __init__(self, session):
        """
        :param session: The sql alchemy session
        """
        self.session = session

    def requestAvatarId(self, credentials):
        """
        :param credentials: The username & password that the user is attempting
        :returns: deferred
        """

        username = credentials.username
        try:
            admin_user = self.session.query(models.AdminUser).filter_by(username=username).one()
        except NoResultFound as e:
            return defer.fail(credError.UnauthorizedLogin("No such administrator"))
        except Exception as e:
            log.err(e)
            self.session.rollback()
            raise e

        # Allow login if there is no password. Use this for
        # setup only
        if admin_user.password_hash == "":
            return defer.succeed(username)

        if credentials.checkHash(admin_user.password_hash):
            return defer.succeed(username)
        else:
            return defer.fail(credError.UnauthorizedLogin("Bad password"))


class SimpleRealm(object):
    implements(IRealm)

    def __init__(self, administrator, session, digest_factory, admin_base_uri):
        self.administrator = administrator
        self.session = session
        self.digest_factory = digest_factory
        self.admin_base_uri = admin_base_uri

    def requestAvatar(self, avatarId, mind, *interfaces):
        if IResource in interfaces:
            try:
                user = self.session.query(models.AdminUser).filter_by(username=avatarId).one()
                # If the pw isn't set yet, only allow level 0 access
                if user.password_hash == "":
                    avatarLevel = 0
                else:
                    avatarLevel = user.level
            except Exception as e:
                self.session.rollback()
                print "Exception: %s" % e

            ui_resource = AdminWebUI(self.administrator, avatarId, avatarLevel, self.digest_factory, self.admin_base_uri)
            api_resource = AdminAPI(self.administrator, avatarId, avatarLevel)
            ui_resource.putChild('api', api_resource)

            return IResource, ui_resource, lambda: None
        else:
            raise NotImplementedError


class WebserverExport(ComponentExport):
    """
    For security reasons, the webserver only has access to a limit subset of
        the administrator functionality. This is exposed here.
    """

    def __init__(self, administrator):
        self.administrator = administrator
        ComponentExport.__init__(self, administrator)

    @export
    @session_aware
    @schema("rpc/administrator.json#get_new_api_credentials")
    def get_new_api_credentials(self, username, expiration):
        return self.administrator.get_new_api_credentials(username, expiration)

    @export
    @session_aware
    @schema("rpc/administrator.json#check_and_update_api_nonce")
    def check_and_update_api_nonce(self, username, nonce):
        return self.administrator.check_and_update_api_nonce(username, nonce)

    @export
    @session_aware
    @schema("rpc/administrator.json#make_account")
    def make_account(self, username, password):
        return self.administrator.make_account(username, password)

    @export
    @session_aware
    @schema("rpc/administrator.json#change_profile")
    def change_profile(self, username, profile):
        return self.administrator.change_profile(username, profile)

    @export
    @session_aware
    @schema("rpc/administrator.json#reset_password_hash")
    def reset_password_hash(self, username, old_password_hash, new_password_hash, token=None):
        return self.administrator.reset_password_hash(username, old_password_hash, new_password_hash, token=token)

    @export
    @session_aware
    @schema("rpc/administrator.json#get_reset_token")
    def get_reset_token(self, username):
        return self.administrator.get_reset_token(username)
    
    @export
    @session_aware
    @schema("rpc/administrator.json#enable_totp")
    def enable_totp(self, username):
        return self.administrator.enable_totp(username)
    
    @export
    @session_aware
    @schema("rpc/administrator.json#verify_totp")
    def verify_totp(self, username, otp):
        return self.administrator.verify_totp(username, otp)
    
    @export
    @session_aware
    @schema("rpc/administrator.json#disable_totp")
    def disable_totp(self, username, otp):
        return self.administrator.disable_totp(username, otp)
    
    @export
    @session_aware
    @schema("rpc/administrator.json#check_totp")
    def check_totp(self, username, otp):
        return self.administrator.check_totp(username, otp)

    @export
    @session_aware
    @schema("rpc/administrator.json#register_support_ticket")
    def register_support_ticket(self, username, nonce, type, foreign_key):
        return self.administrator.register_support_ticket(username, nonce, type, foreign_key)

    @export
    @session_aware
    @schema("rpc/administrator.json#request_support_nonce")
    def request_support_nonce(self, username, type):
        return self.administrator.request_support_nonce(username, type)

    @export
    @session_aware
    @schema("rpc/administrator.json#get_audit")
    def get_audit(self):
        return self.administrator.get_audit()

    @export
    @session_aware
    @schema("rpc/administrator.json#get_profile")
    def get_profile(self, username):
        return self.administrator.get_profile(username)

class CronExport(ComponentExport):
    def __init__(self, administrator):
        self.administrator = administrator
        ComponentExport.__init__(self, administrator)

    @export
    @session_aware
    @schema("rpc/administrator.json#mail_statements")
    def mail_statements(self, period):
        return self.administrator.mail_statements(period)

    @export
    @session_aware
    @schema("rpc/administrator.json#mtm_futures")
    def mtm_futures(self):
        return self.administrator.mtm_futures()

    @export
    @session_aware
    @schema("rpc/administrator.json#notify_expired")
    def notify_expired(self):
        return self.administrator.notify_expired()


class TicketServerExport(ComponentExport):
    """The administrator exposes these functions to the TicketServer

    """

    def __init__(self, administrator):
        self.administrator = administrator
        ComponentExport.__init__(self, administrator)

    @export
    @session_aware
    @schema("rpc/administrator.json#check_support_nonce")
    def check_support_nonce(self, username, nonce, type):
        return self.administrator.check_support_nonce(username, nonce, type)

    @export
    @session_aware
    @schema("rpc/administrator.json#register_support_ticket")
    def register_support_ticket(self, username, nonce, type, foreign_key):
        return self.administrator.register_support_ticket(username, nonce, type, foreign_key)


if __name__ == "__main__":
    log.startLogging(sys.stdout)

    session = database.make_session()

    debug = config.getboolean("administrator", "debug")
    accountant = AccountantProxy("dealer",
                                 config.get("accountant", "administrator_export"),
                                 config.getint("accountant", "administrator_export_base_port"))

    # Slow accountant with 20 minute timeout
    accountant_slow = AccountantProxy("dealer",
                                 config.get("accountant", "administrator_export"),
                                 config.getint("accountant", "administrator_export_base_port"),
                                 timeout=60*20)

    # Set the cashier timeout to 5 seconds because sending multisig cash may
    # take a little bit
    cashier = dealer_proxy_async(config.get("cashier", "administrator_export"), timeout=5)
    watchdog(config.get("watchdog", "administrator"))
    webserver = dealer_proxy_async(config.get("webserver", "administrator_export"))

    if config.getboolean("webserver", "ssl"):
        protocol = 'https'
    else:
        protocol = 'http'

    base_uri = "%s://%s:%d" % (protocol,
                               config.get("webserver", "www_address"),
                               config.getint("webserver", "www_port"))
    administrator_email = config.get("administrator", "email")
    zendesk_domain = config.get("ticketserver", "zendesk_domain")

    user_limit = config.getint("administrator", "user_limit")
    bs_cache_update = config.getint("administrator", "bs_cache_update")

    engine_base_port = config.getint("engine", "administrator_base_port")
    engines = {}
    for contract in session.query(models.Contract).filter_by(active=True):
        engines[contract.ticker] = dealer_proxy_async("tcp://127.0.0.1:%d" %
                                                      (engine_base_port + int(contract.id)))

    bitgo_config = {'use_production': not config.getboolean("cashier", "testnet"),
                    'client_id': config.get("bitgo", "client_id"),
                    'client_secret': config.get("bitgo", "client_secret")}

    bitgo = BitGo(**bitgo_config)
    bitgo_private_key_file = config.get("cashier", "bitgo_private_key_file")

    sendmail = Sendmail(administrator_email)
    if config.getboolean("administrator", "nexmo_enable"):
        nexmo = Nexmo(config.get("administrator", "nexmo_api_key"),
                    config.get("administrator", "nexmo_api_secret"),
                    config.get("exchange_info", "exchange_name"),
                    config.get("administrator", "nexmo_from_code"))
        messenger = Messenger(sendmail, nexmo)
    else:
        messenger = Messenger(sendmail)

    administrator = Administrator(session, accountant, cashier, engines,
                                  zendesk_domain,
                                  accountant_slow, webserver,
                                  debug=debug, base_uri=base_uri,
                                  messenger=messenger,
                                  user_limit=user_limit,
                                  bs_cache_update_period=bs_cache_update,
                                  bitgo=bitgo,
                                  bitgo_private_key_file=bitgo_private_key_file,
                                  testnet=config.getboolean("cashier", "testnet"),
                                  )

    webserver_export = WebserverExport(administrator)
    ticketserver_export = TicketServerExport(administrator)
    cron_export = CronExport(administrator)

    router_share_async(webserver_export,
                       config.get("administrator", "webserver_export"))
    router_share_async(ticketserver_export,
                       config.get("administrator", "ticketserver_export"))
    router_share_async(cron_export,
                       config.get("administrator", "cron_export"))

    checkers = [PasswordChecker(session)]
    digest_factory = DigestCredentialFactory('md5', 'Sputnik Admin Interface')
    admin_base_uri = "%s://%s:%d" % (protocol,
                                     config.get("webserver", "www_address"),
                                     config.getint("administrator", "UI_port"))

    wrapper = HTTPAuthSessionWrapper(Portal(SimpleRealm(AdminWebExport(administrator), session, digest_factory,
                                                        admin_base_uri),
                                            checkers),
                                     [digest_factory])

    # SSL
    if config.getboolean("webserver", "ssl"):
        key = config.get("webserver", "ssl_key")
        cert = config.get("webserver", "ssl_cert")
        cert_chain = config.get("webserver", "ssl_cert_chain")
        contextFactory = ChainedOpenSSLContextFactory(key, cert_chain)
        reactor.listenSSL(config.getint("administrator", "UI_port"), Site(resource=wrapper),
                          contextFactory,
                          interface=config.get("administrator", "interface"))
    else:
        reactor.listenTCP(config.getint("administrator", "UI_port"), Site(resource=wrapper),
                          interface=config.get("administrator", "interface"))

    # Ticketserver

    administrator_for_ticketserver =  dealer_proxy_async(config.get("administrator", "ticketserver_export"))
    zendesk = Zendesk(config.get("ticketserver", "zendesk_domain"),
                      config.get("ticketserver", "zendesk_token"),
                      config.get("ticketserver", "zendesk_email"))

    if config.getboolean("ticketserver", "enable_blockscore"):
        blockscore = BlockScore(config.get("ticketserver", "blockscore_api_key"))
    else:
        blockscore = None

    ticketserver =  TicketServer(administrator_for_ticketserver, zendesk, blockscore=blockscore)

    interface = config.get("webserver", "interface")
    if config.getboolean("webserver", "www"):
        web_dir = File(config.get("webserver", "www_root"))
        web_dir.putChild('ticket_server', ticketserver)
        web = Site(web_dir)
        port = config.getint("webserver", "www_port")
        if config.getboolean("webserver", "ssl"):
            reactor.listenSSL(port, web, contextFactory, interface=interface)
        else:
            reactor.listenTCP(port, web, interface=interface)
    else:
        base_resource = Resource()
        base_resource.putChild('ticket_server', ticketserver)
        reactor.listenTCP(config.getint("ticketserver", "ticketserver_port"), Site(base_resource),
                                        interface="127.0.0.1")


    reactor.run()

