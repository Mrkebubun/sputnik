from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("svc_registrar")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin

from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import wamp

class RegistrarService(ServicePlugin):
    def __init__(self):
        ServicePlugin.__init__(self)

    def init(self):
        req_path = "sputnik.webserver.plugins.backend.administrator.AdministratorProxy"
        self.administrator = self.manager.plugins.get(req_path)
        if not self.administrator:
            raise PluginException("Missing dependency %s." % req_path)
    
    @wamp.register(u"service.registrar.create_account")
    @inlineCallbacks
    def make_account(self, username, password, email, locale=None):
        try:
            result = yield self.administrator.make_account(username, password)
            if result:
                profile = {"email": email, "nickname": nickname,
                           "locale": locale}
                yield self.administrator.change_profile(username, profile)
                returnValue(True, username)
        except Exception, e:
            returnValue(False, e.args)

    @wamp.register(u"service.registrar.get_reset_token")
    @inlineCallbacks
    def get_reset_token(self, username):
        try:
            result = yield self.administrator.get_reset_token(username)
            log("Generated password reset token for user %s." % username)
            returnValue(True, None)
        except Exception, e:
            error("Failed to generate password reset token for user %s." % \
                    username)
            error(e)
            returnValue(False, e.args)

    @wamp.register(u"service.registrar.change_password_token")
    @inlineCallbacks
    def get_reset_token(self, username, hash, token):
        try:
            result = yield self.administrator.reset_password_hash(username,
                    None, hash, token=token)
            log("Reset password using token for user %s." % username)
            returnValue(True, None)
        except Exception, e:
            error("Failed to reset password using token for user %s." % \
                    username)
            error(e)
            returnValue(False, e.args)

    @inlineCallbacks
    def onJoin(self, details):
        results = yield self.register(self)
        for success, result in results:
            if success:
                log("Registered %s." % self._registrations[result.id].procedure)
            else:
                error("Error registering method: %s." % result.value.args[0])


