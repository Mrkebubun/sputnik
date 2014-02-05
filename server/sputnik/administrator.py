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

from zmq_util import export, router_share_async

from twisted.internet import reactor
from twisted.internet.defer import maybeDeferred

from twisted.web.resource import Resource
from twisted.web.server import Site
from twisted.internet import reactor


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

    def __init__(self, session):
        self.session = session

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

class AdminWebUI(Resource):
    def render_GET(self):
        return "Here be admin interface!"

class WebserverLink:
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
    administrator = Administrator(session)
    webserver_link = WebserverLink(administrator)
    router_share_async(webserver_link,
                       config.get("administrator", "webserver_link"))

    admin_ui = AdminWebUI()
    reactor.listenTCP(config.get("administrator", "UI_port"), Site(admin_ui), interface=config.get("administrator", "interface"))
    reactor.run()

