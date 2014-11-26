from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("permissions")

from sputnik.webserver.plugins import AuthorizationPlugin
from autobahn.wamp import types

class BasicPermissions(AuthorizationPlugin):
    def __init__(self):
        AuthorizationPlugin.__init__(self, u"basic_permissions")

    def authorize(self, router, session, uri, action):
        log("Authorizing %s(%s) to %s %s" % \
                (session._authid, session._authrole, \
                 IRouter.ACTION_TO_STRING[action], uri))
        
        return True

