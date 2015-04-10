#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("auth_totp")

from sputnik.webserver.plugin import AuthenticationPlugin
from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import util
from autobahn.wamp import types, auth

class TOTPVerification(AuthenticationPlugin):
    def __init__(self):
        AuthenticationPlugin.__init__(self)

    def init(self):
        self.administrator = self.require("sputnik.webserver.plugins.backend.administrator.AdministratorProxy")

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
                            router_session.totp = result['totp_enabled']
                            break
                except Exception, e:
                    error("Caught exception looking up user.")
                    error()

    @inlineCallbacks
    def onAuthenticate(self, router_session, signature, extra):
        if not hasattr(router_session, "totp"):
            return

        username = router_session.challenge["authid"].encode("utf8")
        totp = router_session.totp
        if totp:
            if "otp" not in extra:
                log("TOTP parameter is missing for %s." % username)
                returnValue(types.Deny(message=u"Missing TOTP."))
            success = yield self.administrator.proxy.check_totp(
                    username, extra["otp"].encode("utf-8"))
            if not success: 
                log("TOTP parameter is invalid for %s." % username)
                returnValue(types.Deny(message=u"Invalid TOTP."))
            log("Successfully verified TOTP for %s." % username)

