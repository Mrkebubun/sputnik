#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("authn_wampcra")

from sputnik.webserver.plugin import AuthenticationPlugin
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import threads
from autobahn import util
from autobahn.wamp import types, auth

import hashlib
import json

class WAMPCRALogin(AuthenticationPlugin):
    def __init__(self):
        AuthenticationPlugin.__init__(self)

    @inlineCallbacks
    def onHello(self, router_session, realm, details):
        for authmethod in details.authmethods:
            if authmethod == u"wampcra":
                debug("Attemping wampcra login for %s..." % details.authid)
                # Create and store a one time challenge.
                challenge = {"authid": details.authid,
                             "authrole": u"user",
                             "authmethod": u"wampcra",
                             "authprovider": u"database",
                             "session": details.pending_session,
                             "nonce": util.newid(),
                             "timestamp": util.utcnow()}

                router_session.challenge = challenge

                # We can accept unicode usernames, but convert them before
                # anything hits the database
                username = challenge["authid"].encode("utf8")

                # If the user does not exist, we should still return a
                #   consistent salt. This prevents the auth system from
                #   becoming a username oracle.
                noise = hashlib.md5("super secret" + username + "more secret")
                salt, secret = noise.hexdigest()[:8], "!"

                # The client expects a unicode challenge string.
                challenge = json.dumps(challenge, ensure_ascii = False)
                
                try:
                    router_session.exists = False
                    result = None

                    databases = self.manager.services["sputnik.webserver.plugins.db"]
                    for db in databases:
                        result = yield db.lookup(username)
                        if result is not None:
                            break

                    if result is not None:
                        salt, secret = result['password'].split(":")
                        router_session.totp = result['totp_enabled']
                        router_session.exists = True
                    # We compute the signature even if there is no such user to
                    #   prevent timing attacks.
                    router_session.signature = (yield threads.deferToThread( \
                            auth.compute_wcs, secret,
                            challenge.encode("utf8"))).decode("ascii")

                except Exception, e:
                    error("Caught exception looking up user.")
                    error()

                # Client expects a unicode salt string.
                salt = salt.decode("ascii")
                extra = {u"challenge": challenge,
                         u"salt": salt,
                         u"iterations": 1000,
                         u"keylen": 32}

                debug("WAMP-CRA challenge issued for %s." % details.authid)
                returnValue(types.Challenge(u"wampcra", extra))

    def onAuthenticate(self, router_session, signature, extra):
        try:
            challenge = router_session.challenge
            if challenge == None:
                return
            if router_session.challenge.get("authmethod") != u"wampcra":
                return
            for field in ["authid", "authrole", "authmethod", "authprovider"]:
                if field not in challenge:
                    # Challenge not in expected format. It was probably
                    #   created by another plugin.
                    return

            if not router_session.challenge or not router_session.signature:
                log("Failed wampcra login for %s." % challenge["authid"])
                return types.Deny(message=u"No pending authentication.")

            if len(signature) != len(router_session.signature):
                log("Failed wampcra login for %s." % challenge["authid"])
                return types.Deny(message=u"Invalid signature.")

            success = True

            # Check each character to prevent HMAC timing attacks. This is
            #   really not an issue since each challenge gets a new nonce,
            #   but better safe than sorry.
            for i in range(len(router_session.signature)):
                if signature[i] != router_session.signature[i]:
                    success = False

            # Reject the user if we did not actually find them in the database.
            if not router_session.exists:
                log("User %s not found." % challenge["authid"])
                success = False

            if success:
                log("Successful wampcra login for %s." % challenge["authid"])
                return types.Accept(authid = challenge["authid"],
                        authrole = challenge["authrole"],
                        authmethod = challenge["authmethod"],
                        authprovider = challenge["authprovider"])

            log("Failed wampcra login for %s." % challenge["authid"])
            return types.Deny(message=u"Invalid signature.")

        except:
            # let another plugin handle this
            return

