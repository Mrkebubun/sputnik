#!/usr/bin/env python

import zmq_util
from twisted.internet import reactor
from datetime import datetime
import logging
import config
from alerts import send_alert

class WatchdogExport(object):
    @zmq_util.export
    def ping(self):
        return "pong"

def watchdog(address):
    return zmq_util.router_share_async(WatchdogExport(), address)

class Watchdog(object):
    def __init__(self, name, address, step=60):
        self.process = zmq_util.dealer_proxy_async(address)
        self.name = name
        self.step = step
        self.last_ping_time = None

    def got_ping(self, event=None):
        gap = datetime.utcnow() - self.last_ping_time
        logging.info("%s ping received: %0.3f ms" % (self.name, gap.total_seconds() * 1000))
        if gap.total_seconds() > 0.1:
            send_alert("%s lag > 100ms: %0.3f ms" % (self.name, gap.total_seconds() * 1000), "Excess lag detected: %s" % self.name)

    def ping_error(self, error):
        send_alert("%s ping error: %s" % (self.name, error), "Ping error: %s" % self.name)

    def ping(self):
        self.last_ping_time = datetime.utcnow()
        d = self.process.ping()
        d.addCallbacks(self.got_ping, self.ping_error)
        d.addCallback(self.schedule_ping)

    def schedule_ping(self, event=None):
        reactor.callLater(self.step, self.ping)

    def run(self):
        logging.info("Watchdog %s starting" % self.name)
        self.schedule_ping()

if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s', level=logging.INFO)
    monitors = config.items("watchdog")
    watchdogs = {}
    for name, address in monitors:
        watchdogs[name] = Watchdog(name, address)
        watchdogs[name].run()

    reactor.run()
