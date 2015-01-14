from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("rpc_registrar")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin, schema, error_handler
from sputnik.exception import WebserverException

from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import wamp

class RegistrarService(ServicePlugin):
    def __init__(self):
        ServicePlugin.__init__(self)

    def init(self):
        self.administrator = self.require("sputnik.webserver.plugins.backend.administrator.AdministratorProxy")
    
    @wamp.register(u"rpc.registrar.make_account")
    @error_handler
    @schema("public/registrar.json#make_account", drop_args=[])
    def make_account(self, username, password, email, nickname, locale=None):
        result = yield self.administrator.proxy.make_account(username, password)
        if result:
            profile = {"email": email, "nickname": nickname,
                       "locale": locale}
            yield self.administrator.proxy.change_profile(username, profile)
            returnValue(username)

    @wamp.register(u"rpc.registrar.get_reset_token")
    @error_handler
    @schema("public/registrar.json#get_reset_token", drop_args=[])
    def get_reset_token(self, username):
        result = yield self.administrator.proxy.get_reset_token(username)
        log("Generated password reset token for user %s." % username)
        returnValue(None)


    @wamp.register(u"rpc.registrar.change_password_token")
    @error_handler
    @schema("public/registrar.json#change_password_token", drop_args=[])
    def change_password_token(self, username, hash, token):
        result = yield self.administrator.proxy.reset_password_hash(username,
                None, hash, token=token)
        log("Reset password using token for user %s." % username)
        returnValue(None)


