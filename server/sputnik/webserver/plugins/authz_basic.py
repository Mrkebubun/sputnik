from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("permissions")

from sputnik.webserver.plugin import AuthorizationPlugin
from autobahn.wamp import types
from autobahn.wamp.interfaces import IRouter

class BasicPermissions(AuthorizationPlugin):
    def __init__(self):
        AuthorizationPlugin.__init__(self, u"basic")

    def authorize(self, router, session, uri, action):
        log("Authorizing %s(%s) to %s %s" % \
                (session._authid, session._authrole, \
                 IRouter.ACTION_TO_STRING[action], uri))
        
        return True

