__author__ = 'sameer'

from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("administrator")

from sputnik.webserver.plugin import ReceiverPlugin
from sputnik.zmq_util import export, router_share_async

class AdministratorReceiver(ReceiverPlugin):
    def __init__(self):
        ReceiverPlugin.__init__(self)

    @export
    def reload_contract(self, ticker):
        self.market.load_contract(ticker)

    def init(self):
        self.market = self.require("sputnik.webserver.plugins.rpc.market.MarketService")
        self.share = router_share_async(self,
                config.get("webserver", "administrator_export"))