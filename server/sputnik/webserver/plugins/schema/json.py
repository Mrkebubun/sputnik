from sputnik import observatory
from sputnik import rpc_schema

import re

debug, log, warn, error, critical = observatory.get_loggers("schema")

from sputnik.webserver.plugin import SchemaPlugin

class JSONSchema(SchemaPlugin):
    def __init__(self):
        SchemaPlugin.__init__(self)
        self.validators = {}
        self.pattern = re.compile(r"[^a-zA-Z0-9_]")

    def validate(self, router, type, uri, args, kwargs):
        # WARNING WARNING WARNING WARNING WARNING
        # validate gets called _BEFORE_ authorize
        # make sure the user cannot to arbitrary filesystem traversal
        #   by trying to read schemas

        tokens = uri.split(".")
        if tokens[0] != "rpc" or len(tokens) != 3:
            warn("Malicious uri found checking schema: %s." % uri)
            return False

        if self.pattern.search(tokens[1]):
            warn("Malicious uri found checking schema: %s." % uri)
            return False

        if self.pattern.search(tokens[2]):
            warn("Malicious uri found checking schema: %s." % uri)
            return False

        path = "public/%s#%s" % tuple(tokens[1:])

        validate = self.validators.get(path)
        if validate is None:
            debug("Cache miss for %s." % uri)
            try:
                validate = rpc_schema.build_call_validate(uri)
                self.validators[path] = validate
            except IOError:
                error("No schema found for %s." % uri)
                return False

        try:
            validate(*args, **kwargs)
            debug("Valid arguments passed to %s." % uri)
        except Exception:
            warn("Invalid arguments passed to %s." % uri)
            return False

        return True

