#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("db_mem")

from sputnik.webserver.plugin import DatabasePlugin
from autobahn.wamp import types

class InMemoryDatabase(DatabasePlugin):
    def __init__(self):
        DatabasePlugin.__init__(self)
        self.users = {}

    def add_user(self, username, line):
        debug("Adding user %s..." % username)
        if username in self.users:
            warn("User %s already exists." % username)
        self.users[username] = line

    def remove_user(self, username):
        debug("Removing user %s..." % username)
        if username in self.users:
            del self.users[username]
        else:
            warn("User %s does not exist." % username)

    def lookup(self, username):
        debug("Looking up username %s..." % username)
        user = self.users.get(username)
        if user:
            debug("User %s found." % username)
            return {'password': user,
                    'totp': None,
                    'api_key': None,
                    'api_secret': None,
                    'api_expiration': None,
                    'username': username}
        else:
            debug("User %s not found." % username)
            return None


