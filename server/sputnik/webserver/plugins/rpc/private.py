from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("private")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin, schema, authenticated

from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from autobahn import wamp
from autobahn.wamp.types import RegisterOptions


class PrivateService(ServicePlugin):
    def __init__(self):
        ServicePlugin.__init__(self)

    @wamp.register(u"rpc.private.foobar")
    @authenticated
    @schema("public/private.json#foobar")
    def foobar(self, x, username=None):
        log(x)
        r = yield succeed(x)
        returnValue([True, r])

    @inlineCallbacks
    def register(self, endpoint, procedure = None, options = None):
        results = yield ServicePlugin.register(self, endpoint, procedure, options=RegisterOptions(details_arg="details", discloseCaller=True))
        returnValue(results)
