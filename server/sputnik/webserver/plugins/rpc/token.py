from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("rpc_token")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin, authenticated

from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import wamp
from autobahn.wamp.types import RegisterOptions

class TokenService(ServicePlugin):
    def __init__(self):
        ServicePlugin.__init__(self)

    def init(self):
        self.administrator = self.require("sputnik.webserver.plugins.backend.administrator.AdministratorProxy")
        self.cookie_jar = self.require("sputnik.webserver.plugins.authn.cookie.CookieLogin")
    
    @wamp.register(u"rpc.registrar.get_cookie")
    @authenticated
    def get_cookie(self, username):
        cookie = self.cookie_jar.get_cookie(username)
        if cookie is None:
            return self.cookie_jar.new_cookie(username)
        return cookie

    @wamp.register(u"rpc.registrar.logout")
    @authenticated
    def logout(self, username):
        self.cookie_jar.delete_cookie(username)
        # TODO: disconnect here

    @inlineCallbacks
    def register(self, endpoint, procedure = None, options = None):
        results = yield ServicePlugin.register(self, endpoint, procedure, options=RegisterOptions(details_arg="details", discloseCaller=True))
        returnValue(results)

