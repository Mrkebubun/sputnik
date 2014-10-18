#!/usr/bin/env python

"""
Main websocket server, accepts RPC and subscription requests from clients. It's the backbone of the project,
facilitating all communications between the client, the database and the matching engine.
"""

from optparse import OptionParser

import config
import compropago
import recaptcha

parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
                  help="config file")
(options, args) = parser.parse_args()

if options.filename:
    # noinspection PyUnresolvedReferences
    config.reconfigure(options.filename)

import cgi
import sys
import datetime
import time
import onetimepass as otp
import hashlib
import uuid
import random
from util import dt_to_timestamp, timestamp_to_dt, ChainedOpenSSLContextFactory
import json
import collections
from zmq_util import export, pull_share_async, dealer_proxy_async
from accountant import AccountantProxy
from zendesk import Zendesk
from watchdog import watchdog
from blockscore import BlockScore

from jsonschema import validate
from twisted.internet import reactor, task
from twisted.web.server import Site
from twisted.web.server import NOT_DONE_YET
from twisted.web.resource import Resource
from twisted.web.static import File
from twisted.python import log
from autobahn.twisted.websocket import listenWS
from autobahn.wamp1.protocol import exportRpc, \
    WampCraProtocol, \
    WampServerFactory, \
    WampCraServerProtocol, exportSub, exportPub

from autobahn.wamp1.protocol import CallHandler

from txzmq import ZmqFactory
import markdown

zf = ZmqFactory()

# noinspection PyUnresolvedReferences
#if config.get("database", "uri").startswith("postgres"):
#    import txpostgres as adbapi
#else:
# noinspection PyPep8Naming
import twisted.enterprise.adbapi as adbapi

# noinspection PyUnresolvedReferences
dbpassword = config.get("database", "password")
if dbpassword:
    dbpool = adbapi.ConnectionPool(config.get("database", "adapter"),
                               user=config.get("database", "username"),
                               password=dbpassword,
                               host=config.get("database", "host"),
                               port=config.get("database", "port"),
                               database=config.get("database", "dbname"))
else:
    dbpool = adbapi.ConnectionPool(config.get("database", "adapter"),
                               user=config.get("database", "username"),
                               database=config.get("database", "dbname"))


class RateLimitedCallHandler(CallHandler):
    def _callProcedure(self, call):
        """

        :param call:
        :returns:
        """

        def do_actual_call(actual_call):
            """

            :param actual_call:
            :returns:
            """
            actual_call.proto.last_call = time.time()
            return CallHandler._callProcedure(self, actual_call)

        now = time.time()
        if now - call.proto.last_call < 0.01:
            # try again later
            log.msg("rate limiting...")
            delay = max(0, call.proto.last_call + 0.01 - now)
            d = task.deferLater(reactor, delay, self._callProcedure, call)
            return d
        return do_actual_call(call)


MAX_TICKER_LENGTH = 100

class AdministratorExport:
    pass


def malicious_looking(w):
    """

    :param w:
    :returns: bool
    """
    return any(x in w for x in '<>&')

class PublicInterface:
    def __init__(self, factory):
        """

        :param factory:
        """
        self.factory = factory
        self.factory.chats = []
        self.init()

    def init(self):
        # TODO: clean this up
        """Get markets, load trade history, compute OHLCV for trade history


        """

        def _cb(res):
            """Deal with get markets SQL query results

            :param res:
            :type res: list
            """
            result = {}
            for r in res:
                result[r[0]] = {"ticker": r[0],
                                "description": r[1],
                                "denominator": r[2],
                                "contract_type": r[3],
                                "full_description": markdown.markdown(r[4], extensions=["markdown.extensions.extra",
                                                                                        "markdown.extensions.sane_lists",
                                                                                        "markdown.extensions.nl2br"
                                ]),
                                "tick_size": r[5],
                                "lot_size": r[6],
                                "denominated_contract_ticker": r[9],
                                "payout_contract_ticker": r[10]}

                if result[r[0]]['contract_type'] == 'futures':
                    result[r[0]]['margin_high'] = r[7]
                    result[r[0]]['margin_low'] = r[8]

                if result[r[0]]['contract_type'] in ['futures', 'prediction']:
                    result[r[0]]['expiration'] = dt_to_timestamp(r[11])

            self.factory.markets = result
            # Update the cache with the last 60 days of trades
            to_dt = datetime.datetime.utcnow()
            from_dt = to_dt - datetime.timedelta(days=60)
            start_dt_for_period = {
                'minute': to_dt - datetime.timedelta(minutes=60),
                'hour': to_dt - datetime.timedelta(hours=60),
                'day': to_dt - datetime.timedelta(days=60)
            }

            for ticker in self.factory.markets.keys():
                def _cb2(result, ticker):
                    """Deal with trade history sql results

                    :param result:
                    :param ticker:
                    """
                    trades = [{'contract': r[0], 'price': r[2], 'quantity': r[3],
                                                           'timestamp': dt_to_timestamp(r[1])} for r in result]
                    self.factory.trade_history[ticker] = trades
                    for period in ["minute", "hour", "day"]:
                        for trade in trades:
                            if trade['timestamp'] > dt_to_timestamp(start_dt_for_period[period]):
                                self.factory.update_ohlcv(trade, period=period)

                dbpool.runQuery(
                    "SELECT contracts.ticker, trades.timestamp, trades.price, trades.quantity FROM trades, contracts WHERE "
                    "trades.contract_id=contracts.id AND contracts.ticker=%s AND trades.timestamp >= %s AND trades.posted IS TRUE",
                    (ticker, from_dt)).addCallback(_cb2, ticker)

        return dbpool.runQuery("SELECT ticker, description, denominator, contract_type, full_description,"
                               "tick_size, lot_size, margin_high, margin_low,"
                               "denominated_contract_ticker, payout_contract_ticker, expiration FROM contracts").addCallback(_cb)

    @exportRpc("get_exchange_info")
    def get_exchange_info(self):
        return [True, self.factory.exchange_info]

    @exportRpc("get_markets")
    def get_markets(self):
        """


        :returns: list
        """
        return [True, self.factory.markets]

    @exportRpc("get_audit")
    def get_audit(self):
        """

        :returns: Deferred
        """

        def _cb(result):
            """

            :param result: what we get from the accountant
            :returns: list
            """
            return [True, result]

        def _cb_error(failure):
            """

            :param failure: The failure details from ZMQ
            :returns: list
            """
            return [False, failure.value.args]

        d = self.factory.administrator.get_audit()
        d.addCallback(_cb)
        d.addErrback(_cb_error)
        return d

    @exportRpc("get_ohlcv_history")
    def get_ohlcv_history(self, ticker, period=None, start_timestamp=None, end_timestamp=None):
        """Get all the OHLCV entries for a given period (day/minute/hour/etc) and time span

        :param ticker:
        :param period:
        :param start_timestamp:
        :param end_timestamp:
        :returns: list - [True, timestamp-indexed dict]
        """
        if start_timestamp is None:
            start_timestamp = dt_to_timestamp(datetime.datetime.utcnow() - datetime.timedelta(days=60))

        if end_timestamp is None:
            end_timestamp=dt_to_timestamp(datetime.datetime.utcnow())

        validate(ticker, {"type": "string"})
        if period is not None:
            validate(period, {"type": "string"})

        validate(start_timestamp, {"type": "number"})
        validate(end_timestamp, {"type": "number"})

        if period is not None:
            if period in self.factory.ohlcv_history[ticker]:
                ohlcv = { key: value for key, value in self.factory.ohlcv_history[ticker][period].iteritems()
                                          if value['open_timestamp'] <= end_timestamp and value['close_timestamp'] >= start_timestamp }
            else:
                ohlcv = {}
        else:
            ohlcv = {}
            for period in ["minute", "hour", "day"]:
                if period in self.factory.ohlcv_history[ticker]:
                    ohlcv.update({ key: value for key, value in self.factory.ohlcv_history[ticker][period].iteritems()
                              if value['open_timestamp'] <= end_timestamp and value['close_timestamp'] >= start_timestamp })

                    # Update the end_timestamp to the earliest key
                    end_timestamp = min(ohlcv.keys())-1


        return [True, ohlcv]

    @exportRpc("get_reset_token")
    def get_reset_token(self, username):
        """Get a password reset token for a certain user -- mail it to them

        :param username:
        :type username: str
        :returns: Deferred
        """
        d = self.factory.administrator.get_reset_token(username)

        def onTokenSuccess(result):
            """

            :param result: ignored
            :returns: list
            """
            return [True, None]

        def onTokenFail(failure):
            """

            :param failure:
            :returns: list - [False, message]
            """
            return [False, failure.value.args]

        return d.addCallbacks(onTokenSuccess, onTokenFail)

    @exportRpc("get_trade_history")
    def get_trade_history(self, ticker, from_timestamp=None, to_timestamp=None):
        """
        Gets a list of trades in recent history

        :param ticker: ticker of the contract to get the trade history from
        :returns: list - [True, list of trades]
        """
        # TODO: cache this
        # TODO: make sure return format is correct

        # sanitize input
        ticker_schema = {"type": "string"}
        validate(ticker, ticker_schema)
        time_span_schema = {"type": "number"}
        if from_timestamp is not None:
            validate(from_timestamp, time_span_schema)
        else:
            from_timestamp = dt_to_timestamp(datetime.datetime.utcnow() - datetime.timedelta(hours=1))

        if to_timestamp is not None:
            validate(to_timestamp, time_span_schema)
        else:
            to_timestamp=dt_to_timestamp(datetime.datetime.utcnow())

        # Don't get more than a couple days of trades
        delta = datetime.timedelta(microseconds=to_timestamp - from_timestamp)
        if delta.days > 2:
            return [False, (0, "Can't retrieve more than two days of trades at once")]

        ticker = ticker[:MAX_TICKER_LENGTH]

        # Filter trade history
        history = [i for i in self.factory.trade_history[ticker]
                   if i['timestamp'] <= to_timestamp and i['timestamp'] >= from_timestamp]

        return [True, history]

    @exportRpc("get_order_book")
    def get_order_book(self, ticker):
        """Get the order book for a given ticker

        :param ticker:
        :returns: list - [success/fail, result]
        """
        validate(ticker, {"type": "string"})

        if ticker in self.factory.all_books:
            return [True, self.factory.all_books[ticker]]
        else:
            # Just return an empty book if there's no book for this market
            log.err("No book for %s" % ticker)
            return [True, {'contract': ticker, 'bids': [], 'asks': []}]

    @exportRpc
    def make_account(self, username, password, salt, email, nickname):
        """Create a new account

        :param username:
        :param password:
        :param salt:
        :param email:
        :param nickname:
        :returns: Deferred
        """
        validate(username, {"type": "string"})
        validate(password, {"type": "string"})
        validate(salt, {"type": "string"})
        validate(email, {"type": "string"})
        validate(nickname, {"type": "string"})

        if malicious_looking(email) or malicious_looking(nickname) or malicious_looking(username):
            return [False, "malicious looking input"]

        password = salt + ":" + password
        d = self.factory.administrator.make_account(username, password)
        profile = {"email": email, "nickname": nickname}
        self.factory.administrator.change_profile(username, profile)

        def onAccountSuccess(result):
            """

            :param result:
            :returns: list - [True, username]
            """
            return [True, username]

        def onAccountFail(failure):
            """

            :param failure:
            :returns: list - [False, message]
            """
            return [False, failure.value.args]

        return d.addCallbacks(onAccountSuccess, onAccountFail)

    @exportRpc("change_password_token")
    def change_password_token(self, username, new_password_hash, token):
        """Changes a users password.  Leaves salt and two factor untouched.

        :param username:
        :param new_password_hash:
        :param token:
        :returns: Deferred
        """
        validate(username, {"type": "string"})
        validate(new_password_hash, {"type": "string"})
        validate(token, {"type": "string"})
        d = self.factory.administrator.reset_password_hash(username, None, new_password_hash, token=token)

        def onResetSuccess(result):
            """

            :param result: ignored
            :returns: list - [True, None]
            """
            return [True, None]

        def onResetFail(failure):
            """

            :param failure:
            :returns: list - [False, message]
            """
            return [False, failure.value.args]

        return d.addCallbacks(onResetSuccess, onResetFail)

    @exportRpc
    def get_chat_history(self):
        return [True, self.factory.chats[-30:]]



class PepsiColaServerProtocol(WampCraServerProtocol):
    """
    Authenticating WAMP server using WAMP-Challenge-Response-Authentication ("WAMP-CRA").
    """

    def __init__(self):
        """


        """
        self.cookie = ""
        self.username = None
        self.nickname = None
        self.public_handle = None
        # noinspection PyPep8Naming
        self.clientAuthTimeout = 0
        # noinspection PyPep8Naming
        self.clientAuthAllowAnonymous = True
        self.base_uri = config.get("webserver", "base_uri")

    def onConnect(self, request):
        log.msg(str(request.headers))
        return WampCraServerProtocol.onConnect(self, request)

    def connectionMade(self):
        """
        Called when a connection to the protocol is made
        this is the right place to initialize stuff, not __init__()
        """
        WampCraServerProtocol.connectionMade(self)

        # install rate limited call handler
        self.last_call = 0
        self.handlerMapping[self.MESSAGE_TYPEID_CALL] = \
            RateLimitedCallHandler(self, self.prefixes)


    def connectionLost(self, reason):
        """
        triggered when the connection is lost
        :param reason: reason why the connection was lost
        """
        log.msg("Connection was lost: %s" % reason)

    def onSessionOpen(self):
        """
        callback performed when a session is opened,
        it registers the client to a sample pubsub topic
        and overrides some global options
        """

        log.msg("in session open")
        ## register a single, fixed URI as PubSub topic
        self.registerForPubSub(self.base_uri + "/feeds/safe_prices#", pubsub=WampCraServerProtocol.SUBSCRIBE,
                               prefixMatch=True)
        self.registerForPubSub(self.base_uri + "/feeds/trades#", pubsub=WampCraServerProtocol.SUBSCRIBE,
                               prefixMatch=True)
        self.registerForPubSub(self.base_uri + "/feeds/book#", pubsub=WampCraServerProtocol.SUBSCRIBE,
                               prefixMatch=True)
        self.registerForPubSub(self.base_uri + "/feeds/ohlcv#", pubsub=WampCraServerProtocol.SUBSCRIBE,
                               prefixMatch=True)

        self.registerForRpc(self.factory.public_interface,
                            self.base_uri + "/rpc/")

        self.registerForPubSub(self.base_uri + "/feeds/chat", pubsub=WampCraServerProtocol.SUBSCRIBE,
                               prefixMatch=True)

        # override global client auth options
        if (self.clientAuthTimeout, self.clientAuthAllowAnonymous) != (0, True):
            # if we never see this warning in the weeks following 02/01
            # we can get rid of this
            log.err("setting clientAuthTimeout and AuthAllowAnonymous in onConnect"
                            "is useless, __init__ took care of it")

        # noinspection PyPep8Naming
        self.clientAuthTimeout = 0
        # noinspection PyPep8Naming
        self.clientAuthAllowAnonymous = True

        # call base class method
        WampCraServerProtocol.onSessionOpen(self)

    def getAuthPermissions(self, auth_key, auth_extra):
        """
        Gets the permission for a login... for now it's very basic
        :param auth_key: pretty much the login
        :param auth_extra: extra information, like a HMAC
        :returns: Deferred
        """
        print 'getAuthPermissions'

        if auth_key in self.factory.cookies:
            username = self.factory.cookies[auth_key]
        else:
            username = auth_key

        def _cb_perms(result):
            """

            :param result: the permissions for the user
            :returns: dict - the permissions for the user
            """
            if not result:
                raise Exception("User %s not found" % username)
            elif result[0][0]:
                # TODO: SECURITY: This is susceptible to a timing attack.
                def _cb(result):
                    if result:
                        salt, password_hash = result[0][0].split(":")
                        authextra = {'salt': salt, 'keylen': 32, 'iterations': 1000}
                    else:
                        noise = hashlib.md5("super secret" + username + "even more secret")
                        salt = noise.hexdigest()[:8]
                        authextra = {'salt': salt, 'keylen': 32, 'iterations': 1000}

                    # SECURITY: If they know the cookie, it is alright for them to know
                    #   the username. They can log in anyway.
                    return {"authextra": authextra,
                            "permissions": {"pubsub": [], "rpc": [], "username": username}}

                return dbpool.runQuery("SELECT password FROM users WHERE username=%s LIMIT 1",
                                       (username,)).addCallback(_cb)
            else:
                log.err("User %s not permitted to login" % username)
                return {"authextra": "",
                        "permissions": {"pubsub": [], "rpc": [], "username": username}}

        def _cb_error(failure):
            """

            :param failure:
            :returns: dict - fake permissions so we don't leak which users exist or not
            """
            log.err("Unable to get permissions for %s: %s" % (username, failure.value.args))
            return {"authextra": "",
                    "permissions": {"pubsub": [], "rpc": [], "username": username}}


        # Check for login permissions
        d = dbpool.runQuery('SELECT permission_groups.login FROM users, permission_groups WHERE '
                            'users.permission_group_id=permission_groups.id AND users.username=%s',
            (username,))
        d.addCallback(_cb_perms)
        d.addErrback(_cb_error)
        return d


    def getAuthSecret(self, auth_key):
        """
        :param auth_key: the login
        :returns: Deferred
        """

        # check for a saved session
        if auth_key in self.factory.cookies:
            return WampCraProtocol.deriveKey("cookie", {'salt': "cookie", 'keylen': 32, 'iterations': 1})

        def auth_secret_callback(result):
            """

            :param result: results from the db query
            :returns: str, None - the auth secret for the given auth key or None when the auth key does not exist
            :raises: Exception
            """
            if not result:
                raise Exception("No such user: %s" % auth_key)

            salt, secret = result[0][0].split(":")
            totp = result[0][1]

            try:
                otp_num = otp.get_totp(totp)
            except TypeError:
                otp_num = ""
            otp_num = str(otp_num)

            # hash password again but this in mostly unnecessary
            # totp should be safe enough to send over in the clear

            # TODO: extra hashing is being done with a possibly empty salt
            # does this weaken the original derived key?
            if otp_num:
                auth_secret = WampCraProtocol.deriveKey(secret, {'salt': otp_num, 'keylen': 32, 'iterations': 10})
            else:
                auth_secret = secret

            log.msg("returning auth secret: %s" % auth_secret)
            return auth_secret

        def auth_secret_errback(fail=None):
            """

            :param fail:
            :returns: str
            """
            log.err("Error retrieving auth secret: %s" % fail if fail else "Error retrieving auth secret")
            # WampCraProtocol.deriveKey returns base64 encoded data. Since ":"
            # is not in the base64 character set, this can never be a valid
            # password
            return ":" + WampCraProtocol.deriveKey("foobar", {'salt': str(random.random())[2:], 'keylen': 32, 'iterations': 1})

        return dbpool.runQuery(
            'SELECT password, totp FROM users WHERE username=%s LIMIT 1', (auth_key,)
        ).addCallback(auth_secret_callback).addErrback(auth_secret_errback)

    # noinspection PyMethodOverriding
    def onAuthenticated(self, auth_key, perms):
        """
        fired when authentication succeeds, registers user for RPC, save user object in session
        :param auth_key: login
        :param perms: a dictionary describing the permissions associated with this user...
        from getAuthPermissions
        :returns: Deferred
        """

        self.troll_throttle = time.time()

        # based on what pub/sub we're permitted to register for, register to those
        self.registerForPubSubFromPermissions(perms['permissions'])

        ## register RPC endpoints (for now do that manually, keep in sync with perms)
        if perms is not None:
            # noinspection PyTypeChecker
            self.registerForRpc(self, baseUri=self.base_uri + "/rpc/")

        # sets the user in the session...
        # search for a saved session
        self.username = self.factory.cookies.get(auth_key)
        if not self.username:
            log.msg("Normal user login for: %s" % auth_key)
            self.username = auth_key
            uid = str(uuid.uuid4())
            self.factory.cookies[uid] = auth_key
            self.cookie = uid
        else:
            log.msg("Cookie login for: %s" % self.username)
            self.cookie = auth_key

        def _cb(result):
            """Sets the nickname cache

            :param result: results from the db query
            """
            self.nickname = result[0][0] if result[0][0] else "anonymous"
            log.msg("SETTING SELF.NICKNAME TO %s" % self.nickname)


        # moved from onSessionOpen
        # should the registration of these wait till after onAuth?  And should they only be for the specific user?
        #  Pretty sure yes.

        self.registerForPubSub(self.base_uri + "/feeds/orders#" + self.username, pubsub=WampCraServerProtocol.SUBSCRIBE)
        self.registerForPubSub(self.base_uri + "/feeds/fills#" + self.username, pubsub=WampCraServerProtocol.SUBSCRIBE)
        self.registerForPubSub(self.base_uri + "/feeds/transactions#" + self.username, pubsub=WampCraServerProtocol.SUBSCRIBE)
        self.registerHandlerForPubSub(self, baseUri=self.base_uri + "/feeds/")

        return dbpool.runQuery("SELECT nickname FROM users where username=%s LIMIT 1",
                        (self.username,)).addCallback(_cb)

    @exportRpc("request_support_nonce")
    def request_support_nonce(self, type):
        """Get a support nonce so this user can submit a support ticket

        :param type: the type of support ticket to get the nonce for
        :returns: Deferred
        """
        d = self.factory.administrator.request_support_nonce(self.username, type)
        def onRequestSupportSuccess(result):
            """

            :param result: the nonce
            :type result: str
            :returns: list - [True, nonce]
            """
            return [True, result]

        def onRequestSupportFail(failure):
            """

            :param failure:
            :returns: list - [False, message]
            """
            return [False, failure.value.args]

        d.addCallbacks(onRequestSupportSuccess, onRequestSupportFail)
        return d

    @exportRpc("get_permissions")
    def get_permissions(self):
        """Get this user's permissions


        :returns: Deferred
        """
        d = dbpool.runQuery("SELECT permission_groups.name, permission_groups.login, permission_groups.deposit, permission_groups.withdraw, permission_groups.trade "
                            "FROM permission_groups, users WHERE "
                            "users.permission_group_id=permission_groups.id AND users.username=%s",
                            (self.username,))

        def onGetPermsSuccess(result):
            """

            :param result: the permissions for the user
            :type result: dict
            :returns: list - [True, permissions]
            """
            permissions = { 'name': result[0][0],
                            'login': result[0][1],
                            'deposit': result[0][2],
                            'withdraw': result[0][3],
                            'trade': result[0][4]}
            return [True, permissions]

        def onGetPermsFail(failure):
            """

            :param failure:
            :returns: [False, message]
            """
            return [False, failure.value.args]

        d.addCallbacks(onGetPermsSuccess, onGetPermsFail)
        return d

    @exportRpc("get_cookie")
    def get_cookie(self):
        """


        :returns: list - [True, cookie]
        """
        return [True, self.cookie]

    @exportRpc("logout")
    def logout(self):
        """Removes the cookie from the cache, disconnects the user


        """
        if self.cookie in self.factory.cookies:
            del self.factory.cookies[self.cookie]
        self.dropConnection()

    @exportRpc("get_new_two_factor")
    def get_new_two_factor(self):
        """prepares new two factor authentication for an account

        :returns: str
        """
        #new = otp.base64.b32encode(os.urandom(10))
        #self.user.two_factor = new
        #return new
        raise NotImplementedError()

    @exportRpc("disable_two_factor")
    def disable_two_factor(self, confirmation):
        """
        disables two factor authentication for an account
        """
        #secret = self.session.query(models.User).filter_by(username=self.user.username).one().two_factor
        #logging.info('in disable, got secret: %s' % secret)
        #totp = otp.get_totp(secret)
        #if confirmation == totp:
        #    try:
        #        logging.info(self.user)
        #        self.user.two_factor = None
        #        logging.info('should be None till added user')
        #        logging.info(self.user.two_factor)
        #        self.session.add(self.user)
        #        logging.info('added user')
        #        self.session.commit()
        #        logging.info('commited')
        #        return True
        #    except:
        #        self.session.rollBack()
        #        return False
        raise NotImplementedError()


    @exportRpc("register_two_factor")
    def register_two_factor(self, confirmation):
        """
        registers two factor authentication for an account
        :param secret: secret to store
        :param confirmation: trial run of secret
        """
        # sanitize input
        #confirmation_schema = {"type": "number"}
        #validate(confirmation, confirmation_schema)

        #there should be a db query here, or maybe we can just refernce self.user..
        #secret = 'JBSWY3DPEHPK3PXP' # = self.user.two_factor

        #logging.info('two factor in register: %s' % self.user.two_factor)
        #secret = self.user.two_factor
        #test = otp.get_totp(secret)
        #logging.info(test)

        #compare server totp to client side totp:
        #if confirmation == test:
        #    try:
        #        self.session.add(self.user)
        #        self.session.commit()
        #        return True
        #    except Exception as e:
        #        self.session.rollBack()
        #        return False
        #else:
        #    return False
        raise NotImplementedError()

    @exportRpc("make_compropago_deposit")
    def make_compropago_deposit(self, charge):
        """

        :param charge: indication on the payment
        :type charge: dict
        :returns: Deferred, list - if the charge is invalid, return failure w/o needed to go deferred
        """
        validate(charge, {"type": "object", "properties":
            {
                "product_price": {"type": "number", "required": "true"},
                "payment_type": {"type": "string", "required": "true"},
                "send_sms": {"type": "boolean", "required": "true"},
                "currency": {"type": "string", "required": "true"},
                "customer_phone": {"type": "string", "required": "true"},
                "customer_email": {"type": "string", "required": "true"},
                "customer_phone_company": {"type": "string", "required": "true"}
            }
        })
        # Make sure we received an integer qty of MXN
        if charge['product_price'] != int(charge['product_price']):
            return [False, (0, "Invalid MXN quantity sent")]

        if charge['customer_phone_company'] not in compropago.Compropago.phone_companies:
            return [False, (0, "Invalid phone company")]

        if charge['payment_type'] not in compropago.Compropago.payment_types:
            return [False, (0, "Invalid payment type")]

        phone_company = charge['customer_phone_company']
        charge['customer_phone'] = filter(str.isdigit, charge['customer_phone'])

        del charge['customer_phone_company']

        charge['customer_name'] = self.username
        charge['product_name'] = 'bitcoins'
        charge['product_id'] = ''
        charge['image_url'] = ''

        c = compropago.Charge(**charge)
        d = self.factory.compropago.create_bill(c)

        def process_bill(bill):
            """Process a bill that was created

            :param bill:
            :returns: Deferred
            """

            def save_bill(txn):
                """Save a cgo bill and return the instructions

                :param txn:
                :returns: list - [True, instructions]
                """
                txn.execute("SELECT id FROM contracts WHERE ticker=%s", ('MXN', ))
                res = txn.fetchall()
                if not res:
                    log.err("Unable to find MXN contract!")
                    return [False, "Internal error: No MXN contract"]

                contract_id = res[0][0]
                payment_id = bill['payment_id']
                instructions = bill['payment_instructions']
                address = 'compropago_%s' % payment_id
                if charge['send_sms']:
                    self.compropago.send_sms(payment_id, charge['customer_phone'], phone_company)
                txn.execute("INSERT INTO addresses (username,address,accounted_for,active,contract_id) VALUES (%s,%s,%s,%s,%d)", (self.username, address, 0, True, contract_id))
                # do not return bill as the payment_id should remain private to us
                return [True, instructions]

            return dbpool.runInteraction(save_bill)

        def error(failure):
            """

            :param failure:
            :returns: list - [False, message]
            """
            log.err("Could not create bill: %s" % str(failure))
            # TODO: set a correct error code
            return [False, (0, "We are unable to connect to Compropago. Please try again later. We are sorry for the inconvenience.")]

        d.addCallback(process_bill)
        d.addErrback(error)
        return d

    @exportRpc("get_transaction_history")
    def get_transaction_history(self, from_timestamp=None, to_timestamp=None):

        """

        :param from_timestamp:
        :param to_timestamp:
        :returns: Deferred
        """

        if from_timestamp is None:
            from_timestamp = dt_to_timestamp(datetime.datetime.utcnow() -
                                                             datetime.timedelta(days=30))

        if to_timestamp is None:
            to_timestamp = dt_to_timestamp(datetime.datetime.utcnow())

        def _gotBalances(result):
            balances = collections.defaultdict(int)
            for row in result:
                balances[row[0]] = int(row[1])


            def _gotTransactions(result):
                """

                :param result:
                :type result: list
                :returns: list - [True, list of transactions]
                """
                transactions = []
                for row in result:
                    balances[row[0]] += row[2]
                    quantity = abs(row[2])

                    # Here we assume that the user is a Liability user
                    if row[2] < 0:
                        direction = 'debit'
                    else:
                        direction = 'credit'

                    transactions.append({'contract': row[0],
                                     'timestamp': dt_to_timestamp(row[1]),
                                     'quantity': quantity,
                                     'type': row[3],
                                     'direction': direction,
                                     'balance': balances[row[0]],
                                     'note': row[4]})


                return [True, transactions]


            d = dbpool.runQuery("SELECT contracts.ticker, journal.timestamp, posting.quantity, journal.type, posting.note "
                                "FROM posting, journal, contracts WHERE posting.journal_id=journal.id AND "
                                "posting.username=%s AND journal.timestamp>=%s AND journal.timestamp<=%s "
                                "AND posting.contract_id=contracts.id ORDER BY journal.timestamp",
                (self.username, timestamp_to_dt(from_timestamp), timestamp_to_dt(to_timestamp)))
            d.addCallback(_gotTransactions)
            d.addErrback(_cb_error)
            return d

        def _cb_error(failure):
            """

            :param failure:
            :returns: list - [False, message]
            """
            return [False, failure.value.args]


        d = dbpool.runQuery("SELECT contracts.ticker, SUM(posting.quantity) FROM posting, journal, contracts "
                            "WHERE posting.journal_id=journal.id AND posting.username=%s AND journal.timestamp<%s "
                            "AND posting.contract_id=contracts.id GROUP BY contracts.ticker",
            (self.username, timestamp_to_dt(from_timestamp)))


        d.addCallback(_gotBalances)
        d.addErrback(_cb_error)
        return d

    @exportRpc("get_new_address")
    def get_new_address(self, ticker):
        """
        assigns a new deposit address to a user and returns the address
        :param ticker:
        :type ticker: str
        :returns: Deferred
        """
        validate(ticker, {"type": "string"})
        ticker = ticker[:MAX_TICKER_LENGTH]

        def onError(failure):
            return [False, failure.value.args]

        def onNewAddress(address):
            return [True, address]

        d = self.factory.cashier.get_new_address(self.username, ticker)
        d.addCallbacks(onNewAddress, onError)
        return d


    @exportRpc("get_current_address")
    def get_current_address(self, ticker):
        """
        RPC call to obtain the current address associated with a particular user
        :param ticker:
        :returns: Deferred
        """
        validate(ticker, {"type": "string"})
        ticker = ticker[:MAX_TICKER_LENGTH]

        def onError(failure):
            return [False, failure.value.args]

        def onCurrentAddress(address):
            return [True, address]

        d = self.factory.cashier.get_current_address(self.username, ticker)
        d.addCallbacks(onCurrentAddress, onError)
        return d

    @exportRpc("get_deposit_instructions")
    def get_deposit_instructions(self, ticker):
        validate(ticker, {"type": "string"})
        ticker = ticker[:MAX_TICKER_LENGTH]

        def onError(failure):
            return [False, failure.value.args]

        def onDepositInstructions(instructions):
            return [True, instructions]

        d = self.factory.cashier.get_deposit_instructions(ticker)
        d.addCallbacks(onDepositInstructions, onError)
        return d

    @exportRpc("request_withdrawal")
    def request_withdrawal(self, ticker, amount, address):
        """
        Makes a note in the database that a withdrawal needs to be processed
        :param ticker: the currency to process the withdrawal in
        :param amount: the amount of money to withdraw
        :param address: the address to which the withdrawn money is to be sent
        :returns: bool, Deferred - if an invalid amount, just return False, otherwise return a deferred
        """
        validate(ticker, {"type": "string"})
        validate(address, {"type": "string"})
        validate(amount, {"type": "number"})
        amount = int(amount)

        if amount <= 0:
            return [False, (0, "Invalid withdrawal amount")]

        def onRequestWithdrawalSuccess(result):
            return [True, result]

        def onRequestWithdrawalFail(failure):
            return [False, failure.value.args]

        d = self.factory.accountant.request_withdrawal(self.username, ticker, amount, address)
        d.addCallbacks(onRequestWithdrawalSuccess, onRequestWithdrawalFail)

        return d

    @exportRpc("get_positions")
    def get_positions(self):
        """
        Returns the user's positions
        :returns: Deferred
        """

        def _cb(result):
            """

            :param result:
            :returns: list - [True, dict of positions]
            """
            return [True, {x[1]: {"contract": x[1],
                                  "position": x[2],
                                  "reference_price": x[3]
            }
                           for x in result}]

        return dbpool.runQuery(
            "SELECT contracts.id, contracts.ticker, positions.position, positions.reference_price "
            "FROM positions, contracts WHERE positions.contract_id = contracts.id AND positions.username=%s",
            (self.username,)).addCallback(_cb)

    @exportRpc("get_profile")
    def get_profile(self):
        """


        :returns: Deferred
        """

        def _cb(result):
            """

            :param result:
            :returns: list - [success, dict or message]
            """
            if not result:
                return [False, (0, "get profile failed")]


            return [True, {'nickname': result[0][0], 'email': result[0][1], 'audit_secret': result[0][2]}]

        return dbpool.runQuery("SELECT nickname, email, audit_secret FROM users WHERE username=%s", (self.username,)).addCallback(
            _cb)

    @exportRpc("change_profile")
    def change_profile(self, email, nickname):
        """
        Updates a user's nickname and email. Can't change
        the user's login, that is fixed.
        :param email:
        :param nickname:
        :returns: Deferred
        """

        # sanitize
        # TODO: make sure email is an actual email
        # TODO: make sure nickname is appropriate
        validate(email, {"type": "string"})
        validate(nickname, {"type": "string"})

        if malicious_looking(email) or malicious_looking(nickname):
            return [False, "malicious looking input"]

        profile = {"email": email, "nickname": nickname}
        d = self.factory.administrator.change_profile(self.username, profile)

        def onProfileSuccess(result):
            """

            :param result: ignored
            :returns: list - [True, dict of profile]
            """
            return self.get_profile()

        def onProfileFail(failure):
            """

            :param failure:
            :returns: list - [False, message]
            """
            return [False, failure.value.args]

        return d.addCallbacks(onProfileSuccess, onProfileFail)

    @exportRpc("change_password")
    def change_password(self, old_password_hash, new_password_hash):
        """
        Changes a users password.  Leaves salt and two factor untouched.
        :param old_password_hash: current password
        :param new_password_hash: new password
        :returns: Deferred
        """
        validate(old_password_hash, {"type": "string"})
        validate(new_password_hash, {"type": "string"})
        d = self.factory.administrator.reset_password_hash(self.username, old_password_hash, new_password_hash)

        def onResetSuccess(result):
            """

            :param result: ignored
            :returns: list - [True, None]
            """
            return [True, None]

        def onResetFail(failure):
            """

            :param failure:
            :returns: list - [False, message]
            """
            return [False, failure.value.args]

        return d.addCallbacks(onResetSuccess, onResetFail)

    @exportRpc("get_open_orders")
    def get_open_orders(self):
        """gets open orders

        :returns: Deferred
        """

        def _cb(result):
            """

            :param result:
            :returns: list - [True, dict of orders, indexed by id]
            """
            return [True, {r[6]: {'contract': r[0], 'price': r[1], 'quantity': r[2], 'quantity_left': r[3],
                           'timestamp': dt_to_timestamp(r[4]), 'side': r[5], 'id': r[6], 'is_cancelled': False} for r in result}]

        return dbpool.runQuery('SELECT contracts.ticker, orders.price, orders.quantity, orders.quantity_left, '
                               'orders.timestamp, orders.side, orders.id FROM orders, contracts '
                               'WHERE orders.contract_id=contracts.id AND orders.username=%s '
                               'AND orders.quantity_left > 0 '
                               'AND orders.accepted=TRUE AND orders.is_cancelled=FALSE', (self.username,)).addCallback(
            _cb)


    @exportRpc("place_order")
    def place_order(self, order):
        """
        Places an order on the engine
        :param order: the order to be placed
        :type order: dict
        :returns: Deferred
        """
        # sanitize inputs:
        try:
            validate(order,
                     {"type": "object", "properties": {
                         "contract": {"type": "string"},
                         "price": {"type": "number"},
                         "quantity": {"type": "number"},
                         "side": {"type": "string"},
                         "quantity_left": {"type": ["number", "null"]},
                         "id": {"type": "number"},
                         "timestamp": {"type": "number"}
                     },
                        "required": ["contract", "price", "quantity", "side"],
                        "additionalProperties": False})
        except Exception as e:
            log.err("Schema validation error: %s" % e)
            raise e
        order['contract'] = order['contract'][:MAX_TICKER_LENGTH]
        order["timestamp"] = dt_to_timestamp(datetime.datetime.utcnow())
        # enforce minimum tick_size for prices:

        def _cb(result):
            """


            :param result: result of checking for the contract
            :returns: Deferred
            :raises: Exception
            """
            if not result:
                raise Exception("Invalid contract ticker.")
            tick_size = result[0][0]
            lot_size = result[0][1]

            order["price"] = int(order["price"])
            order["quantity"] = int(order["quantity"])


            # Check for zero price or quantity
            if order["price"] == 0 or order["quantity"] == 0:
                return [False, (0, "invalid price or quantity")]

            # check tick size and lot size in the accountant, not here

            order['username'] = self.username

            def onSuccess(result):
                return [True, result]

            def onFail(failure):
                return [False, failure.value.args]

            d = self.factory.accountant.place_order(self.username, order)
            d.addCallbacks(onSuccess, onFail)
            return d

        return dbpool.runQuery("SELECT tick_size, lot_size FROM contracts WHERE ticker=%s",
                               (order['contract'],)).addCallback(_cb)

    @exportRpc("get_safe_prices")
    def get_safe_prices(self, array_of_tickers):
        """

        :param array_of_tickers:
        :returns: dict
        """
        validate(array_of_tickers, {"type": "array", "items": {"type": "string"}})
        if array_of_tickers:
            return {ticker: self.factory.safe_prices[ticker] for ticker in array_of_tickers}
        return self.factory.safe_prices

    @exportRpc("cancel_order")
    def cancel_order(self, order_id):
        """
        Cancels a specific order
        :returns: Deferred
        :param order_id: order_id of the order
        """
        # sanitize inputs:
        validate(order_id, {"type": "number"})
        print 'received order_id', order_id
        order_id = int(order_id)
        print 'formatted order_id', order_id
        print 'output from server', str({'cancel_order': {'id': order_id, 'username': self.username}})

        def onSuccess(result):
            return [True, result]

        def onFail(failure):
            return [False, failure.value.args]

        d = self.factory.accountant.cancel_order(self.username, order_id)
        d.addCallbacks(onSuccess, onFail)
        return d

    # so we actually never need to call a "verify captcha" function, the captcha parameters are just passed
    # as part as any other rpc that wants to be captcha protected. Leaving this code as an example though
    # @exportRpc("verify_captcha")
    # def verify_captcha(self, challenge, response):
    #     validate(challenge, {"type": "string"})
    #     validate(response, {"type": "string"})
    #     return self.factory.recaptacha.verify(self.getClientIP(), challenge, response)


    @exportSub("chat")
    def subscribe(self, topic_uri_prefix, topic_uri_suffix):
        """
        Custom topic subscription handler
        :returns: bool
        :param topic_uri_prefix: prefix of the URI
        :param topic_uri_suffix:suffix part, in this case always "chat"
        """
        log.msg("client wants to subscribe to %s%s" % (topic_uri_prefix, topic_uri_suffix))
        if self.username:
            log.msg("he's logged in as %s so we'll let him" % self.username)
            return True
        else:
            log.msg("but he's not logged in, so we won't let him")
            return False

    @exportPub("chat")
    def publish(self, topic_uri_prefix, topic_uri_suffix, event):
        """
        Custom topic publication handler
        :returns: list, None - the message published, if any
        :param topic_uri_prefix: prefix of the URI
        :param topic_uri_suffix: suffix part, in this case always "general"
        :param event: event being published, a json object
        """
        print 'string?', event
        log.msg("client wants to publish to %s%s" % (topic_uri_prefix, topic_uri_suffix))
        if not self.username:
            log.msg("he's not logged in though, so no")
            return None
        else:
            log.msg("he's logged as %s in so that's cool" % self.username)
            if type(event) not in [str, unicode]:
                log.err("but the event type isn't a string, that's way uncool so no")
                return None
            elif len(event) > 0:
                message = cgi.escape(event)
                if len(message) > 128:
                    message = message[:128] + u"[\u2026]"
                # TODO: enable this
                # chat_log.info('%s:%s' % (self.nickname, message))

                #pause message rate if necessary
                time_span = time.time() - self.troll_throttle
                print time_span
                if time_span < 3:
                    time.sleep(time_span)
                    print 'sleeping'
                self.troll_throttle = time.time()
                print self.troll_throttle
                msg = [cgi.escape(self.nickname), message]
                self.factory.chats.append(msg)
                if len(self.factory.chats) > 50:
                    self.factory.chats = self.factory.chats[-50:]
                log.msg(self.factory.chats)
                return msg



class EngineExport:
    def __init__(self, webserver):
        self.webserver = webserver

    @export
    def book(self, ticker, book):
        self.webserver.all_books[ticker] = book
        self.webserver.dispatch(
            self.webserver.base_uri + "/feeds/book#%s" % ticker, book)

    @export
    def safe_prices(self, ticker, price):
        self.webserver.safe_prices[ticker] = price
        self.webserver.dispatch(
            self.webserver.base_uri + "/feeds/safe_prices#%s" % ticker, price)

class AccountantExport:
    def __init__(self, webserver):
        self.webserver = webserver

    @export
    def fill(self, user, trade):
        self.webserver.dispatch(
            self.webserver.base_uri + "/feeds/fills#%s" % user, trade)

    @export
    def transaction(self, user, transaction):
        self.webserver.dispatch(
            self.webserver.base_uri + "/feeds/transactions#%s" % user, transaction)

    @export
    def trade(self, ticker, trade):
        self.webserver.dispatch(
            self.webserver.base_uri + "/feeds/trades#%s" % ticker, trade)
        self.webserver.trade_history[ticker].append(trade)
        for period in ["day", "hour", "minute"]:
            self.webserver.update_ohlcv(trade, period=period, update_feed=True)

    @export
    def order(self, username, order):
        self.webserver.dispatch(
            self.webserver.base_uri + "/feeds/orders#%s" % username, order)


class PepsiColaServerFactory(WampServerFactory):
    """
    Simple broadcast server broadcasting any message it receives to all
    currently connected clients.
    """

    # noinspection PyPep8Naming
    def __init__(self, url, base_uri, accountant, administrator, cashier, compropago,
                 recaptcha, debugWamp=False, debugCodePaths=False, exchange_info={}):
        """

        :param url:
        :type url: str
        :param base_uri:
        :type base_uri: str
        :param debugWamp:
        :type debugWamp: bool
        :param debugCodePaths:
        :type debugCodePaths: bool
        """
        WampServerFactory.__init__(
            self, url, debugWamp=debugWamp, debugCodePaths=debugCodePaths)

        self.base_uri = base_uri

        self.all_books = {}
        self.safe_prices = {}
        self.markets = {}
        self.trade_history = collections.defaultdict(list)
        self.ohlcv_history = collections.defaultdict(dict)
        self.chats = []
        self.cookies = {}

        self.public_interface = PublicInterface(self)

        self.accountant = accountant
        self.administrator = administrator
        self.cashier = cashier

        self.compropago = compropago
        self.recaptcha = recaptcha
        self.exchange_info = exchange_info


    def update_ohlcv(self, trade, period="day", update_feed=False):
        """

        :param trade:
        :param period:
        """
        period_map = {'minute': 60,
                      'hour': 3600,
                      'day': 3600 * 24}
        period_seconds = int(period_map[period])
        period_micros = int(period_seconds * 1000000)
        ticker = trade['contract']
        if period not in self.ohlcv_history[ticker]:
            self.ohlcv_history[ticker][period] = {}

        start_period = int(trade['timestamp'] / period_micros) * period_micros
        if start_period not in self.ohlcv_history[ticker][period]:
            # This is a new period, so send out the prior period
            prior_period = start_period - period_micros
            if update_feed and prior_period in self.ohlcv_history[ticker][period]:
                prior_ohlcv = self.ohlcv_history[ticker][period][prior_period]
                self.dispatch(self.base_uri + "/feeds/ohlcv#%s" % ticker, prior_ohlcv)

            self.ohlcv_history[ticker][period][start_period] = {'period': period,
                                       'contract': ticker,
                                       'open': trade['price'],
                                       'low': trade['price'],
                                       'high': trade['price'],
                                       'close': trade['price'],
                                       'volume': trade['quantity'],
                                       'vwap': trade['price'],
                                       'open_timestamp': start_period,
                                       'close_timestamp': start_period + period_micros - 1}
        else:
            self.ohlcv_history[ticker][period][start_period]['low'] = min(trade['price'], self.ohlcv_history[ticker][period][start_period]['low'])
            self.ohlcv_history[ticker][period][start_period]['high'] = max(trade['price'], self.ohlcv_history[ticker][period][start_period]['high'])
            self.ohlcv_history[ticker][period][start_period]['close'] = trade['price']
            self.ohlcv_history[ticker][period][start_period]['vwap'] = ( self.ohlcv_history[ticker][period][start_period]['vwap'] * \
                                            self.ohlcv_history[ticker][period][start_period]['volume'] + trade['quantity'] * trade['price'] ) / \
                                          ( self.ohlcv_history[ticker][period][start_period]['volume'] + trade['quantity'] )
            self.ohlcv_history[ticker][period][start_period]['volume'] += trade['quantity']

class TicketServer(Resource):
    isLeaf = True
    def __init__(self, administrator, zendesk, blockscore=None):
        self.administrator = administrator
        self.zendesk = zendesk
        self.blockscore = blockscore

        Resource.__init__(self)

    def getChild(self, path, request):
        """

        :param path:
        :param request:
        :returns: Resource
        """
        return self

    def log(self, request):
        """Log a request

        :param request:
        """
        log.msg(request.getClientIP(),
                     request.method,
                     request.uri,
                     request.clientproto,
                     request.code,
                     request.sentLength or "-",
                     request.getHeader("referer") or "-",
                     request.getHeader("user-agent") or "-",
                     request.getHeader("authorization") or "-")

    def create_kyc_ticket(self, request):
        """

        :param request:
        :type request: IRequest
        :returns: Deferred
        """
        headers = request.getAllHeaders()
        fields = cgi.FieldStorage(
                    fp = request.content,
                    headers = headers,
                    environ= {'REQUEST_METHOD': request.method,
                              'CONTENT_TYPE': headers['content-type'] }
                    )

        def onBlockScore(blockscore_result):
            def onFail(failure):
                """

                :param failure:
                """
                log.err("unable to create support ticket: %s" % str(failure.value.args))
                request.write("Failure: %s" % str(failure.value.args))
                request.finish()

            def onCheckSuccess(user):
                attachments = []
                file_fields = fields['file']
                if not isinstance(file_fields, list):
                    file_fields = [file_fields]

                for field in file_fields:
                    attachments.append({"filename": field.filename,
                                        "data": field.value,
                                        "type": field.type})

                try:
                    data = {'blockscore_result': blockscore_result,
                           'input_data': json.loads(fields['data'].value)}
                except ValueError:
                    data = {'error': "Invalid json data: %s" % fields['data'].value }

                def onCreateTicketSuccess(ticket_number):
                    def onRegisterTicketSuccess(result):
                        log.msg("Ticket registered successfully")
                        request.write("OK")
                        request.finish()

                    log.msg("Ticket created: %s" % ticket_number)
                    d3 = self.administrator.register_support_ticket(username, nonce, 'Compliance', str(ticket_number))
                    d3.addCallbacks(onRegisterTicketSuccess, onFail)


                d2 = self.zendesk.create_ticket(user, "New compliance document submission",
                                                json.dumps(data, indent=4,
                                                           separators=(',', ': ')), attachments)
                d2.addCallbacks(onCreateTicketSuccess, onFail)

            username = fields['username'].value
            nonce = fields['nonce'].value
            d = self.administrator.check_support_nonce(username, nonce, 'Compliance')
            d.addCallbacks(onCheckSuccess, onFail)
            return d


        if self.blockscore is not None:
            input_data = json.loads(fields['data'].value)

            input_values = {'date_of_birth': input_data['date_of_birth'],
                            'identification': {'passport': input_data['passport_number']},
                            'name': {'first': input_data['first_name'],
                                     'middle': input_data['middle_name'],
                                     'last': input_data['last_name']},
                            'address': {'street1': input_data['address1'],
                                        'street2': input_data['address2'],
                                        'city': input_data['city'],
                                        'state': input_data['state'],
                                        'postal_code': input_data['postal_code'],
                                        'country_code': input_data['country_code']}
            }
            d = self.blockscore.verify(input_values)
            d.addBoth(onBlockScore)
        else:
            d = onBlockScore({})

        return NOT_DONE_YET

    def render(self, request):
        """

        :param request:
        :returns: NOT_DONE_YET, None
        """
        self.log(request)
        if request.postpath[0] == 'create_kyc_ticket':
            return self.create_kyc_ticket(request)
        else:
            return None


if __name__ == '__main__':
    log.startLogging(sys.stdout)
    #chat_log = logging.getLogger('chat_log')

    #chat_log_handler = logging.FileHandler(filename=config.get("webserver", "chat_log"))
    #chat_log_formatter = logging.Formatter('%(asctime)s %(message)s')
    #chat_log_handler.setFormatter(chat_log_formatter)
    #chat_log.addHandler(chat_log_handler)

    if config.getboolean("webserver", "debug"):
        log.startLogging(sys.stdout)
        debug = True
    else:
        debug = False

    # IP address to listen on for all publicly visible services
    interface = config.get("webserver", "interface")

    base_uri = config.get("webserver", "base_uri")

    uri = "ws://"
    contextFactory = None
    if config.getboolean("webserver", "ssl"):
        uri = "wss://"
        key = config.get("webserver", "ssl_key")
        cert = config.get("webserver", "ssl_cert")
        cert_chain = config.get("webserver", "ssl_cert_chain")
        contextFactory = ChainedOpenSSLContextFactory(key, cert_chain)

    address = config.get("webserver", "ws_address")
    port = config.getint("webserver", "ws_port")
    uri += "%s:%s/" % (address, port)

    accountant = AccountantProxy("dealer",
            config.get("accountant", "webserver_export"),
            config.getint("accountant", "webserver_export_base_port"))
    administrator = dealer_proxy_async(
            config.get("administrator", "webserver_export"))
    cashier = dealer_proxy_async(config.get("cashier", "webserver_export"))
    compropago = compropago.Compropago(config.get("cashier", "compropago_key"))
    recaptcha = recaptcha.ReCaptcha(
            private_key=config.get("webserver", "recaptcha_private_key"),
            public_key=config.get("webserver", "recaptcha_public_key"))

    exchange_info = { 'name': config.get("webserver", "exchange_name"),
                      'feed_uri': config.get("webserver", "exchange_rss_feed"),
                      'google_analytics': config.get("webserver", "google_analytics")}

    factory = PepsiColaServerFactory(uri, base_uri, accountant, administrator, cashier, compropago, recaptcha,
                                     debugWamp=debug, debugCodePaths=debug, exchange_info=exchange_info)
    factory.protocol = PepsiColaServerProtocol

    engine_export = EngineExport(factory)
    accountant_export = AccountantExport(factory)

    pull_share_async(engine_export,
                         config.get("webserver", "engine_export"))
    pull_share_async(accountant_export,
                         config.get("webserver", "accountant_export"))


    # prevent excessively large messages
    # https://autobahn.ws/python/reference
    factory.setProtocolOptions(maxMessagePayloadSize=1000)

    listenWS(factory, contextFactory, interface=interface)

    watchdog = watchdog(config.get("watchdog", "webserver"))
    administrator =  dealer_proxy_async(config.get("administrator", "ticketserver_export"))
    zendesk = Zendesk(config.get("ticketserver", "zendesk_domain"),
                      config.get("ticketserver", "zendesk_token"),
                      config.get("ticketserver", "zendesk_email"))

    if config.getboolean("ticketserver", "enable_blockscore"):
        blockscore = BlockScore(config.get("ticketserver", "blockscore_api_key"))
    else:
        blockscore = None

    ticket_server =  TicketServer(administrator, zendesk, blockscore=blockscore)

    if config.getboolean("webserver", "www"):
        web_dir = File(config.get("webserver", "www_root"))
        web_dir.putChild('ticket_server', ticket_server)
        web = Site(web_dir)
        port = config.getint("webserver", "www_port")
        if config.getboolean("webserver", "ssl"):
            reactor.listenSSL(port, web, contextFactory, interface=interface)
        else:
            reactor.listenTCP(port, web, interface=interface)
    else:
        base_resource = Resource()
        base_resource.putChild('ticket_server', ticket_server)
        reactor.listenTCP(config.getint("ticketserver", "ticketserver_port"), Site(base_resource),
                                        interface="127.0.0.1")


    reactor.run()

