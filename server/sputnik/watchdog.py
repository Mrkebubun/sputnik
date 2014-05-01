#!/usr/bin/env python

import zmq_util
from twisted.application.internet import TimerService
from twisted.internet import reactor
from datetime import datetime, timedelta
import logging
import config

class WatchdogExport(object):
    @zmq_util.export
    def ping(self, id):
        return id

def watchdog(address):
    return zmq_util.router_share_async(WatchdogExport(), address)

class Watchdog(object):
    def __init__(self, name, address, step=60):
        self.process = zmq_util.dealer_proxy_async(address)
        self.name = name
        self.step_timedelta = timedelta(seconds=step)
        self.timer_service = TimerService(step, self.ping)
        self.next_ping_id = 0
        self.ping_times = {}

    def got_ping(self, id):
        gap = datetime.utcnow() - self.ping_times[id]
        logging.info("%s ping %d received: %f ms" % (self.name, id, gap.total_seconds() * 1000))

    def ping_error(self, error):
        logging.error("%s ping error: %s" % (self.name, error))

    def ping(self):
        self.ping_times[self.next_ping_id] = datetime.utcnow()
        d = self.process.ping(self.next_ping_id)
        self.next_ping_id += 1
        d.addCallbacks(self.got_ping, self.ping_error)

    def run(self):
        self.timer_service.startService()

if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s', level=logging.INFO)
    monitors = config.items("watchdog")
    watchdogs = {}
    for name, address in monitors:
        watchdogs[name] = Watchdog(name, address)
        watchdogs[name].run()

    reactor.run()
