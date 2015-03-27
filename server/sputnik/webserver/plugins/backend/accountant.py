#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

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
