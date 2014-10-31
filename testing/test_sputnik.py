__author__ = 'sameer'

from twisted.trial import unittest
import sys
import os
import StringIO
import logging
from twisted.internet import defer
from twisted.web.server import NOT_DONE_YET
import copy

logging.basicConfig(level=1000)

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../tools"))

db_init = """
database init
contracts add BTC
contracts add MXN
contracts add PLN
contracts add HUF

contracts add BTC/MXN
contracts add BTC/PLN
contracts add BTC/HUF

contracts add NETS2014
contracts set NETS2014 contract_type prediction
contracts set NETS2014 denominator 1000
contracts set NETS2014 lot_size 1000000
contracts set NETS2014 tick_size 1
contracts set NETS2014 expiration 2014-06-28
contracts set NETS2014 denominated_contract_ticker BTC
contracts set NETS2014 fees 200

contracts add NETS2015
contracts set NETS2015 contract_type prediction
contracts set NETS2015 denominator 1000
contracts set NETS2015 lot_size 1000000
contracts set NETS2015 tick_size 1
contracts set NETS2015 expiration 2015-06-28
contracts set NETS2015 denominated_contract_ticker BTC
contracts set NETS2015 fees 200

contracts set BTC contract_type cash
contracts set BTC denominator 100000000
contracts set BTC lot_size 1000000

contracts set MXN contract_type cash
contracts set MXN denominator 10000
contracts set MXN lot_size 100

contracts set PLN contract_type cash
contracts set PLN denominator 10000
contracts set PLN lot_size 100

contracts set HUF contract_type cash
contracts set HUF denominator 100
contracts set HUF lot_size 100

contracts set BTC/MXN contract_type cash_pair
contracts set BTC/MXN tick_size 100
contracts set BTC/MXN lot_size 1000000
contracts set BTC/MXN denominator 1
contracts set BTC/MXN denominated_contract_ticker MXN
contracts set BTC/MXN payout_contract_ticker BTC
contracts set BTC/MXN fees 100

contracts set BTC/PLN contract_type cash_pair
contracts set BTC/PLN tick_size 100
contracts set BTC/PLN lot_size 1000000
contracts set BTC/PLN denominator 1
contracts set BTC/PLN denominated_contract_ticker PLN
contracts set BTC/PLN payout_contract_ticker BTC
contracts set BTC/PLN fees 100

contracts set BTC/HUF contract_type cash_pair
contracts set BTC/HUF tick_size 100
contracts set BTC/HUF lot_size 1000000
contracts set BTC/HUF denominator 1
contracts set BTC/HUF denominated_contract_ticker HUF
contracts set BTC/HUF payout_contract_ticker BTC
contracts set BTC/HUF fees 100

permissions add Default login
permissions add Full trade withdraw deposit login
permissions add NoTrade withdraw deposit login

fees add Default 100 100

accounts add customer
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
accounts set onlinecash type Asset

accounts add offlinecash
accounts set offlinecash type Asset

accounts add depositoverflow
accounts set depositoverflow type Liability

accounts add pendingwithdrawal
accounts set pendingwithdrawal type Liability

accounts add adjustments
accounts set adjustments type Asset

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

class FakeComponent:
    def __init__(self, name=None):
        self.log = []
        self.name = name
        self.component = self

    def _log_call(self, key, *args, **kwargs):
        self.log.append((key, copy.deepcopy(args), copy.deepcopy(kwargs)))
        if self.name:
            callspec = []
            callspec.extend(args)
            callspec.extend("%s=%s" % (key, repr(value)) \
                    for key, value in kwargs.iteritems())
            logging.info("Method call: %s.%s%s" %
                    (self.name, key, str(tuple(callspec))))

    def __getattr__(self, key):
        if key.startswith("__"):
            raise AttributeError

        def proxy_method(*args, **kwargs):
            self._log_call(key, *args, **kwargs)

            return None

        return proxy_method

    # Checks if arg_compare's elements that exist in arg
    # match what is in arg. If there is an element in arg_compare as a dict
    # that doesn't exist in arg, it is ignored
    @staticmethod
    def check(arg, arg_compare):
        def same(a, b):
            from sputnik import engine2
            if isinstance(a, engine2.Order) and isinstance(b, engine2.Order):
                return a.side == b.side and a.price == b.price \
                           and a.quantity == b.quantity and a.quantity_left == b.quantity_left
            else:
                return arg == arg_compare

        if same(arg, arg_compare):
            return True
        else:
            if isinstance(arg, (list, tuple)) and isinstance(arg_compare, (list, tuple)):
                for arg_a, arg_b in zip(arg, arg_compare):
                    if not FakeComponent.check(arg_a, arg_b):
                        return False
                return True
            if isinstance(arg, dict) and isinstance(arg_compare, dict):
                for key, value in arg.iteritems():
                    if key not in arg_compare or not FakeComponent.check(value, arg_compare[key]):
                        return False

                return True
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
                #print "Check failure in %s" % str(call)
                return False

        return True

# TODO: Remove this once we've removed all FakeProxy
class FakeProxy(FakeComponent):
    pass

class FakeSendmail(FakeComponent):
    def __init__(self, from_address):
        """

        :param from_address:
        """
        self.from_address = from_address
        FakeComponent.__init__(self, "sendmail")

def fix_config():
    spec_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server", "sputnik", "specs"))
    test_config = "[database]\nuri = sqlite://\n[specs]\nschema_root=%s\n[accountant]\nnum_proces = 0\n" % \
            spec_dir
    from sputnik import config

    config.reset()
    config.readfp(StringIO.StringIO(test_config))

class TestSputnik(unittest.TestCase):
    def setUp(self):
        logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s',
                            level=logging.DEBUG)
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        fix_config()

        from sputnik import database, models

        self.session = database.make_session()

        import leo

        self.leo = leo.LowEarthOrbit(self.session)
        self.run_leo(db_init)

    def run_leo(self, init):
        for line in init.split("\n"):
            self.leo.parse(line)
        self.session.commit()

    def create_account(self, username, address=None, currency='BTC', password=None, ):
        self.leo.parse("accounts add %s" % username)
        if password is not None:
            self.leo.parse("accounts password %s %s" % (username, password))

        # Initialize a position
        self.leo.parse("accounts position %s %s" % (username, currency))
        self.session.commit()

        if address is not None:
            self.add_address(username, address, currency=currency)

    def get_user(self, username):
        from sputnik import models
        user = self.session.query(models.User).filter_by(username=username).one()
        return user

    def get_contract(self, ticker):
        from sputnik import models
        contract = self.session.query(models.Contract).filter_by(ticker=ticker).one()
        return contract

    def add_address(self, username=None, address=None, currency='BTC'):
        self.leo.parse("addresses add %s %s" % (currency, address))
        if username is not None:
            self.leo.parse("addresses set %s username %s" % (address, username))
            self.leo.parse("addresses set %s active 1" % address)
        self.session.commit()

    def render_test_helper(self, resource, request):
        result = resource.render(request)
        if isinstance(result, str):
            request.write(result)
            request.finish()
            return defer.succeed(None)
        elif result is NOT_DONE_YET:
            if request.finished:
                return defer.succeed(None)
            else:
                return request.notifyFinish()
        else:
            raise ValueError("Unexpected return value: %r" % (result,))
