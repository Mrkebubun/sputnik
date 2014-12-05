from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("accountant_proxy")

from sputnik.webserver.plugin import BackendPlugin
from sputnik.zmq_util import export, pull_share_async, dealer_proxy_async

class AccountantProxy(BackendPlugin):
    def __init__(self):
        BackendPlugin.__init__(self)

