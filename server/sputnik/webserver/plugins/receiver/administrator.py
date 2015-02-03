__author__ = 'sameer'

from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("administrator")

from sputnik.webserver.plugin import ReceiverPlugin
from sputnik.zmq_util import export, pull_share_async, dealer_proxy_async

class AdministratorReceiver(ReceiverPlugin):
    def __init__(self):
        ReceiverPlugin.__init__(self)

    @export
    def reload_contract(self, ticker):
        self.market.load_contract(ticker)

    def init(self):
        self.market = self.require("sputnik.webserver.plugins.rpc.market.MarketService")
        self.share = dealer_proxy_async(self,
                config.get("webserver", "administrator_export"))