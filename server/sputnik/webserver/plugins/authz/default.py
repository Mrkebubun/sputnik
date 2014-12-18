from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("permissions")

from sputnik.webserver.plugin import AuthorizationPlugin
from autobahn.wamp import types
from autobahn.wamp.interfaces import IRouter
import re
from sputnik import util

class DefaultPermissions(AuthorizationPlugin):
    def __init__(self):
        AuthorizationPlugin.__init__(self)

    def authorize(self, router, session, uri, action):
        debug("Checking permissions for %s(%s) to %s %s" % \
              (session._authid, session._authrole, \
               IRouter.ACTION_TO_STRING[action], uri))
        
        # allow trusted roles to do everything
        if session._authrole == u"trusted":
            log("Authorizing %s(%s) to %s %s" % \
                (session._authid, session._authrole, \
                 IRouter.ACTION_TO_STRING[action], uri))
            return True

        # allow others to only call and subscribe
        if action not in [IRouter.ACTION_CALL, IRouter.ACTION_SUBSCRIBE]:
            return False

        # Rpc calls
        rpc_match = re.compile("^rpc\.([a-z_.]+)\.")
        match = rpc_match.match(uri)
        if match is not None:
            section = match.groups(1)[0]
            # Some sections give to everyone
            if section in ["info", "market", "registrar"]:
                log("Authorizing %s(%s) to %s %s" % \
                    (session._authid, session._authrole, \
                     IRouter.ACTION_TO_STRING[action], uri))
                return True
            if section in ["trader", "private"] and session._authrole == u"user":
                log("Authorizing %s(%s) to %s %s" % \
                    (session._authid, session._authrole, \
                     IRouter.ACTION_TO_STRING[action], uri))
                return True
            return False

        feed_match = re.compile("^feeds\.([a-z_]+)\.")
        match = feed_match.match(uri)
        if match is not None:
            section = match.groups(1)[0]
            if section in ["market"]:
                return True
            if section in ["user"] and session._authrole == u"user":
                # Make sure we can read this feed
                # Check for sha256
                user_match = re.compile("^feeds\.%s\.[a-z_]+\.([0-9a-f]+)$" % section)
                match = user_match.match(uri)
                if match is not None:
                    hash = match.groups(1)[0]
                    if hash == util.encode_username(session._authid):
                        log("Authorizing %s(%s) to %s %s" % \
                            (session._authid, session._authrole, \
                             IRouter.ACTION_TO_STRING[action], uri))
                        return True

            # No joy, no access
            return False

