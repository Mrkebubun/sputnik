#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("authn_anonymous")

from sputnik.webserver.plugin import AuthenticationPlugin
from autobahn.wamp import types

class AnonymousLogin(AuthenticationPlugin):
    def __init__(self):
        AuthenticationPlugin.__init__(self)

    def onHello(self, router_session, realm, details):
        for authmethod in details.authmethods:
            if authmethod == u"anonymous":
                log("Successful anonymous login (ID: %s)." % \
                        details.pending_session)
                return types.Accept(authid=u"anonymous",
                                    authrole=u"anonymous",
                                    authmethod=u"anonymous",
                                    authprovider=u"anonymous")

