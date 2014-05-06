#!/usr/bin/env python

from sendmail import Sendmail
from sys import stdin, stdout
import config
import StringIO
import logging
from supervisor import childutils


class Alerts(object):
    def __init__(self, from_address, to_address, subject_prefix):
        self.factory = Sendmail(from_address)
        self.from_address = from_address
        self.to_address = to_address
        self.subject_prefix = subject_prefix

    def alert(self, message, subject):
        self.factory.send_mail(message, subject=self.subject_prefix + " " + subject,
                               to_address=self.to_address)

    def process_event(self, headers, data):
        logging.debug("event arrived: %s / %s" % (headers, data))
        if headers['eventname'].startswith('PROCESS_COMMUNICATION'):
            buf = StringIO.StringIO(data)
            field_line = buf.readline()
            fields = dict([x.split(':') for x in field_line.split()])
            subject = "{}:{}:{}".format(fields['groupname'],
                                        fields['processname'],
                                        fields['pid'])
            message = buf.read()
            logging.debug("Sending alert %s / %s" % (subject, message))
            self.alert(message, subject)

        childutils.listener.ok(stdout)

    def run(self):
        logging.debug("Alerter started")
        while True:
            headers, data = childutils.listener.wait(stdin, stdout)
            self.process_event(headers, data)


def send_alert(message):
    childutils.pcomm.send(message)

if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s', level=logging.DEBUG)
    from_address = config.get("alerts", "from")
    to_address = config.get("alerts", "to")
    subject_prefix = config.get("alerts", "subject")
    alerts = Alerts(from_address, to_address, subject_prefix)
    alerts.run()