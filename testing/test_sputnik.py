__author__ = 'sameer'

import unittest
import sys
import os
import StringIO

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
        "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
        "../tools"))

db_init = """
database init
contracts add BTC
contracts add MXN
contracts add BTC/MXN
contracts modify BTC contract_type cash
contracts modify BTC denominator 100000000
contracts modify MXN contract_type cash
contracts modify MXN denominator 100
contracts modify BTC/MXN contract_type cash_pair
contracts modify BTC/MXN tick_size 100
contracts modify BTC/MXN lot_size 1000000
contracts modify BTC/MXN denominator 1

permissions add Default

accounts add mexbt
accounts add m2
accounts add remainder
accounts add marketmaker
accounts password marketmaker marketmaker
accounts add randomtrader
accounts password randomtrader randomtrader
accounts position marketmaker BTC
accounts position marketmaker MXN
accounts position randomtrader BTC
accounts position randomtrader MXN

accounts add onlinecash
accounts modify onlinecash type Asset

accounts add depositoverflow
accounts modify depositoverflow type Liability

accounts add adjustments
accounts modify adjustments type Asset

admin add admin
"""

class TestSputnik(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_config = "[database]\nuri = sqlite://"
        from sputnik import config
        config.reset()
        config.readfp(StringIO.StringIO(test_config))

    def setUp(self):
        from sputnik import database, models
        self.session = database.make_session()

        import leo
        self.leo = leo.LowEarthOrbit(self.session)
        self.run_leo(db_init)

    def run_leo(self, init):
        for line in init.split("\n"):
            self.leo.parse(line)
        self.session.commit()