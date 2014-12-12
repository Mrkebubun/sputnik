from sputnik import config
from sputnik import observatory
from sputnik import util

debug, log, warn, error, critical = observatory.get_loggers("feeds_user")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin
from datetime import datetime

from twisted.internet.defer import inlineCallbacks, returnValue, gatherResults
from autobahn import wamp


class UserAnnouncer(ServicePlugin):
    def encode_username(self, username):
        return hashlib.sha256(username)

    def on_fill(self, username, fill):
        username = self.encode_username(username)
        self.publish(u"feeds.fills.%s" % username, fill)

    def on_transaction(self, username, transaction):
        username = self.encode_username(username)
        self.publish(u"feeds.transactions.%s" % username, transaction)

    def on_order(self, username, order):
        username = self.encode_username(username)
        self.publish(u"feeds.orders.%s" % username, order)

