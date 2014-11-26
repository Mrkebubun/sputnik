from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("db_mem")

from sputnik.webserver.plugins import DatabasePlugin
from autobahn.wamp import types

class InMemoryDatabase(DatabasePlugin):
    def __init__(self):
        DatabasePlugin.__init__(self, "memdb")
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
            debug("User %s found.")
        else:
            debug("User %s not found.")
        return user

