#!/usr/bin/python

"""
The administrator modifies database objects. It is allowed to access User
    objects. For other objects it delegates to appropriate services. This
    ensures there are no race conditions.

The interface is exposed with ZMQ RPC running under Twisted. Many of the RPC
    calls block, but performance is not crucial here.

"""

import sys
import collections
from datetime import datetime
import json
import copy
import string
import pickle

from twisted.web.resource import Resource, IResource
from twisted.web.server import Site
from twisted.web.guard import HTTPAuthSessionWrapper, DigestCredentialFactory
from twisted.web.server import NOT_DONE_YET
from twisted.web.util import redirectTo
from twisted.internet.task import LoopingCall
from zope.interface import implements
from twisted.internet import reactor, defer
from twisted.python import log
from twisted.cred.portal import IRealm, Portal
from twisted.cred.checkers import ICredentialsChecker
from twisted.cred.credentials import IUsernameDigestHash
from twisted.cred import error as credError
from twisted.cred._digest import calcHA1
from jinja2 import Environment, FileSystemLoader
import Crypto.Random.random
import sqlalchemy.orm.exc
from sqlalchemy import func
import Crypto.Random.random
from sqlalchemy.orm.exc import NoResultFound
from autobahn.wamp1.protocol import WampCraProtocol
from dateutil import parser

import config
import database
import models
from util import ChainedOpenSSLContextFactory
import util
from sendmail import Sendmail
from watchdog import watchdog
from accountant import AccountantProxy
from zmq_util import export, router_share_async, dealer_proxy_async, push_proxy_async, ComponentExport
from rpc_schema import schema


class AdministratorException(Exception): pass


USERNAME_TAKEN = AdministratorException(1, "Username is already taken.")
NO_SUCH_USER = AdministratorException(2, "No such user.")
FAILED_PASSWORD_CHANGE = AdministratorException(3, "Password does not match")
INVALID_TOKEN = AdministratorException(4, "No such token found.")
EXPIRED_TOKEN = AdministratorException(5, "Token expired or already used.")
TICKET_EXISTS = AdministratorException(7, "Ticket already exists")
USER_LIMIT_REACHED = AdministratorException(8, "User limit reached")
ADMIN_USERNAME_TAKEN = AdministratorException(9, "Administrator username is already taken")
INVALID_SUPPORT_NONCE = AdministratorException(10, "Invalid support nonce")
SUPPORT_NONCE_USED = AdministratorException(11, "Support nonce used already")
INVALID_CURRENCY_QUANTITY = AdministratorException(12, "Invalid currency quantity")


def session_aware(func):
    def new_func(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception, e:
            self.session.rollback()
            raise e

    return new_func


class Administrator:
    """
    The main administrator class. This makes changes to the database.
    """

    def __init__(self, session, accountant, cashier, engines,
                 zendesk_domain,
                 debug=False, base_uri=None, sendmail=None,
                 template_dir='admin_templates',
                 user_limit=500,
                 bs_cache_update_period=86400):
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
        self.cashier = cashier
        self.engines = engines
        self.zendesk_domain = zendesk_domain
        self.debug = debug
        self.template_dir = template_dir
        self.jinja_env = Environment(loader=FileSystemLoader(template_dir))
        self.base_uri = base_uri
        self.sendmail = sendmail
        self.user_limit = user_limit
        self.page_size = 10

        self.load_bs_cache()
        # Initialize the balance sheet cache
        if bs_cache_update_period is not None:
            self.bs_updater = LoopingCall(self.update_bs_cache)
            self.bs_updater.start(bs_cache_update_period, now=True)
        else:
            self.update_bs_cache()

    @session_aware
    def make_account(self, username, password):
        """Makes a user account with the given password

        :param username: The new username
        :type username: str
        :param password: The new password hash with salt
        :type password: str
        :returns: bool
        :raises: USER_LIMIT_REACHED, USERNAME_TAKEN, OUT_OF_ADDRESSES
        """
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
        self.session.add(user)

        contracts = self.session.query(models.Contract).filter_by(
            contract_type='cash').all()
        for contract in contracts:
            position = models.Position(user, contract)
            self.session.add(position)

        self.session.commit()

        log.msg("Account created for %s" % username)
        return True

    @session_aware
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

        user.email = profile.get("email", user.email)
        user.nickname = profile.get("nickname", user.nickname)
        self.session.merge(user)

        self.session.commit()
        log.msg("Profile changed for %s to %s/%s" % (user.username, user.email, user.nickname))
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

    @session_aware
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
        extra = {"salt": salt, "keylen": 32, "iterations": 1000}
        password = WampCraProtocol.deriveKey(new_password, extra)
        user.password = "%s:%s" % (salt, password)
        self.session.add(user)
        self.session.commit()
        return True

    @session_aware
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

        [salt, hash] = user.password.split(':')

        if hash != old_password_hash and token is None:
            raise FAILED_PASSWORD_CHANGE
        elif hash != old_password_hash:
            # Check token
            token = self.check_token(username, token)
            token.used = True
            self.session.add(token)

        user.password = "%s:%s" % (salt, new_password_hash)

        self.session.add(user)
        self.session.commit()
        return True

    @session_aware
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
        # Now email the token
        t = self.jinja_env.get_template('reset_password.email')
        content = t.render(token=token.token, expiration=token.expiration.strftime("%Y-%m-%d %H:%M:%S %Z"),
                           user=user, base_uri=self.base_uri).encode('utf-8')

        # Now email the token
        log.msg("Sending mail: %s" % content)
        s = self.sendmail.send_mail(content, to_address=user.email,
                                    subject='Reset password link enclosed')

        return True

    def expire_all(self):
        """Use this to expire all objects in the session, because other processes may have updated things in the db

        """
        self.session.expire_all()

    def get_users(self):
        """Give us an array of all the users

        :returns: list -- list of models.User
        """
        users = self.session.query(models.User).all()
        return users

    def get_admin_users(self):
        """Give us an array of all the admin users

        :returns: list -- list of models.AdminUser
        """
        admin_users = self.session.query(models.AdminUser).all()
        return admin_users

    @util.timed
    def get_user(self, username):
        """Give us the details of a particular user

        :param username: the user
        :type username: str
        :returns: models.User
        """
        user = self.session.query(models.User).filter_by(username=username).one()

        return user

    @session_aware
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

    @session_aware
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

    @session_aware
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

    @session_aware
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
                raise FAILED_PASSWORD_CHANGE

        user.password_hash = new_password_hash
        self.session.add(user)
        self.session.commit()
        log.msg("Admin user %s has password reset" % username)
        return True

    @session_aware
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

    def get_positions(self):
        """Get all the positions that exist

        :returns: list -- models.Position
        """
        positions = self.session.query(models.Position).all()
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

    def cancel_order(self, username, id):
        self.accountant.cancel_order(username, id)

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
        self.accountant.adjust_position(username, ticker, quantity, admin_username)

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
        self.accountant.transfer_position(from_user, ticker, 'debit', quantity, note, uid)
        self.accountant.transfer_position(to_user, ticker, 'credit', quantity, note, uid)

    def clear_contract(self, ticker, price_ui):
        contract = util.get_contract(self.session, ticker)
        price = util.price_to_wire(contract, price_ui)
        uid = util.get_uid()

        # Don't try to clear if the contract is not active
        if not contract.active:
            return

        # Mark contract inactive
        try:
            contract.active = False
            self.session.add(contract)
            self.session.commit()
        except Exception as e:
            log.err("Unable to mark contract inactive %s" % e)
        else:
            d = self.accountant.clear_contract(None, ticker, price, uid)
            # TODO: if this is an early clearing, reactivate the contract after clear_contract is done
            # We need to make sure that the timeout here is long, because clear_contract
            # won't return for a while
            #
            # How do we ensure that the accountants know that it is reactivated?
            # send a ZMQ message to them all?


    def manual_deposit(self, address, quantity_ui, admin_username):
        address_db = self.session.query(models.Addresses).filter_by(address=address).one()
        quantity = util.quantity_to_wire(address_db.contract, quantity_ui)
        if quantity % address_db.contract.lot_size != 0:
            log.err("Manual deposit for invalid quantity: %d" % quantity)
            raise INVALID_CURRENCY_QUANTITY

        log.msg("Manual deposit of %d to %s" % (quantity, address))
        self.accountant.deposit_cash(address_db.username, address, quantity, total=False, admin_username=admin_username)

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

    @util.timed
    def get_permission_groups(self):
        """Get all the permission groups

        :returns: list -- models.PermissionGroup
        """
        permission_groups = self.session.query(models.PermissionGroup).all()
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
        contracts = self.session.query(models.Contract).filter_by(active=True).all()
        return contracts

    def get_contract(self, ticker):
        contract = util.get_contract(self.session, ticker)
        return contract

    def edit_contract(self, ticker, args):
        contract = self.get_contract(ticker)
        for key, value in args.iteritems():
            setattr(contract, key, value)

        self.session.commit()

    @util.timed
    def get_withdrawals(self):
        withdrawals = self.session.query(models.Withdrawal).all()
        return withdrawals

    @util.timed
    def get_deposits(self):
        addresses = self.session.query(models.Addresses).filter(models.Addresses.username != None).all()
        return addresses

    @util.timed
    def get_orders(self, user, page=0):
        all_orders = self.session.query(models.Order).filter_by(user=user)
        order_count = all_orders.count()
        order_pages = int(order_count / self.page_size) + 1
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
        self.accountant.change_permission_group(username, id)

    def change_fee_group(self, username, id):
        """Change the permission group for a user

        :param username: The user we are changing
        :type username: str
        :param id: the id of the new permission group
        :type id: int
        """
        log.msg("Changing fee group for %s to %d" % (username, id))
        self.accountant.change_fee_group(username, id)

    def modify_fee_group(self, id, name, aggressive_factor, passive_factor):
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
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            raise e

        self.accountant.reload_fee_group(None, group.id)

    def new_fee_group(self, name, aggressive_factor, passive_factor):
        try:
            log.msg("Creating new fee group: %s" % name)
            fee_group = models.FeeGroup(name, aggressive_factor, passive_factor)
            self.session.add(fee_group)
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            log.err("Error: %s" % e)

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

    def process_withdrawal(self, id, online=False, cancel=False, admin_username=None):
        self.cashier.process_withdrawal(id, online=online, cancel=cancel, admin_username=admin_username)


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
            raise Exception("Insufficient privileges to run Admin API")

        resources = {'/api/withdrawals': self.withdrawals,
                     '/api/deposits': self.deposits,
                     '/api/process_withdrawal': self.process_withdrawal,
                     '/api/manual_deposit': self.manual_deposit,
                     '/api/rescan_address': self.rescan_address,
        }
        if request.path in resources:
            return resources[request.path](request, data)
        else:
            raise Exception("Invalid request")


    def withdrawals(self, request, data):
        withdrawals = self.administrator.get_withdrawals()
        return [w.dict for w in withdrawals if w.pending]

    def deposits(self, request, data):
        deposits = self.administrator.get_deposits()
        return [d.dict for d in deposits]

    def rescan_address(self, request, data):
        self.administrator.cashier.rescan_address(data['address'])
        return {'result': True}

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

        self.administrator.process_withdrawal(int(data['id']), online=online, cancel=cancel,
                                              admin_username=self.avatarId)
        return {'result': True}

    def manual_deposit(self, request, data):
        self.administrator.manual_deposit(data['address'], float(data['quantity']), self.avatarId)
        return {'result': True}

    def render(self, request):
        data = request.content.read()
        self.log(request, data)
        request.setHeader('content-type', 'application/json')
        try:
            if request.method == "GET":
                result = self.process_request(request)
            else:
                parsed_data = json.loads(data)
                result = self.process_request(request, data=parsed_data)
        except Exception as e:
            result = {"error": str(e)}

        return json.dumps(result, sort_keys=True,
                          indent=4, separators=(',', ': '))


class AdminWebUI(Resource):
    isLeaf = False

    def __init__(self, administrator, avatarId, avatarLevel, digest_factory):
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
        self.jinja_env = Environment(loader=FileSystemLoader(self.administrator.template_dir),
                                     autoescape=True)
        self.digest_factory = digest_factory
        Resource.__init__(self)


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
                      '/contracts': self.contracts
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
                      '/cancel_order': self.cancel_order},
                    # Level 5
                     {'/admin_list': self.admin_list,
                      '/new_admin_user': self.new_admin_user,
                      '/set_admin_level': self.set_admin_level,
                      '/force_reset_admin_password': self.force_reset_admin_password,
                      '/transfer_position': self.transfer_position,
                      '/adjust_position': self.adjust_position,
                      '/clear_contract': self.clear_contract}]
        
        resource_list = {}
        for level in range(0, self.avatarLevel + 1):
            resource_list.update(resources[level])
        try:
            resource = resource_list[request.path]
            return resource(request)
        except KeyError:
            return self.invalid_request(request)

    def invalid_request(self, request):
        t = self.jinja_env.get_template("invalid_request.html")
        return t.render().encode('utf-8')

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

        self.administrator.process_withdrawal(int(request.args['id'][0]), online=online, cancel=cancel,
                                              admin_username=self.avatarId)
        return redirectTo("/user_details?username=%s" % request.args['username'][0], request)

    def permission_groups(self, request):
        """Get the permission groups page

        """
        self.administrator.expire_all()
        permission_groups = self.administrator.get_permission_groups()
        t = self.jinja_env.get_template('permission_groups.html')
        return t.render(permission_groups=permission_groups).encode('utf-8')

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
        self.administrator.change_permission_group(username, id)
        return redirectTo("/user_details?username=%s" % request.args['username'][0], request)

    def fee_groups(self, request):
        fee_groups = self.administrator.get_fee_groups()
        fee_group_problems = self.administrator.check_fee_groups(fee_groups)
        t = self.jinja_env.get_template('fee_groups.html')
        return t.render(fee_groups=fee_groups, fee_group_problems=fee_group_problems).encode('utf-8')

    def change_fee_group(self, request):
        username = request.args['username'][0]
        id = int(request.args['id'][0])
        self.administrator.change_fee_group(username, id)
        return redirectTo("/user_details?username=%s" % request.args['username'][0], request)

    def modify_fee_group(self, request):
        id = int(request.args['id'][0])
        name = request.args['name'][0]
        aggressive_factor = int(request.args['aggressive_factor'][0])
        passive_factor = int(request.args['passive_factor'][0])
        self.administrator.modify_fee_group(id, name, aggressive_factor, passive_factor)
        return redirectTo('/fee_groups', request)

    def new_fee_group(self, request):
        name = request.args['name'][0]
        aggressive_factor = int(request.args['aggressive_factor'][0])
        passive_factor = int(request.args['passive_factor'][0])
        self.administrator.new_fee_group(name, aggressive_factor, passive_factor)
        return redirectTo('/fee_groups', request)

    def contracts(self, request):
        contracts = self.administrator.get_contracts()
        t = self.jinja_env.get_template('contracts.html')
        return t.render(contracts=contracts).encode('utf-8')

    def edit_contract(self, request):
        ticker = request.args['ticker'][0]
        args = {}
        for key in ["description", "full_description", "cold_wallet_address", "deposit_instructions"]:
            if key in request.args:
                args[key] = request.args[key][0].decode('utf-8')

        for key in ["fees", "hot_wallet_limit"]:
            if key in request.args:
                args[key] = int(request.args[key][0])

        if "expiration" in request.args:
            args['expiration'] = parser.parse(request.args['expiration'][0])

        self.administrator.edit_contract(ticker, args)
        return redirectTo('/contracts', request)

    def clear_contract(self, request):
        self.administrator.clear_contract(request.args['ticker'][0], float(request.args['price'][0]))
        return redirectTo("/contracts", request)

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

        d.addCallback(got_order_book)
        return NOT_DONE_YET

    def cancel_order(self, request):
        id = int(request.args['id'][0])
        username = request.args['username'][0]
        self.administrator.cancel_order(username, id)

        return redirectTo("/order_book?ticker=%s" % request.args['ticker'][0], request)

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
        zendesk_domain = self.administrator.zendesk_domain

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
                            debug=self.administrator.debug, permission_groups=permission_groups,
                            orders=orders, order_pages=order_pages, orders_page=orders_page,
                            min_range=max(orders_page - 10, 0), max_range=min(order_pages, orders_page + 10))
        return rendered.encode('utf-8')

    def adjust_position(self, request):
        """Adjust a user's position then go back to his detail page

        """
        self.administrator.adjust_position(request.args['username'][0], request.args['contract'][0],
                                           float(request.args['quantity'][0]), self.avatarId)
        return redirectTo("/user_details?username=%s" % request.args['username'][0], request)

    def transfer_position(self, request):
        """Transfer a position from a user and go back to his details page

        """

        self.administrator.transfer_position(request.args['contract'][0], request.args['from_user'][0],
                                             request.args['to_user'][0], float(request.args['quantity'][0]),
                                             "%s (%s)" % (request.args['note'][0], self.avatarId))
        return redirectTo("/user_details?username=%s" % request.args['username'][0], request)

    def rescan_address(self, request):
        """Send a message to the cashier to rescan an address

        """
        self.administrator.cashier.rescan_address(request.args['address'][0])
        return redirectTo("/user_details?username=%s" % request.args['username'][0], request)

    def manual_deposit(self, request):
        """Tell the cashier that an address received a certain amount of money

        """
        self.administrator.manual_deposit(request.args['address'][0], float(request.args['quantity'][0]), self.avatarId)
        return redirectTo("/user_details?username=%s" % request.args['username'][0], request)

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

    def __init__(self, administrator, session, digest_factory):
        self.administrator = administrator
        self.session = session
        self.digest_factory = digest_factory

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
                print "Exception: %s" % e

            ui_resource = AdminWebUI(self.administrator, avatarId, avatarLevel, self.digest_factory)
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
    @schema("rpc/administrator.json#make_account")
    def make_account(self, username, password):
        return self.administrator.make_account(username, password)

    @export
    @schema("rpc/administrator.json#change_profile")
    def change_profile(self, username, profile):
        return self.administrator.change_profile(username, profile)

    @export
    @schema("rpc/administrator.json#reset_password_hash")
    def reset_password_hash(self, username, old_password_hash, new_password_hash, token=None):
        return self.administrator.reset_password_hash(username, old_password_hash, new_password_hash, token=token)

    @export
    @schema("rpc/administrator.json#get_reset_token")
    def get_reset_token(self, username):
        return self.administrator.get_reset_token(username)

    @export
    @schema("rpc/administrator.json#register_support_ticket")
    def register_support_ticket(self, username, nonce, type, foreign_key):
        return self.administrator.register_support_ticket(username, nonce, type, foreign_key)

    @export
    @schema("rpc/administrator.json#request_support_nonce")
    def request_support_nonce(self, username, type):
        return self.administrator.request_support_nonce(username, type)

    @export
    @schema("rpc/administrator.json#get_audit")
    def get_audit(self):
        return self.administrator.get_audit()


class TicketServerExport(ComponentExport):
    """The administrator exposes these functions to the TicketServer

    """

    def __init__(self, administrator):
        self.administrator = administrator
        ComponentExport.__init__(self, administrator)

    @export
    @schema("rpc/administrator.json#check_support_nonce")
    def check_support_nonce(self, username, nonce, type):
        return self.administrator.check_support_nonce(username, nonce, type)

    @export
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

    cashier = push_proxy_async(config.get("cashier", "administrator_export"))
    watchdog(config.get("watchdog", "administrator"))

    if config.getboolean("webserver", "ssl"):
        protocol = 'https'
    else:
        protocol = 'http'

    base_uri = "%s://%s:%d" % (protocol,
                               config.get("webserver", "www_address"),
                               config.getint("webserver", "www_port"))
    from_email = config.get("administrator", "email")
    zendesk_domain = config.get("ticketserver", "zendesk_domain")

    user_limit = config.getint("administrator", "user_limit")
    bs_cache_update = config.getint("administrator", "bs_cache_update")
    engine_base_port = config.getint("engine", "administrator_base_port")
    engines = {}
    for contract in session.query(models.Contract).filter_by(active=True).all():
        engines[contract.ticker] = dealer_proxy_async("tcp://127.0.0.1:%d" %
                                                      (engine_base_port + int(contract.id)))

    administrator = Administrator(session, accountant, cashier, engines,
                                  zendesk_domain,
                                  debug=debug, base_uri=base_uri,
                                  sendmail=Sendmail(from_email),
                                  user_limit=user_limit,
                                  bs_cache_update_period=bs_cache_update)

    webserver_export = WebserverExport(administrator)
    ticketserver_export = TicketServerExport(administrator)

    router_share_async(webserver_export,
                       config.get("administrator", "webserver_export"))
    router_share_async(ticketserver_export,
                       config.get("administrator", "ticketserver_export"))

    checkers = [PasswordChecker(session)]
    digest_factory = DigestCredentialFactory('md5', 'Sputnik Admin Interface')
    wrapper = HTTPAuthSessionWrapper(Portal(SimpleRealm(administrator, session, digest_factory),
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

    reactor.run()

