#!/usr/bin/env python
# Copyright (c) 2014, Mimetic Markets, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# 1. Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
# IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
# TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
# TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
__author__ = 'sameer'
import sys

from twisted.python import log
from twisted.internet import reactor, ssl, task

from autobahn.twisted.websocket import connectWS

from client import BotFactory
from random_trader import RandomBot
from market_maker import MarketMakerBot
import random
import string
import logging
import argparse

class LoadTester():
    def onMakeAccount(self, event):
        RandomBot.onMakeAccount(self, event)
        self.authenticate()

    def startAutomation(self):
        # Now make an account
        self.username = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        self.password = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        self.makeAccount(self.username, self.password, "%s@m2.io" % self.username, "Test User %s" % self.username)

class MarketLoadTester(LoadTester, MarketMakerBot):
    pass

class RandomLoadTester(LoadTester, RandomBot):
    place_all_random = True
    pass

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s', level=logging.DEBUG)


    log.startLogging(sys.stdout)

    parser = argparse.ArgumentParser(description='Test a Sputnik exchange under load')
    parser.add_argument('uri', help="the websockets URI for the exchange")
    parser.add_argument('-r', '--rate', type=float, help="pause in s between orders", default=1)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--random', help="Run the random bot", action="store_true")
    group.add_argument('--market', help="RUn the marketmaker bot", action="store_true")

    args = parser.parse_args()

    factory = BotFactory(args.uri, debugWamp=False, rate=args.rate)
    if args.random:
        factory.protocol = RandomLoadTester
    elif args.market:
        factory.protocol = MarketLoadTester

    # null -> ....
    if factory.isSecure:
        contextFactory = ssl.ClientContextFactory()
    else:
        contextFactory = None

    connectWS(factory, contextFactory)
    reactor.run()