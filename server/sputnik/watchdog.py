#!/usr/bin/env python
#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

import sys
import zmq_util
from twisted.internet import reactor
from twisted.python import log
from datetime import datetime
import config
from alerts import AlertsProxy
import database
import models


class WatchdogExport(object):
    @zmq_util.export
    def ping(self):
        return "pong"

def watchdog(address):
    return zmq_util.router_share_async(WatchdogExport(), address)

class Watchdog():
    def __init__(self, name, address, alerts_proxy, step=60):
        self.process = zmq_util.dealer_proxy_async(address, timeout=10)
        self.alerts_proxy = alerts_proxy
        self.name = name
        self.step = step
        self.last_ping_time = None
        self.ping_limit_ms = 200

    def got_ping(self, event=None):
        gap = datetime.utcnow() - self.last_ping_time
        ms = gap.total_seconds() * 1000
        log.msg("%s ping received: %0.3f ms" % (self.name, ms))
        if ms > self.ping_limit_ms:
            self.alerts_proxy.send_alert("%s lag > %d ms: %0.3f ms" % (self.name, self.ping_limit_ms,
                                                                       ms), "Excess lag detected")

    def ping_error(self, error):
        self.alerts_proxy.send_alert("%s ping error: %s" % (self.name, error), "Ping error")

    def ping(self):
        self.last_ping_time = datetime.utcnow()
        d = self.process.ping()
        d.addCallbacks(self.got_ping, self.ping_error)
        d.addCallback(self.schedule_ping)

    def schedule_ping(self, event=None):
        reactor.callLater(self.step, self.ping)

    def run(self):
        log.msg("Watchdog %s starting" % self.name)
        self.schedule_ping()

if __name__ == "__main__":
    log.startLogging(sys.stdout)
    monitors = ["administrator", "cashier", "ledger", "webserver"]
    session = database.make_session()
    proxy = AlertsProxy(config.get("alerts", "export"))
    watchdogs = {}
    for name in monitors:
        watchdogs[name] = Watchdog(name, config.get("watchdog", name), proxy)
        watchdogs[name].run()

    num_accountants = config.getint("accountant", "num_procs")
    for i in range(num_accountants):
        name = "accountant_%d" % i
        watchdogs[name] = Watchdog(name, config.get("watchdog", "accountant") % (config.getint("watchdog", "accountant_base_port") + i), proxy)
        watchdogs[name].run()

    engine_base_port = config.getint("watchdog", "engine_base_port")
    for contract in session.query(models.Contract).filter_by(active=True).all():
        if contract.contract_type != "cash":
            watchdogs[contract.ticker] = Watchdog(contract.ticker, config.get("watchdog", "engine") % (engine_base_port +
                                                                                          int(contract.id)), proxy)
            watchdogs[contract.ticker].run()

    reactor.run()
