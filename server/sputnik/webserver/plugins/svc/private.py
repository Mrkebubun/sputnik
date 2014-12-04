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

    def foobar(self, details):
        log(details)

    @inlineCallbacks
    def onJoin(self, details):
        result = yield self.register(self.foobar, u"service.private.foobar", RegisterOptions(details_arg="details", discloseCaller=True))


