from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("alerts_proxy")

from sputnik.webserver.plugin import BackendPlugin
from sputnik.alerts import AlertsProxy as ap

class AlertsProxy(BackendPlugin):
    def __init__(self):
        BackendPlugin.__init__(self)
        self.proxy = ap(config.get("alerts", "export"))


