from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("rpc_info")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin, schema

from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from autobahn import wamp


class InfoService(ServicePlugin):
    def __init__(self):
        ServicePlugin.__init__(self)

    def init(self):
        self.exchange_info = dict(config.items("exchange_info"))
        self.administrator = self.require("sputnik.webserver.plugins.backend.administrator.AdministratorProxy")

    @wamp.register(u"rpc.info.get_exchange_info")
    @schema("public/info.json#get_exchange_info")
    def get_exchange_info(self):
        result = yield succeed(self.exchange_info)
        returnValue([True, result])

    @wamp.register(u'rpc.info.get_audit')
    @schema("public/info.json#get_audit")
    def get_audit(self):
        try:
            result = yield self.administrator.proxy.get_audit()
            returnValue([True, result])
        except Exception as e:
            error("Unable to get audit")
            error(e)
            returnValue([False, e.args])
