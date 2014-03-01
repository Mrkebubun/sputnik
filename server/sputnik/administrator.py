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

from urlparse import parse_qs, urlparse

from twisted.web.resource import Resource
from twisted.web.server import Site
from twisted.internet import reactor

from jinja2 import Template


class AdministratorException(Exception): pass

USERNAME_TAKEN = AdministratorException(1, "Username is already taken.")
NO_SUCH_USER = AdministratorException(2, "No such user.")
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
            raise OUT_OF_ADDRESSES
        address.user = user
        address.active = True

        self.session.commit()
        return True

    @session_aware
    def change_profile(self, username, profile):
        user = self.session.query(models.User).filter_by(
            username=username).first()
        if not user:
            raise NO_SUCH_USER

        user.email = profile.get("email", user.email)
        user.nickname = profile.get("nickname", user.nickname)
        self.session.merge(user)

        self.session.commit()
        return True

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
        return self.accountant.adjust_position(username, ticker, adjustment)

class AdminWebUI(Resource):
    isLeaf = True
    def __init__(self, administrator):
        self.administrator = administrator
        Resource.__init__(self)

    def render_GET(self, request):
        if request.path == '/':
            return self.user_list().encode('utf-8')
        elif request.path == '/audit':
            return self.audit().encode('utf-8')
        elif request.path == '/position_edit' and self.administrator.debug:
            return self.position_edit(request).encode('utf-8')
        elif request.path == '/user_details':
            return self.user_details(request).encode('utf-8')
        else:
            return "Request received: %s" % request.uri

    def user_list(self):
        users = self.administrator.get_users()
        t = Template(open('admin_templates/user_list.html', 'r').read())
        return t.render(users=users)

    def user_details(self, request):
        params = parse_qs(urlparse(request.uri).query)

        user = self.administrator.get_user(params['username'][0])
        t = Template(open('admin_templates/user_details.html', 'r').read())
        rendered = t.render(user=user)
        return rendered

    def audit(self):
        # TODO: Do this in SQLalchemy
        positions = self.administrator.get_positions()
        position_totals = collections.defaultdict(int)
        for position in positions:
            position_totals[position.contract.ticker] += position.position

        t = Template(open('admin_templates/audit.html', 'r').read())
        rendered = t.render(position_totals=position_totals)
        return rendered

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

if __name__ == "__main__":
    session = database.make_session()

    debug = config.getboolean("administrator", "debug")
    accountant = dealer_proxy_async(config.get("accountant", "administrator_export"))

    administrator = Administrator(session, accountant, debug)
    webserver_export = WebserverExport(administrator)

    router_share_async(webserver_export,
        config.get("administrator", "webserver_export"))

    admin_ui = AdminWebUI(administrator)

    reactor.listenTCP(config.getint("administrator", "UI_port"), Site(admin_ui),
                      interface=config.get("administrator", "interface"))
    reactor.run()

