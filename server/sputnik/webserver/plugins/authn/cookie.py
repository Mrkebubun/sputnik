from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("authn_cookie")

from sputnik.webserver.plugin import AuthenticationPlugin
from autobahn import util
from autobahn.wamp import types
import json

class CookieLogin(AuthenticationPlugin):
    def __init__(self):
        AuthenticationPlugin.__init__(self)
        self.cookies = {}

    def new_cookie(self, username):
        self.cookies[username] = util.newid()
        return self.cookies[username]

    def set_cookie(self, username, cookie):
        self.cookies[username] = cookie

    def get_cookie(self, username):
        return self.cookies.get(username)

    def delete_cookie(self, username):
        if username in self.cookies:
            del self.cookies[username]

    def onHello(self, router_session, realm, details):
        for authmethod in details.authmethods:
            if authmethod == u"cookie":
                debug("Attemping cookie login for %s..." % details.authid)
                # Ideally, we would just check the cookie here, however
                #   the HELLO message does not have any extra fields to store
                #   it.

                # This is not a real challenge. It is used for bookkeeping,
                # however. We require to cookie owner to also know the
                # correct authid, so we store what they think it is here.

                # Create and store a one time challenge.
                challenge = {"authid": details.authid,
                             "authrole": u"user",
                             "authmethod": u"cookie",
                             "authprovider": u"cookie",
                             "session": details.pending_session,
                             "nonce": util.utcnow(),
                             "timestamp": util.newid()}
                router_session.challenge = challenge

                # The client expects a unicode challenge string.
                challenge = json.dumps(challenge, ensure_ascii=False)
                extra = {u"challenge": challenge}

                debug("Cookie challenge issued for %s." % details.authid)
                return types.Challenge(u"cookie", extra)

    def onAuthenticate(self, router_session, signature, extra):
        try:
            challenge = router_session.challenge
            authid = challenge["authid"]
            if challenge == None:
                return
            if router_session.challenge.get("authmethod") != u"cookie":
                return
            for field in ["authrole", "authmethod", "authprovider"]:
                if field not in challenge:
                    # Challenge not in expected format. It was probably
                    #   created by another plugin.
                    return
        except Exception as e:
            # let another plugin handle this
            return

        cookie = self.cookies.get(authid)
        if cookie != signature:
            log("Failed cookie login for %s." % challenge["authid"])
            return types.Deny(u"Invalid cookie.")

        log("Successful cookie login for %s." % challenge["authid"])
        return types.Accept(authid = challenge["authid"],
                            authrole = challenge["authrole"],
                            authmethod = challenge["authmethod"],
                            authprovider = challenge["authprovider"])

