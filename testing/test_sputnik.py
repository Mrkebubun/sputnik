__author__ = 'sameer'

from twisted.trial import unittest
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


def dumpArgs(func):
    '''Decorator to print function call details - parameters names and effective values'''

    def wrapper(*func_args, **func_kwargs):
        arg_names = func.func_code.co_varnames[:func.func_code.co_argcount]
        args = func_args[:len(arg_names)]
        defaults = func.func_defaults or ()
        args = args + defaults[len(defaults) - (func.func_code.co_argcount - len(args)):]
        params = zip(arg_names, args)
        args = func_args[len(arg_names):]
        if args: params.append(('args', args))
        if func_kwargs: params.append(('kwargs', func_kwargs))
        ret_val = func(*func_args, **func_kwargs)
        print func.func_name + ' (' + ', '.join('%s = %r' % p for p in params) + ' )=' + str(ret_val)
        return ret_val

    return wrapper


class FakeProxy:
    def __init__(self):
        self.log = []

    def __getattr__(self, key):
        if key.startswith("__"):
            raise AttributeError

        def proxy_method(*args, **kwargs):
            self.log.append((key, args, kwargs))
            return None

        return proxy_method

    # Checks if arg_compare's elements that exist in arg
    # match what is in arg. If there is an element in arg_compare as a dict
    # that doesn't exist in arg, it is ignored
    @dumpArgs
    def check(self, arg, arg_compare):
        if arg == arg_compare:
            return True
        else:
            if isinstance(arg, (list, tuple)) and isinstance(arg_compare, (list, tuple)):
                for arg_a, arg_b in zip(arg, arg_compare):
                    return self.check(arg_a, arg_b)
            if isinstance(arg, dict) and isinstance(arg_compare, dict):
                for key, value in arg.iteritems():
                    if key not in arg_compare:
                        return False
                    return self.check(value, arg_compare[key])
            else:
                return False

    def check_for_call(self, method, args, kwargs):
        for log_entry in self.log:
            found = False
            if log_entry[0] == method:
                if self.check(args, log_entry[1]) and self.check(kwargs, log_entry[2]):
                    return log_entry

        return None

    def check_for_calls(self, calls):
        for call in calls:
            if self.check_for_call(call[0], call[1], call[2]) is None:
                print "Check failure in %s" % str(call)
                return False

        return True


class TestSputnik(unittest.TestCase):
    def setUp(self):
        test_config = "[database]\nuri = sqlite://"
        from sputnik import config

        config.reset()
        config.readfp(StringIO.StringIO(test_config))

        from sputnik import database, models

        self.session = database.make_session()

        import leo

        self.leo = leo.LowEarthOrbit(self.session)
        self.run_leo(db_init)

    def run_leo(self, init):
        for line in init.split("\n"):
            self.leo.parse(line)
        self.session.commit()

    def create_account(self, username, address=None, currency='btc'):
        self.leo.parse("accounts add %s" % username)
        self.session.commit()

        if address is not None:
            self.add_address(username, address, currency=currency)

    def add_address(self, username=None, address=None, currency='btc'):
        self.leo.parse("addresses add %s %s" % (currency, address))
        if username is not None:
            self.leo.parse("addresses modify %s username %s" % (address, username))
            self.leo.parse("addresses modify %s active 1" % address)
        self.session.commit()
