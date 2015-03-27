#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("cashier_proxy")

from sputnik.webserver.plugin import BackendPlugin
from sputnik.zmq_util import dealer_proxy_async

class CashierProxy(BackendPlugin):
    def __init__(self):
        BackendPlugin.__init__(self)
        self.proxy = dealer_proxy_async(
                config.get("cashier", "webserver_export"))

