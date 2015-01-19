from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("auth_cookie")

from sputnik.webserver.plugin import AuthenticationPlugin
from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import util
from autobahn.wamp import types, auth

class TOTPVerification(AuthenticationPlugin):
    def __init__(self):
        AuthenticationPlugin.__init__(self)

    @inlineCallbacks
    def onHello(self, router_session, realm, details):
        for authmethod in details.authmethods:
            # only run TOTP for wampcra
            if authmethod == u"wampcra":
                log("Checking for TOTP for username %s..." % details.authid)
                # We can accept unicode usernames, but convert them before
                # anything hits the database
                username = router_session.challenge["authid"].encode("utf8")

                try:
                    databases = self.manager.services["sputnik.webserver.plugins.db"]
                    for db in databases:
                        result = yield db.lookup(username)
                        if result is not None:
                            router_session.totp = result['totp']
                            break
                except Exception, e:
                    error("Caught exception looking up user.")
                    error()

    def onAuthenticate(self, router_session, signature, extra):
        if not hasattr(router_session, "totp"):
            return

        totp = router_session.totp
        if totp:
            if "totp" not in extra:
                return types.Deny(message=u"Missing TOTP.")
            codes = [auth.compute_totp(totp, i) for i in range(-1, 2)]
            if extra["totp"].encode("utf8") not in codes:
                return types.Deny(message=u"Invalid TOTP.")

