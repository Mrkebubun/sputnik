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

__author__ = 'sameer'

import sys

from twisted.python import log
from twisted.internet import reactor, ssl, task

from autobahn.twisted.websocket import connectWS
from ConfigParser import ConfigParser

from client import TradingBot, BotFactory
from collections import deque
import logging
from os import path

# http://code.activestate.com/recipes/440546-chomsky-random-text-generator/
"""CHOMSKY is an aid to writing linguistic papers in the style
    of the great master.  It is based on selected phrases taken
    from actual books and articles written by Noam Chomsky.
    Upon request, it assembles the phrases in the elegant
    stylistic patterns that Chomsky is noted for.
    To generate n sentences of linguistic wisdom, type
        (CHOMSKY n)  -- for example
        (CHOMSKY 5) generates half a screen of linguistic truth."""

leadins = """To characterize a linguistic level L,
    On the other hand,
    This suggests that
    It appears that
    Furthermore,
    We will bring evidence in favor of the following thesis:
    To provide a constituent structure for T(Z,K),
    From C1, it follows that
    For any transformation which is sufficiently diversified in application to be of any interest,
    Analogously,
    Clearly,
    Note that
    Of course,
    Suppose, for instance, that
    Thus
    With this clarification,
    Conversely,
    We have already seen that
    By combining adjunctions and certain deformations,
    I suggested that these results would follow from the assumption that
    If the position of the trace in (99c) were only relatively inaccessible to movement,
    However, this assumption is not correct, since
    Comparing these examples with their parasitic gap counterparts in (96) and (97), we see that
    In the discussion of resumptive pronouns following (81),
    So far,
    Nevertheless,
    For one thing,
    Summarizing, then, we assume that
    A consequence of the approach just outlined is that
    Presumably,
    On our assumptions,
    It may be, then, that
    It must be emphasized, once again, that
    Let us continue to suppose that
    Notice, incidentally, that """
# List of LEADINs to buy time.

subjects = """ the notion of level of grammaticalness
    a case of semigrammaticalness of a different sort
    most of the methodological work in modern linguistics
    a subset of English sentences interesting on quite independent grounds
    the natural general principle that will subsume this case
    an important property of these three types of EC
    any associated supporting element
    the appearance of parasitic gaps in domains relatively inaccessible to ordinary extraction
    the speaker-hearer's linguistic intuition
    the descriptive power of the base component
    the earlier discussion of deviance
    this analysis of a formative as a pair of sets of features
    this selectionally introduced contextual feature
    a descriptively adequate grammar
    the fundamental error of regarding functional notions as categorial
    relational information
    the systematic use of complex symbols
    the theory of syntactic features developed earlier"""
# List of SUBJECTs chosen for maximum professorial macho.

verbs = """can be defined in such a way as to impose
    delimits
    suffices to account for
    cannot be arbitrary in
    is not subject to
    does not readily tolerate
    raises serious doubts about
    is not quite equivalent to
    does not affect the structure of
    may remedy and, at the same time, eliminate
    is not to be considered in determining
    is to be regarded as
    is unspecified with respect to
    is, apparently, determined by
    is necessary to impose an interpretation on
    appears to correlate rather closely with
    is rather different from"""
#List of VERBs chosen for autorecursive obfuscation.

objects = """ problems of phonemic and morphological analysis.
    a corpus of utterance tokens upon which conformity has been defined by the paired utterance test.
    the traditional practice of grammarians.
    the levels of acceptability from fairly high (e.g. (99a)) to virtual gibberish (e.g. (98d)).
    a stipulation to place the constructions into these various categories.
    a descriptive fact.
    a parasitic gap construction.
    the extended c-command discussed in connection with (34).
    the ultimate standard that determines the accuracy of any proposed grammar.
    the system of base rules exclusive of the lexicon.
    irrelevant intervening contexts in selectional rules.
    nondistinctness in the sense of distinctive feature theory.
    a general convention regarding the forms of the grammar.
    an abstract underlying order.
    an important distinction in language use.
    the requirement that branching is not tolerated within the dominance scope of a complex symbol.
    the strong generative capacity of the theory."""
# List of OBJECTs selected for profound sententiousness.

import textwrap, random
from itertools import chain, islice, izip

def chomsky(times=1, line_length=72):
    parts = []
    for part in (leadins, subjects, verbs, objects):
        phraselist = map(str.strip, part.splitlines())
        random.shuffle(phraselist)
        parts.append(phraselist)
    output = chain(*islice(izip(*parts), 0, times))
    return textwrap.fill(' '.join(output), line_length).split('\n')

class RandomBot(TradingBot):
    def startAutomationAfterAuth(self):
        self.place_orders = task.LoopingCall(self.placeRandomOrder)
        self.place_orders.start(1 * self.factory.rate)

        self.chomsky = deque(chomsky())
        self.chatter = task.LoopingCall(self.saySomethingRandom)
        self.chatter.start(6 * self.factory.rate)

        return True

    def startAutomation(self):
        self.authenticate()

    def placeRandomOrder(self):
        random_markets = []
        for ticker, contract in self.markets.iteritems():
            if contract['contract_type'] != "cash":
                random_markets.append(ticker)

        # Pick a market at random
        ticker = random.choice(random_markets)
        side = random.choice(["BUY", "SELL"])
        contract = self.markets[ticker]

        # Look at best bid/ask
        try:
            # Distance is [0.95,1.05]
            distance = float(random.randint(0,10))/100 + 0.95

            # Post something close to the bid or ask, depending on the size
            if side is 'BUY':
                best_ask = min([order['price'] for order in self.markets[ticker]['asks']])
                price = self.price_from_wire(ticker, best_ask) * distance
            else:
                best_bid = max([order['price'] for order in self.markets[ticker]['bids']])
                price = self.price_from_wire(ticker, best_bid) * distance

        except (ValueError, KeyError):
            # We don't have a best bid/ask. If it's a prediction contract, pick a random price
            if contract['contract_type'] == "prediction":
                price = float(random.randint(0,1000))/1000
            else:
                return

        # a qty somewhere between 0.5 and 2 BTC
        if contract['contract_type'] == "prediction":
            quantity = random.randint(1, 4)
        else:
            quantity = float(random.randint(50, 200))/100

        self.placeOrder(ticker, self.quantity_to_wire(ticker, quantity),
                        self.price_to_wire(ticker, price), side)

    def saySomethingRandom(self):
        try:
            random_saying = self.chomsky.popleft()
        except IndexError:
            self.chomsky.extend(chomsky())
            random_saying = self.chomsky.popleft()

        self.chat(random_saying)

    def cancelRandomOrder(self):
        if len(self.orders.keys()) > 0:
            while True:
                order_to_cancel = random.choice(self.orders.keys())
                if not self.orders[order_to_cancel]['is_cancelled'] and self.orders[order_to_cancel]['quantity_left'] > 0:
                    break
            self.cancelOrder(order_to_cancel)

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s', level=logging.DEBUG)

    if len(sys.argv) > 1 and sys.argv[1] == 'debug':
        debug = True
    else:
        debug = False

    log.startLogging(sys.stdout)
    config = ConfigParser()
    config_file = path.abspath(path.join(path.dirname(__file__),
            "./client.ini"))
    config.read(config_file)

    uri = config.get("client", "uri")
    username = config.get("random_trader", "username")
    password = config.get("random_trader", "password")
    rate = config.getfloat("random_trader", "rate")

    factory = BotFactory(uri, debugWamp=debug, username_password=(username, password), rate=rate)
    factory.protocol = RandomBot

    # null -> ....
    if factory.isSecure:
        contextFactory = ssl.ClientContextFactory()
    else:
        contextFactory = None

    connectWS(factory, contextFactory)
    reactor.run()
