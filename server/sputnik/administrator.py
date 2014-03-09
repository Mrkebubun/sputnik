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

from zmq_util import export, router_share_async, dealer_proxy_async

from twisted.web.resource import Resource, IResource
from twisted.web.server import Site
from twisted.web.guard import HTTPAuthSessionWrapper, DigestCredentialFactory

from zope.interface import implements

from twisted.internet import reactor
from twisted.cred.portal import IRealm, Portal
from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse
from jinja2 import Environment, FileSystemLoader

import logging
import autobahn, string, Crypto.Random.random

class AdministratorException(Exception): pass

USERNAME_TAKEN = AdministratorException(1, "Username is already taken.")
NO_SUCH_USER = AdministratorException(2, "No such user.")
FAILED_PASSWORD_CHANGE = AdministratorException(3, "Password does not match")
OUT_OF_ADDRESSES = AdministratorException(999, "Ran out of addresses.")



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

    def __init__(self, session, accountant, debug=False):
        self.session = session
        self.accountant = accountant
        self.debug = debug

    @session_aware
    def make_account(self, username, password):
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
        password = autobahn.wamp.WampCraProtocol.deriveKey(new_password, extra)
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

    def get_user(self, username):
        user = self.session.query(models.User).filter(models.User.username == username).one()
        return user

    def get_positions(self):
        positions = self.session.query(models.Position).all()
        return positions

    def adjust_position(self, username, ticker, adjustment):
        logging.debug("Calling adjust position for %s: %s/%d" % (username, ticker, adjustment))
        self.accountant.adjust_position(username, ticker, adjustment)

class AdminWebUI(Resource):
    isLeaf = True
    def __init__(self, administrator, avatarId):
        self.administrator = administrator
        self.avatarId = avatarId
        self.jinja_env = Environment(loader=FileSystemLoader('admin_templates'))
        Resource.__init__(self)

    def getChild(self, path, request):
        return self

    def render(self, request):
        if request.path in ['/user_list', '/']:
            return self.user_list().encode('utf-8')
        elif request.path == '/audit':
            return self.audit().encode('utf-8')
        elif request.path == '/adjust_position' and self.administrator.debug:
            return self.adjust_position(request).encode('utf-8')
        elif request.path == '/user_details':
            return self.user_details(request).encode('utf-8')
        elif request.path == '/reset_password':
            return self.reset_password(request).encode('utf-8')
        else:
            return "Request received: %s" % request.uri

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
                                           int(request.args['adjustment'][0]))
        return self.user_details(request)

    def audit(self):
        # We are getting trades and positions which things other than the administrator
        # are modifying, so we need to do an expire here
        self.administrator.expire_all()
        # TODO: Do this in SQLalchemy
        positions = self.administrator.get_positions()
        position_totals = collections.defaultdict(int)
        for position in positions:
            if position.position is not None:
                position_totals[position.contract.ticker] += position.position

        t = self.jinja_env.get_template('audit.html')
        rendered = t.render(position_totals=position_totals)
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
    def reset_password_hash(self, username, old_password_hash, new_password_hash):
        return self.administrator.reset_password_hash(username, old_password_hash, new_password_hash)

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    session = database.make_session()

    debug = config.getboolean("administrator", "debug")
    accountant = dealer_proxy_async(config.get("accountant", "administrator_export"))

    administrator = Administrator(session, accountant, debug)
    webserver_export = WebserverExport(administrator)

    router_share_async(webserver_export,
        config.get("administrator", "webserver_export"))

    checkers = [InMemoryUsernamePasswordDatabaseDontUse(admin='admin')]
    wrapper = HTTPAuthSessionWrapper(Portal(SimpleRealm(administrator), checkers),
            [DigestCredentialFactory('md5', 'Sputnik Admin Interface')])

    reactor.listenTCP(config.getint("administrator", "UI_port"), Site(resource=wrapper),
                      interface=config.get("administrator", "interface"))
    reactor.run()

