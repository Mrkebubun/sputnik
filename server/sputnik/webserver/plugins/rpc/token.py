from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("rpc_token")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin, authenticated, schema, error_handler
from sputnik.exception import WebserverException

from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from autobahn import wamp
from autobahn.wamp.types import RegisterOptions
from datetime import datetime, timedelta
from sputnik import util


class TokenService(ServicePlugin):
    def __init__(self):
        ServicePlugin.__init__(self)

    def init(self):
        self.administrator = self.require("sputnik.webserver.plugins.backend.administrator.AdministratorProxy")
        self.cookie_jar = self.require("sputnik.webserver.plugins.authn.cookie.CookieLogin")
    
    @wamp.register(u"rpc.token.get_cookie")
    @error_handler
    @authenticated
    @schema(u"public/token.json#get_cookie")
    def get_cookie(self, username=None):
        cookie = self.cookie_jar.get_cookie(username)
        if cookie is None:
            cookie = self.cookie_jar.new_cookie(username)
        r = yield succeed(cookie)
        returnValue(r)

    @wamp.register(u"rpc.token.get_new_api_credentials")
    @error_handler
    @authenticated
    @schema(u"public/token.json#get_new_api_credentials")
    def get_new_api_credentials(self, expiration=None, username=None):
        if expiration is None:
            now = datetime.utcnow()
            expiration = util.dt_to_timestamp(now + timedelta(days=7))

        r = yield self.administrator.proxy.get_new_api_credentials(username, expiration)
        returnValue(r)

    @wamp.register(u"rpc.token.logout")
    @error_handler
    @authenticated
    @schema(u"public/token.json#logout")
    def logout(self, username):
        self.cookie_jar.delete_cookie(username)
        # TODO: disconnect here

        r = yield succeed(None)
        returnValue(r)

    @wamp.register(u"rpc.token.change_password")
    @error_handler
    @authenticated
    @schema(u"public/token.json#change_password")
    def change_password(self, old_password_hash, new_password_hash, username=None):
        """
        Changes a users password.  Leaves salt and two factor untouched.
        :param old_password_hash: current password
        :param new_password_hash: new password
        :returns: Deferred
        """


        result = yield self.administrator.proxy.reset_password_hash(username, old_password_hash, new_password_hash)
        returnValue(None)

    @wamp.register(u"rpc.token.enable_totp")
    @error_handler
    @authenticated
    @schema(u"public/token.json#enable_totp")
    def enable_otp(self, username=None):
        """Starts two step process to enable OTP for an account."""
        secret = yield self.administrator.proxy.enable_totp(username)
        returnValue(secret)

    @wamp.register(u"rpc.token.verify_totp")
    @error_handler
    @authenticated
    @schema(u"public/token.json#verify_totp")
    def verify_otp(self, otp, username=None):
        """Confirms that the user has saved the OTP secret."""
        result = yield self.administrator.proxy.verify_totp(username, otp)
        returnValue(result)

    @wamp.register(u"rpc.token.disable_totp")
    @error_handler
    @authenticated
    @schema(u"public/token.json#disable_totp")
    def disable_otp(self, otp, username=None):
        """Disables OTP for an account."""
        result = yield self.administrator.proxy.disable_totp(username, otp)
        returnValue(result)

    @inlineCallbacks
    def register(self, endpoint, procedure = None, options = None):
        results = yield ServicePlugin.register(self, endpoint, procedure, options=RegisterOptions(details_arg="details", discloseCaller=True))
        returnValue(results)

