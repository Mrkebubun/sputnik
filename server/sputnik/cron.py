#!/usr/bin/env python
#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

__author__ = 'sameer'

import sys

from twisted.python import log
from twisted.internet import reactor

import config
from zmq_util import dealer_proxy_async
import argparse


class Cron:
    def __init__(self, administrator):
        self.administrator = administrator

    def mail_statements(self, period):
        return self.administrator.mail_statements(period)

    def mtm_futures(self):
        self.administrator.notify_expired()
        return self.administrator.mtm_futures()

if __name__ == "__main__":
    log.startLogging(sys.stdout)

    administrator = dealer_proxy_async(config.get("administrator", "cron_export"), timeout=300)
    cron = Cron(administrator)

    # Parse arguments to figure out what to do
    parser = argparse.ArgumentParser(description="Run Sputnik jobs out of cron")
    subparsers = parser.add_subparsers(description="job that is to be performed", metavar="command", dest="command")
    parser_mail_statements = subparsers.add_parser("mail_statements", help="Mail statements to users")
    parser_mail_statements.add_argument("--period", dest="period", action="store", default="monthly",
                                        help="Statement period", choices=["monthly", "weekly", "daily"])
    parser_mtm_futures = subparsers.add_parser("mtm_futures", help="mark futures contracts to market")

    kwargs = vars(parser.parse_args())
    command = kwargs["command"]
    del kwargs["command"]

    method = getattr(cron, command)

    result = method(**kwargs)
    def _cb(result):
        log.msg("%s result: %s" % (command, result))
        reactor.stop()
    def _err(failure):
        log.err(failure)
        reactor.stop()

    result.addCallback(_cb).addErrback(_err)
    reactor.run()







