from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("administrator_proxy")

from sputnik.webserver.plugin import BackendPlugin
from sputnik.zmq_util import dealer_proxy_async

class AdministratorProxy(BackendPlugin):
    def __init__(self):
        BackendPlugin.__init__(self)
        self.proxy = dealer_proxy_async(
                config.get("administrator", "webserver_export"))

