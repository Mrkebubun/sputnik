from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("schema")

from sputnik.webserver.plugin import SchemaPlugin

class JSONSchema(SchemaPlugin):
    def __init__(self):
        SchemaPlugin.__init__(self, u"json")

    def validate(self, type, uri, args, kwargs):
        return True

