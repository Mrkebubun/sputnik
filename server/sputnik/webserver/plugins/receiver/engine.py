from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("engine")

from sputnik.webserver.plugin import ReceiverPlugin
from sputnik.zmq_util import export, pull_share_async, dealer_proxy_async

class EngineReceiver(ReceiverPlugin):
    def __init__(self):
        ReceiverPlugin.__init__(self)

    @export
    def book(self, ticker, book):
        log("Got 'book' for %s / %s" % (ticker, book))
        self.send_to_listeners("book", ticker, book)

    @export
    def safe_prices(self, ticker, price):
        log("Got safe price for %s: %s" % (ticker, price))
        self.send_to_listeners("safe_prices", ticker, price)

    def init(self):
        self.share = pull_share_async(self,
                config.get("webserver", "engine_export"))

    def shutdown(self):
        # TODO: add shutdown code
        pass

