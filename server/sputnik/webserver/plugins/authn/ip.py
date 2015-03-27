#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("authn_ip")

from sputnik.webserver.plugin import AuthenticationPlugin
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import threads
from autobahn import util
from autobahn.wamp import types, auth

import hashlib
import json

class IPFilter(AuthenticationPlugin):
    def __init__(self):
        AuthenticationPlugin.__init__(self)

    def onHello(self, router_session, realm, details):
        ip = router_session._transport.peer
        headers = router_session._transport.http_headers
        if "x-forwarded-for" in headers:
            ip += " (but really: %s)" % str(headers["x-forwarded-for"])
        log("Received HELLO from %s from: %s." % (details.authid, ip))

