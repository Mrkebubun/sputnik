from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("private")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin

from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import wamp
from autobahn.wamp.types import RegisterOptions


class PrivateService(ServicePlugin):
    def __init__(self):
        ServicePlugin.__init__(self)

    @wamp.register(u"foobar")
    def get_exchange_info(self, details):
        log(details)

    @inlineCallbacks
    def onJoin(self, details):
        yield self.register(self.foobar, u"foobar", RegisterOptions(details_arg = 'details'))


