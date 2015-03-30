#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("permissions")

from sputnik.webserver.plugin import AuthorizationPlugin
from autobahn.wamp import types
from autobahn.wamp.interfaces import IRouter

class BasicPermissions(AuthorizationPlugin):
    def __init__(self):
        AuthorizationPlugin.__init__(self)

    def authorize(self, router, session, uri, action):
        log("Authorizing %s(%s) to %s %s" % \
                (session._authid, session._authrole, \
                 IRouter.ACTION_TO_STRING[action], uri))
        
        return True

