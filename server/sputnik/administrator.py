#!/usr/bin/python

"""
The administrator modifies database objects. It is allowed to access User
    objects. For other objects it delegates to appropriate services. This
    ensures there are no race conditions.

The interface is exposed with ZMQ RPC running under Twisted. Many of the RPC
    calls block, but performance is not crucial here.

"""

import config
import database
import models
import collections
from datetime import datetime
from webserver import ChainedOpenSSLContextFactory

from zmq_util import export, router_share_async, dealer_proxy_async, push_proxy_async

from twisted.web.resource import Resource, IResource
from twisted.web.server import Site
from twisted.web.guard import HTTPAuthSessionWrapper, DigestCredentialFactory

from zope.interface import implements

from twisted.internet import reactor
from twisted.cred.portal import IRealm, Portal
from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse
from jinja2 import Environment, FileSystemLoader
import json
import smtplib

import logging
import autobahn, string, Crypto.Random.random
import sqlalchemy.orm.exc
from email.mime.text import MIMEText

from autobahn.wamp1.protocol import WampCraProtocol

class AdministratorException(Exception): pass

USERNAME_TAKEN = AdministratorException(1, "Username is already taken.")
NO_SUCH_USER = AdministratorException(2, "No such user.")
FAILED_PASSWORD_CHANGE = AdministratorException(3, "Password does not match")
INVALID_TOKEN = AdministratorException(4, "No such token found.")
EXPIRED_TOKEN = AdministratorException(5, "Token expired or already used.")
OUT_OF_ADDRESSES = AdministratorException(999, "Ran out of addresses.")
USER_LIMIT_REACHED = AdministratorException(6, "User limit reached")



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

    def __init__(self, session, accountant, cashier, debug=False):
        self.session = session
        self.accountant = accountant
        self.cashier = cashier
        self.debug = debug
        self.jinja_env = Environment(loader=FileSystemLoader('admin_templates'))
        self.from_email = config.get("administrator", "email")
        if config.getboolean("webserver", "ssl"):
            protocol = 'https'
        else:
            protocol = 'http'

        self.base_uri = "%s://%s:%d" % (protocol,
                                        config.get("webserver", "ws_address"),
                                        config.getint("webserver", "ws_port"))

    @session_aware
    def make_account(self, username, password):
        user_count = self.session.query(models.User).count()
        # TODO: Make this configurable
        if user_count > 100:
            logging.error("User limit reached")
            raise USER_LIMIT_REACHED

        existing = self.session.query(models.User).filter_by(
            username=username).first()
        if existing:
            logging.error("Account creation failed: %s username is taken" % username)
            raise USERNAME_TAKEN

        user = models.User(username, password)
        self.session.add(user)

        contracts = self.session.query(models.Contract).filter_by(
            contract_type='cash').all()
        for contract in contracts:
            position = models.Position(user, contract)
            self.session.add(position)

        address = self.session.query(models.Addresses).filter_by(
            active=False, user=None).first()
        if not address:
            # TODO: create a new address for the user
            logging.error("Account creating failed for %s: insufficient addresses" % username)
            raise OUT_OF_ADDRESSES
        address.user = user
        address.active = True

        self.session.commit()
        logging.info("Account created for %s" % username)
        return True

    @session_aware
    def change_profile(self, username, profile):
        user = self.session.query(models.User).filter_by(
            username=username).one()
        if not user:
            raise NO_SUCH_USER

        user.email = profile.get("email", user.email)
        user.nickname = profile.get("nickname", user.nickname)
        self.session.merge(user)

        self.session.commit()
        logging.info("Profile changed for %s to %s/%s" % (user.username, user.email, user.nickname))
        return True

    def check_token(self, username, input_token):
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
        user = self.session.query(models.User).filter_by(username=username).one()
        if not user:
            raise NO_SUCH_USER

        alphabet = string.digits + string.lowercase
        num = Crypto.Random.random.getrandbits(64)
        salt = ""
        while num != 0:
            num, i = divmod(num, len(alphabet))
            salt = alphabet[i] + salt
        extra = {"salt":salt, "keylen":32, "iterations":1000}
        password = WampCraProtocol.deriveKey(new_password, extra)
        user.password = "%s:%s" % (salt, password)
        self.session.add(user)
        self.session.commit()
        return True

    @session_aware
    def reset_password_hash(self, username, old_password_hash, new_password_hash, token=None):
        try:
            user = self.session.query(models.User).filter_by(username=username).one()
        except sqlalchemy.orm.exc.NoResultFound:
            raise NO_SUCH_USER

        [salt, hash] = user.password.split(':')

        if hash != old_password_hash and token is None:
            raise FAILED_PASSWORD_CHANGE
        else:
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
        try:
            user = self.session.query(models.User).filter(models.User.username == username).one()
        except sqlalchemy.orm.exc.NoResultFound:
            raise NO_SUCH_USER

        token = models.ResetToken(username, hours_to_expiry)
        self.session.add(token)
        self.session.commit()

        logging.debug("Created token: %s" % token)
        # Now email the token
        t = self.jinja_env.get_template('reset_password.email')
        content = t.render(token=token.token, expiration=token.expiration.strftime("%Y-%m-%d %H:%M:%S %Z"),
                           username=username, base_uri=self.base_uri).encode('utf-8')

        # Now email the token
        msg = MIMEText(content)
        msg['Subject'] = 'Reset password link enclosed'
        msg['From'] = self.from_email
        msg['To'] = '<%s> %s' % (user.email, user.nickname)
        logging.debug("Sending mail: %s" % msg.as_string())
        s = smtplib.SMTP('localhost')
        s.sendmail(self.from_email, [user.email], msg.as_string())
        s.quit()

        return True

    def expire_all(self):
        self.session.expire_all()

    def get_users(self):
        users = self.session.query(models.User).all()
        return users

    def get_user(self, username):
        user = self.session.query(models.User).filter(models.User.username == username).one()
        return user

    def get_positions(self):
        positions = self.session.query(models.Position).all()
        return positions

    def get_journal(self, journal_id):
        journal = self.session.query(models.Journal).filter_by(id=journal_id).one()
        return journal

    def adjust_position(self, username, ticker, quantity, description):
        logging.debug("Calling adjust position for %s: %s/%d - %s" % (username, ticker, quantity, description))
        self.accountant.adjust_position(username, ticker, quantity, description)

    def transfer_position(self, ticker, from_user, to_user, quantity, from_description='User', to_description='User'):
        logging.debug("Transferring %d of %s from %s/%s to %s/%s" % (
            quantity, ticker, from_user, from_description, to_user, to_description))
        self.accountant.transfer_position(ticker, from_user, to_user, quantity, from_description, to_description)


class AdminWebUI(Resource):
    isLeaf = True
    def __init__(self, administrator, avatarId):
        self.administrator = administrator
        self.avatarId = avatarId
        self.jinja_env = Environment(loader=FileSystemLoader('admin_templates'))
        Resource.__init__(self)

    def getChild(self, path, request):
        return self

    def log(self, request):
        line = '%s %s "%s %s %s" %d %s "%s" "%s" "%s" %s'
        logging.info(line, request.getClientIP(),
                     request.getUser(),
                     request.method,
                     request.uri,
                     request.clientproto,
                     request.code,
                     request.sentLength or "-",
                     request.getHeader("referer") or "-",
                     request.getHeader("user-agent") or "-",
                     request.getHeader("authorization") or "-",
                     json.dumps(request.args))

    def render(self, request):
        self.log(request)
        if request.path in ['/user_list', '/']:
            # Level 1
            return self.user_list().encode('utf-8')
        elif request.path == '/balance_sheet':
            return self.balance_sheet().encode('utf-8')
        elif request.path == '/adjust_position' and self.administrator.debug:
            # Level 5
            return self.adjust_position(request).encode('utf-8')
        elif request.path == '/user_details':
            # Level 1
            return self.user_details(request).encode('utf-8')
        elif request.path == '/ledger':
            # ?
            return self.ledger(request).encode('utf-8')
        elif request.path == '/rescan_address':
            return self.rescan_address(request).encode('utf-8')
        elif request.path == '/reset_password':
            # Level 2
            return self.reset_password(request).encode('utf-8')
        elif request.path == '/transfer_position':
            # Level 4
            return self.transfer_position(request).encode('utf-8')
        else:
            return "Request received: %s" % request.uri

    def ledger(self, request):
        journal_id = request.args['id'][0]
        journal = self.administrator.get_journal(journal_id)
        t = self.jinja_env.get_template('ledger.html')
        return t.render(journal=journal)

    def user_list(self):
        # We dont need to expire here because the user_list doesn't show
        # anything that is modified by anyone but the administrator
        users = self.administrator.get_users()
        t = self.jinja_env.get_template('user_list.html')
        return t.render(users=users)

    def reset_password(self, request):
        self.administrator.reset_password_plaintext(request.args['username'][0], request.args['new_password'][0])
        return self.user_details(request)

    def user_details(self, request):
        # We are getting trades and positions which things other than the administrator
        # are modifying, so we need to do an expire here
        self.administrator.expire_all()

        user = self.administrator.get_user(request.args['username'][0])
        t = self.jinja_env.get_template('user_details.html')
        rendered = t.render(user=user, debug=self.administrator.debug)
        return rendered

    def adjust_position(self, request):
        self.administrator.adjust_position(request.args['username'][0], request.args['contract'][0],
                                           int(request.args['quantity'][0]), request.args['description'][0])
        return self.user_details(request)

    def transfer_position(self, request):
        self.administrator.transfer_position(request.args['contract'][0], request.args['from_user'][0],
                                             request.args['to_user'][0], int(request.args['quantity'][0]),
                                             request.args['from_description'][0], request.args['to_description'][0])
        return self.user_details(request)

    def rescan_address(self, request):
        self.administrator.cashier.rescan_address(request.args['address'][0])
        return self.user_details(request)

    def balance_sheet(self):
        # We are getting trades and positions which things other than the administrator
        # are modifying, so we need to do an expire here
        self.administrator.expire_all()
        # TODO: Do this in SQLalchemy
        positions = self.administrator.get_positions()
        asset_totals = collections.defaultdict(int)
        liability_totals = collections.defaultdict(int)
        assets_by_ticker = collections.defaultdict(list)
        liabilities_by_ticker = collections.defaultdict(list)

        for position in positions:
            if position.position is not None:
                if position.position_type == 'Asset':
                    asset_totals[position.contract.ticker] += position.position
                    assets_by_ticker[position.contract.ticker].append(position)
                else:
                    liability_totals[position.contract.ticker] += position.position
                    liabilities_by_ticker[position.contract.ticker].append(position)

        t = self.jinja_env.get_template('balance_sheet.html')
        rendered = t.render(assets_by_ticker=assets_by_ticker, asset_totals=asset_totals,
                            liabilities_by_ticker=liabilities_by_ticker, liability_totals=liability_totals)
        return rendered

class SimpleRealm(object):
    implements(IRealm)

    def __init__(self, administrator):
        self.administrator = administrator

    def requestAvatar(self, avatarId, mind, *interfaces):
        if IResource in interfaces:
            return IResource, AdminWebUI(self.administrator, avatarId), lambda: None
        raise NotImplementedError

class WebserverExport:
    """
    For security reasons, the webserver only has access to a limit subset of
        the administrator functionality. This is exposed here.
    """

    def __init__(self, administrator):
        self.administrator = administrator

    @export
    def make_account(self, username, password):
        return self.administrator.make_account(username, password)

    @export
    def change_profile(self, username, profile):
        return self.administrator.change_profile(username, profile)

    @export
    def reset_password_hash(self, username, old_password_hash, new_password_hash, token=None):
        return self.administrator.reset_password_hash(username, old_password_hash, new_password_hash, token=token)

    @export
    def get_reset_token(self, username):
        return self.administrator.get_reset_token(username)

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    session = database.make_session()

    debug = config.getboolean("administrator", "debug")
    accountant = dealer_proxy_async(config.get("accountant", "administrator_export"))
    cashier = push_proxy_async(config.get("cashier", "administrator_export"))

    administrator = Administrator(session, accountant, cashier, debug)
    webserver_export = WebserverExport(administrator)

    router_share_async(webserver_export,
        config.get("administrator", "webserver_export"))

    checkers = [InMemoryUsernamePasswordDatabaseDontUse(admin='lFRAwzNkNeo')]
    wrapper = HTTPAuthSessionWrapper(Portal(SimpleRealm(administrator), checkers),
            [DigestCredentialFactory('md5', 'Sputnik Admin Interface')])

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

