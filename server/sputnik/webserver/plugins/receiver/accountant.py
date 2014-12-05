from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("accountant")

from sputnik.webserver.plugin import BackendPlugin
from sputnik.zmq_util import export, pull_share_async, dealer_proxy_async

class AccountantReceiver(BackendPlugin):
    def __init__(self):
        BackendPlugin.__init__(self)
        self.listeners = []

    @export
    def fill(self, username, trade):
        log("Got fill for %s: %s" % (username, trade))
        for listener in self.listeners:
            try:
                listener.fill(username, trade)
            except Exception, e:
                error("Error handling fill() in %s." % listener)
                error(e)

    @export
    def transaction(self, username, transaction):
        for listener in self.listeners:
            log("Got transaction for %s: %s" % (username, transaction))
            try:
                listener.transaction(username, transaction)
            except Exception, e:
                error("Error handling transaction() in %s." % listener)
                error(e)

    @export
    def trade(self, ticker, trade):
        for listener in self.listeners:
            log("Got trade for %s: %s" % (ticker, trade))
            try:
                listener.trade(tricker, trade)
            except Exception, e:
                error("Error handling trade()) in %s." % listener)
                error(e)

    @export
    def order(self, username, order):
        for listener in self.listeners:
            log("Got order for %s: %s" % (username, order))
            try:
                listener.order(username, order)
            except Exception, e:
                error("Error handling order() in %s." % listener)
                error(e)

    def init(self):
        self.share = pull_share_async(self,
                config.get("webserver", "accountant_export"))

    def shutdown(self):
        # TODO: add shutdown code
        pass

