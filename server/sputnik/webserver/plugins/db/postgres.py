from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("db_postgres")

from sputnik.webserver.plugin import DatabasePlugin
from autobahn.wamp import types
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.enterprise import adbapi

class PostgresDatabase(DatabasePlugin):
    def __init__(self):
        DatabasePlugin.__init__(self)
        dbpassword = config.get("database", "password")
        if dbpassword:
            dbpool = adbapi.ConnectionPool(config.get("database", "adapter"),
                    user=config.get("database", "username"),
                    password=dbpassword,
                    host=config.get("database", "host"),
                    port=config.get("database", "port"),
                    database=config.get("database", "dbname"))
        else:
            dbpool = adbapi.ConnectionPool(config.get("database", "adapter"),
                    user=config.get("database", "username"),
                    database=config.get("database", "dbname"))
        self.dbpool = dbpool

    @inlineCallbacks
    def lookup(self, username):
        query = "SELECT password, totp FROM users WHERE username=%s LIMIT 1"
        try:
            debug("Looking up username %s..." % username)

            # A hit and a miss both take approximately the same amount of time.
            #   We can probably not worry about timing attacks here.
            result = yield self.dbpool.runQuery(query, (username,))
            if result:
                debug("User %s found." % username)
                returnValue(result[0])

            debug("User %s not found." % username)
        except Exception, e:
            error("Exception caught looking up user %s." % username)
            error()

