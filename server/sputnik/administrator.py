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
from webserver import ChainedOpenSSLContextFactory

from zmq_util import export, router_share_async, dealer_proxy_async, push_proxy_async

from twisted.web.resource import Resource, IResource
from twisted.web.server import Site
from twisted.web.guard import HTTPAuthSessionWrapper, DigestCredentialFactory

from zope.interface import implements

from twisted.internet import reactor, defer
from twisted.cred.portal import IRealm, Portal
from twisted.cred.checkers import AllowAnonymousAccess, ICredentialsChecker
from twisted.cred.credentials import IUsernameDigestHash
from twisted.cred import error as credError
from twisted.cred._digest import calcHA1
from jinja2 import Environment, FileSystemLoader
import json

import logging
import string, Crypto.Random.random
from sqlalchemy.orm.exc import NoResultFound

from autobahn.wamp1.protocol import WampCraProtocol
import hashlib

class AdministratorException(Exception): pass

USERNAME_TAKEN = AdministratorException(1, "Username is already taken.")
NO_SUCH_USER = AdministratorException(2, "No such user.")
FAILED_PASSWORD_CHANGE = AdministratorException(3, "Password does not match")
OUT_OF_ADDRESSES = AdministratorException(999, "Ran out of addresses.")
USER_LIMIT_REACHED = AdministratorException(5, "User limit reached")
ADMIN_USERNAME_TAKEN = AdministratorException(6, "Administrator username is already taken")



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
    def reset_password_hash(self, username, old_password_hash, new_password_hash):
        user = self.session.query(models.User).filter_by(username=username).one()
        if not user:
            raise NO_SUCH_USER

        [salt, hash] = user.password.split(':')

        if hash != old_password_hash:
            raise FAILED_PASSWORD_CHANGE

        user.password = "%s:%s" % (salt, new_password_hash)

        self.session.add(user)
        self.session.commit()
        return True

    def expire_all(self):
        self.session.expire_all()

    def get_users(self):
        users = self.session.query(models.User).all()
        return users

    def get_admin_users(self):
        admin_users = self.session.query(models.AdminUser).all()
        return admin_users

    def get_user(self, username):
        user = self.session.query(models.User).filter_by(username=username).one()
        return user

    @session_aware
    def set_admin_level(self, username, level):
        user = self.session.query(models.AdminUser).filter_by(username=username).one()
        user.level = level
        self.session.add(user)
        self.session.commit()
        return True

    @session_aware
    def new_admin_user(self, username, password, level):
        if self.session.query(models.AdminUser).filter_by(username=username).count() > 0:
            raise ADMIN_USERNAME_TAKEN

        user = models.AdminUser(username, password, level)
        self.session.add(user)
        self.session.commit()
        return True

    @session_aware
    def reset_admin_password(self, username, old_password_hash, new_password_hash):
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
        return True

    @session_aware
    def force_reset_admin_password(self, username, new_password_hash):
        try:
            user = self.session.query(models.AdminUser).filter_by(username=username).one()
        except NoResultFound:
            raise NO_SUCH_USER

        user.password_hash = new_password_hash
        self.session.add(user)
        self.session.commit()
        return True

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
    def __init__(self, administrator, avatarId, avatarLevel, digest_factory):
        self.administrator = administrator
        self.avatarId = avatarId
        self.avatarLevel = avatarLevel
        self.jinja_env = Environment(loader=FileSystemLoader('admin_templates'))
        self.digest_factory = digest_factory
        Resource.__init__(self)


    def calc_ha1(self, password, username=None):
        if username is None:
            username = self.avatarId

        realm = self.digest_factory.digest.authenticationRealm
        return calcHA1('md5', username, realm, password, None, None)

    def getChild(self, path, request):
        self.log(request)
        return self

    def log(self, request):
        line = '%s %s %s "%s %s %s" %d %s "%s" "%s" "%s" %s'
        logging.info(line,
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
                     request.getHeader("authorization") or "-",
                     json.dumps(request.args))

    def render(self, request):
        self.log(request)
        resources = [
                    # Level 0
                    { '/': self.admin,
                      '/reset_admin_password': self.reset_admin_password
                    },
                    # Level 1
                     {'/': self.user_list,
                      '/user_details': self.user_details,
                      '/rescan_address': self.rescan_address,
                      '/admin': self.admin,
                     },
                    # Level 2
                     {'/reset_password': self.reset_password},
                    # Level 3
                     {'/balance_sheet': self.balance_sheet,
                      '/ledger': self.ledger },
                    # Level 4
                     {'/transfer_position': self.transfer_position},
                    # Level 5
                     {'/admin_list': self.admin_list,
                      '/new_admin_user': self.new_admin_user,
                      '/set_admin_level': self.set_admin_level,
                      '/force_reset_admin_password': self.force_reset_admin_password,
                      '/adjust_position': self.adjust_position}]
        resource_list = {}
        for level in range(0, self.avatarLevel+1):
            resource_list.update(resources[level])
        try:
            resource = resource_list[request.path]
            return resource(request).encode('utf-8')
        except KeyError:
            return None

    def ledger(self, request):
        journal_id = request.args['id'][0]
        journal = self.administrator.get_journal(journal_id)
        t = self.jinja_env.get_template('ledger.html')
        return t.render(journal=journal)

    def user_list(self, request):
        # We dont need to expire here because the user_list doesn't show
        # anything that is modified by anyone but the administrator
        users = self.administrator.get_users()
        t = self.jinja_env.get_template('user_list.html')
        return t.render(users=users)

    def reset_password(self, request):
        self.administrator.reset_password_plaintext(request.args['username'][0], request.args['new_password'][0])
        return self.user_details(request)

    def reset_admin_password(self, request):
        self.administrator.reset_admin_password(self.avatarId, self.calc_ha1(request.args['old_password'][0]),
                                                self.calc_ha1(request.args['new_password'][0]))
        return self.admin(request)

    def force_reset_admin_password(self, request):
        self.administrator.reset_admin_password(request.args['username'][0], self.calc_ha1(request.args['password'][0],
                                                                                      username=request.args['username'][0]))

        return self.admin_list(request)

    def admin(self, request):
        t = self.jinja_env.get_template('admin.html')
        return t.render(username=self.avatarId)

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

    def admin_list(self, request):
        admin_users = self.administrator.get_admin_users()
        t = self.jinja_env.get_template('admin_list.html')
        return t.render(admin_users=admin_users)

    def new_admin_user(self, request):
        self.administrator.new_admin_user(request.args['username'][0], self.calc_ha1(request.args['password'][0],
                                                                                     username=request.args['username'][0]),
                                          int(request.args['level'][0]))
        return self.admin_list(request)

    def set_admin_level(self, request):
        self.administrator.set_admin_level(request.args['username'][0], int(request.args['level'][0]))
        return self.admin_list(request)

    def balance_sheet(self, request):
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

class PasswordChecker(object):
    implements(ICredentialsChecker)
    credentialInterfaces = (IUsernameDigestHash,)

    def __init__(self, session):
        self.session = session

    def requestAvatarId(self, credentials):
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

            return IResource, AdminWebUI(self.administrator, avatarId, avatarLevel, self.digest_factory), lambda: None
        else:
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
    def reset_password_hash(self, username, old_password_hash, new_password_hash):
        return self.administrator.reset_password_hash(username, old_password_hash, new_password_hash)

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

