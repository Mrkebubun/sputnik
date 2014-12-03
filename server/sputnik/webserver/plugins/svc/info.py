from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("svc_info")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin

from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import wamp


class InfoService(ServicePlugin):
    def __init__(self):
        ServicePlugin.__init__(self)

    def init(self):
        self.exchange_info = dict(config.items("exchange_info"))

    @wamp.register(u"service.info.get_exchange_info")
    def get_exchange_info(self):
        return [True, self.exchange_info]

