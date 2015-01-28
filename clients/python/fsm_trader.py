# Copyright (c) 2014, 2015 Mimetic Markets, Inc.
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
# from fsm import FSM
from sputnik import SputnikSession

class FSMTrader(SputnikSession):
    def __init__(self):
        fsm = FSM("INIT", None)
        self.fsm = fsm
        fsm.set_default_transition(self.fsm_error, "STOP")
        fsm.add_transition("join", "INIT", self.start, "START")
        fsm.add_transition("leave", "INIT", self.notify_disconnected, "STOP")
        fsm.add_transition("leave", "START", self.notify_disconnected, "STOP")
        fsm.add_transition("leave", "FALLING", self.notify_disconnected, "STOP")
        fsm.add_transition("leave", "RISING", self.notify_disconnected, "STOP")
        fsm.add_transition("price_falling", "START", self.buy, "FALLING")
        fsm.add_transition("price_falling", "FALLING", self.buy, "FALLING")
        fsm.add_transition("price_falling", "RISING", self.buy, "FALLING")
        fsm.add_transition("price_rising", "START", self.sell, "RISING")
        fsm.add_transition("price_rising", "FALLING", self.sell, "RISING")
        fsm.add_transition("price_rising", "RISING", self.sell, "RISING")

    def onJoin(self, details):
        SputnikSession.onJoin(details)
        self.fsm.process("join")

    def onLeave(self, details):
        self.fsm.process("leave")

    def buy(self, fsm):
        # decide if we want to buy and how much
        pass

    def sell(self, fsm):
        # decide if we want to sell and how much
        pass

    def start(self, fsm):
        pass

    def onMarkets(self, markets):
        # save a base price for the market here
        pass

    def onBook(self, uri, book):
        # read off new price and emit a "price_rising" or "price_falling"
        #   after doing a small time average
        pass

    def notify_disconnected(self, fsm):
        print "Disconnected. Stopped."

    def fsm_error(self, fsm):
        print "FSM encountered an error. Stopped."

