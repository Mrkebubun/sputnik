from sputnik.webserver.plugin import AuthenticationPlugin
from autobahn.wamp import types, util

class WAMPCRALogin(AuthenticationPlugin):
    def __init__(self):
        AuthenticationPlugin.__init__(self, u"totp")

    @inlineCallbacks
    def onHello(self, router_session, realm, details):
        for authmethod in details.authmethods:
            # only run TOTP for wampcra
            if authmethod == u"wampcra":
                # We can accept unicode usernames, but convert them before
                # anything hits the database
                username = challenge["authid"].encode("utf8")

                try:
                    memdb = self.manager.plugins["memdb"]
                    result = yield memdb.lookup(username)
                    router_session.totp = result[2]
                except Exception, e
                    log.err(e)

    def onAuthenticate(self, router_session, signature, extra):
        try:
            challenge = router_session.challenge
            if challenge == None:
                return
            if router_session.challenge.get("authmethod") != u"wampcra":
                return
        except:
            # let another plugin handle this
            return

        pass

        # Check the TOTP
        if self.totp:
            codes = [auth.compute_totp(self.totp, i) for i in range(-1, 2)]
            if extra["totp"].encode("utf8") not in codes:
                success = False

