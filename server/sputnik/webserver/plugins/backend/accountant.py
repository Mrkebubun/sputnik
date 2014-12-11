from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("accountant_proxy")

from sputnik.webserver.plugin import BackendPlugin
from sputnik import accountant

class AccountantProxy(BackendPlugin):
    def __init__(self):
        BackendPlugin.__init__(self)
        self.proxy = accountant.AccountantProxy("dealer",
            config.get("accountant", "webserver_export"),
            config.getint("accountant", "webserver_export_base_port"))
