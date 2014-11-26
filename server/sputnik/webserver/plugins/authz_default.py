from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("permissions")

from sputnik.webserver.plugin import AuthorizationPlugin
from autobahn.wamp import types
from autobahn.wamp.interfaces import IRouter

class DefaultPermissions(AuthorizationPlugin):
    def __init__(self):
        AuthorizationPlugin.__init__(self, u"default")

    def authorize(self, router, session, uri, action):
        log("Authorizing %s(%s) to %s %s" % \
                (session._authid, session._authrole, \
                 IRouter.ACTION_TO_STRING[action], uri))
        
        # allow trusted roles to do everything
        if session._authrole == u"trusted":
            return True

        # allow others to only call and subscribe
        if action not in [IRouter.ACTION_CALL, IRouter.ACTION_SUBSCRIBE]:
            return False

        # allow anonymous access to only public URIs
        if session._authrole == u"anonymous":
            if uri.startswith("sputnik.methods.public"):
                return True
            if uri.startswith("sputnik.feeds.public"):
                return True
            return False

        # allow authenticated users access to authenticated methods and feeds
        if session._authrole == u"user":
            # allow calls to private methods
            if uri.startswith("sputnik.methods.private"):
                return True
            # TODO: figure out what to match for private feeds
            if uri.startswith("sputnik.feeds.private.number"):
                return True
            return False

