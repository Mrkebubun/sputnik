#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

__author__ = 'sameer'

import sys
import os
from test_sputnik import fix_config, TestSputnik, FakeComponent
from twisted.internet import defer, reactor, task
from pprint import pprint

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../tools"))

fix_config()

from sputnik import models, margin


class TestFees(TestSputnik):
    def setUp(self):
        TestSputnik.setUp(self)
        fees_init = """
fees add LiqRebate 100 -50 100 50
fees add NoFee 0 0 0 0
fees add HeavyFee 200 200 200 400

accounts set marketmaker fees LiqRebate
accounts set randomtrader fees HeavyFee
accounts set m2 fees NoFee

contracts set BTC/MXN fees 50
contracts set NETS2015 fees 350

contracts set MXN deposit_bps_fee 200
contracts set MXN withdraw_bps_fee 100
contracts set MXN deposit_base_fee 50
contracts set MXN withdraw_base_fee 100
"""
        self.run_leo(fees_init)

    def test_trade_fees(self):
        from sputnik import util

        BTCMXN = self.get_contract('BTC/MXN')
        NETS2015 = self.get_contract('NETS2015')
        BTCHUF = self.get_contract('BTC/HUF')
        NETS2014 = self.get_contract('NETS2014')

        marketmaker = self.get_user('marketmaker')
        randomtrader = self.get_user('randomtrader')
        m2 = self.get_user('m2')
        customer = self.get_user('customer')

        fees_result = {}
        for user in [marketmaker, randomtrader, m2, customer]:
            for contract in [BTCMXN, NETS2015, BTCHUF, NETS2014]:
                for ap in [None, "aggressive", "passive"]:
                    cash_spent = 1000000000
                    price = 1000000
                    if contract.contract_type == "futures" or contract.contract_type == "prediction":
                        quantity = cash_spent * contract.denominator / price / contract.lot_size
                    else:
                        payout_contract = contract.payout_contract
                        quantity = cash_spent * contract.denominator * payout_contract.denominator / price

                    fees_result[(user.username, contract.ticker, ap)] = util.get_fees(user, contract, price, quantity,
                                                                                      ap=ap)

        self.assertDictEqual(fees_result, {(u'customer', u'BTC/HUF', None): {u'HUF': 10000000},
                                           (u'customer', u'BTC/HUF', 'aggressive'): {u'HUF': 10000000},
                                           (u'customer', u'BTC/HUF', 'passive'): {u'HUF': 10000000},
                                           (u'customer', u'BTC/MXN', None): {u'MXN': 5000000},
                                           (u'customer', u'BTC/MXN', 'aggressive'): {u'MXN': 5000000},
                                           (u'customer', u'BTC/MXN', 'passive'): {u'MXN': 5000000},
                                           (u'customer', u'NETS2014', None): {u'BTC': 20000000},
                                           (u'customer', u'NETS2014', 'aggressive'): {u'BTC': 20000000},
                                           (u'customer', u'NETS2014', 'passive'): {u'BTC': 20000000},
                                           (u'customer', u'NETS2015', None): {u'BTC': 35000000},
                                           (u'customer', u'NETS2015', 'aggressive'): {u'BTC': 35000000},
                                           (u'customer', u'NETS2015', 'passive'): {u'BTC': 35000000},
                                           (u'm2', u'BTC/HUF', None): {u'HUF': 0},
                                           (u'm2', u'BTC/HUF', 'aggressive'): {u'HUF': 0},
                                           (u'm2', u'BTC/HUF', 'passive'): {u'HUF': 0},
                                           (u'm2', u'BTC/MXN', None): {u'MXN': 0},
                                           (u'm2', u'BTC/MXN', 'aggressive'): {u'MXN': 0},
                                           (u'm2', u'BTC/MXN', 'passive'): {u'MXN': 0},
                                           (u'm2', u'NETS2014', None): {u'BTC': 0},
                                           (u'm2', u'NETS2014', 'aggressive'): {u'BTC': 0},
                                           (u'm2', u'NETS2014', 'passive'): {u'BTC': 0},
                                           (u'm2', u'NETS2015', None): {u'BTC': 0},
                                           (u'm2', u'NETS2015', 'aggressive'): {u'BTC': 0},
                                           (u'm2', u'NETS2015', 'passive'): {u'BTC': 0},
                                           (u'marketmaker', u'BTC/HUF', None): {u'HUF': 10000000},
                                           (u'marketmaker', u'BTC/HUF', 'aggressive'): {u'HUF': 10000000},
                                           (u'marketmaker', u'BTC/HUF', 'passive'): {u'HUF': -5000000},
                                           (u'marketmaker', u'BTC/MXN', None): {u'MXN': 5000000},
                                           (u'marketmaker', u'BTC/MXN', 'aggressive'): {u'MXN': 5000000},
                                           (u'marketmaker', u'BTC/MXN', 'passive'): {u'MXN': -2500000},
                                           (u'marketmaker', u'NETS2014', None): {u'BTC': 20000000},
                                           (u'marketmaker', u'NETS2014', 'aggressive'): {u'BTC': 20000000},
                                           (u'marketmaker', u'NETS2014', 'passive'): {u'BTC': -10000000},
                                           (u'marketmaker', u'NETS2015', None): {u'BTC': 35000000},
                                           (u'marketmaker', u'NETS2015', 'aggressive'): {u'BTC': 35000000},
                                           (u'marketmaker', u'NETS2015', 'passive'): {u'BTC': -17500000},
                                           (u'randomtrader', u'BTC/HUF', None): {u'HUF': 20000000},
                                           (u'randomtrader', u'BTC/HUF', 'aggressive'): {u'HUF': 20000000},
                                           (u'randomtrader', u'BTC/HUF', 'passive'): {u'HUF': 20000000},
                                           (u'randomtrader', u'BTC/MXN', None): {u'MXN': 10000000},
                                           (u'randomtrader', u'BTC/MXN', 'aggressive'): {u'MXN': 10000000},
                                           (u'randomtrader', u'BTC/MXN', 'passive'): {u'MXN': 10000000},
                                           (u'randomtrader', u'NETS2014', None): {u'BTC': 40000000},
                                           (u'randomtrader', u'NETS2014', 'aggressive'): {u'BTC': 40000000},
                                           (u'randomtrader', u'NETS2014', 'passive'): {u'BTC': 40000000},
                                           (u'randomtrader', u'NETS2015', None): {u'BTC': 70000000},
                                           (u'randomtrader', u'NETS2015', 'aggressive'): {u'BTC': 70000000},
                                           (u'randomtrader', u'NETS2015', 'passive'): {u'BTC': 70000000}}
        )

    def test_deposit_withdraw_fees(self):
        from sputnik import util

        marketmaker = self.get_user('marketmaker')
        randomtrader = self.get_user('randomtrader')
        m2 = self.get_user('m2')
        customer = self.get_user('customer')

        MXN = self.get_contract('MXN')
        fees_result = {user.username: util.get_withdraw_fees(user, MXN, 1000000) for user in
                       [marketmaker, randomtrader, m2, customer]}
        self.assertDictEqual(fees_result, {u'customer': {u'MXN': 10100},
                                           u'm2': {u'MXN': 0},
                                           u'marketmaker': {u'MXN': 10100},
                                           u'randomtrader': {u'MXN': 20200}})

        fees_result = {user.username: util.get_deposit_fees(user, MXN, 1000000) for user in
                       [marketmaker, randomtrader, m2, customer]}
        self.assertDictEqual(fees_result, {u'customer': {u'MXN': 20050},
                                           u'm2': {u'MXN': 0},
                                           u'marketmaker': {u'MXN': 10025},
                                           u'randomtrader': {u'MXN': 80200}})