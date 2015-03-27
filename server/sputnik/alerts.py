#!/usr/bin/env python
#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
from sendmail import Sendmail
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from twisted.python import log
from sys import stdin, stdout
import config
import os
import __main__ as main
from supervisor import childutils
from zmq_util import export, pull_share_async, push_proxy_async, ComponentExport
import collections


class Alerts():
    def __init__(self, from_address, to_address, subject_prefix):
        self.factory = Sendmail(from_address)
        self.from_address = from_address
        self.to_address = to_address
        self.subject_prefix = subject_prefix
        self.alert_cache = collections.defaultdict(list)
        self.looping_call = LoopingCall(self.send_cached_alerts)

    def send_alert(self, message, subject, cache=True):
        if cache:
            self.alert_cache[subject].append(message)
        else:
            log.msg("Sending alert: %s/%s" % (subject, message))
            self.factory.send_mail(message, subject=self.subject_prefix + " " + subject,
                                   to_address=self.to_address)

    def send_cached_alerts(self):
        for subject, messages in self.alert_cache.items():
            self.send_alert('\n---\n'.join(messages), subject, cache=False)
            del self.alert_cache[subject]

    def start(self, time=60):
        self.looping_call.start(time, now=False)

class AlertsExport(ComponentExport):
    def __init__(self, alerts):
        self.alerts = alerts
        ComponentExport.__init__(self, alerts)

    @export
    def send_alert(self, message, subject, cache=True):
        self.alerts.send_alert(message, subject, cache=cache)

class AlertsProxy():
    def __init__(self, zmq_export):
        self.socket = push_proxy_async(zmq_export)

    def send_alert(self, message, subject="No subject"):
        program = os.path.basename(main.__file__)
        self.socket.send_alert(message, "%s: %s" % (program, subject))

if __name__ == "__main__":
    log.startLogging(stdout)
    from_address = config.get("alerts", "from")
    to_address = config.get("alerts", "to")
    subject_prefix = config.get("alerts", "subject")
    alerts = Alerts(from_address, to_address, subject_prefix)
    alerts.start()

    alerts_export = AlertsExport(alerts)
    pull_share_async(alerts_export, config.get("alerts", "export"))
    reactor.run()
