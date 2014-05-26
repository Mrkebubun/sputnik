#!/usr/bin/env python

from sendmail import Sendmail
from twisted.internet import reactor
from sys import stdin, stdout
import config
import os
import __main__ as main
import logging
from supervisor import childutils
from zmq_util import export, pull_share_async, push_proxy_async


class Alerts():
    def __init__(self, from_address, to_address, subject_prefix):
        self.factory = Sendmail(from_address)
        self.from_address = from_address
        self.to_address = to_address
        self.subject_prefix = subject_prefix

    def send_alert(self, message, subject):
        logging.debug("Sending alert: %s/%s" % (subject, message))
        self.factory.send_mail(message, subject=self.subject_prefix + " " + subject,
                               to_address=self.to_address)


class AlertsExport():
    def __init__(self, alerts):
        self.alerts = alerts

    @export
    def send_alert(self, message, subject):
        self.alerts.send_alert(message, subject)

class AlertsProxy():
    def __init__(self, zmq_export):
        self.socket = push_proxy_async(zmq_export)

    def send_alert(self, message, subject="No subject"):
        program = os.path.basename(main.__file__)
        self.socket.send_alert(message, "%s: %s" % (program, subject))

if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s', level=logging.DEBUG)
    from_address = config.get("alerts", "from")
    to_address = config.get("alerts", "to")
    subject_prefix = config.get("alerts", "subject")
    alerts = Alerts(from_address, to_address, subject_prefix)
    alerts_export = AlertsExport(alerts)
    pull_share_async(alerts_export, config.get("alerts", "export"))
    reactor.run()