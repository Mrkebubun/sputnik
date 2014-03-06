#!/usr/bin/env python

"""
Main websocket server, accepts RPC and subscription requests from clients. It's the backbone of the project,
facilitating all communications between the client, the database and the matching engine.
"""

from optparse import OptionParser

import config
import compropago


parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
                  help="config file", default="../config/sputnik.ini")
(options, args) = parser.parse_args()

if options.filename:
    # noinspection PyUnresolvedReferences
    config.reconfigure(options.filename)

import cgi
import logging
import sys
import datetime
import time
import onetimepass as otp
import hashlib
import uuid
import util
from zmq_util import export, pull_share_async, dealer_proxy_async

from jsonschema import validate
from twisted.python import log
from twisted.internet import reactor, task, ssl
from twisted.web.server import Site
from twisted.web.static import File
from autobahn.websocket import listenWS
from autobahn.wamp import exportRpc, \
    WampCraProtocol, \
    WampServerFactory, \
    WampCraServerProtocol, exportSub, exportPub

from autobahn.wamp import CallHandler

from OpenSSL import SSL

from txzmq import ZmqFactory

zf = ZmqFactory()

# noinspection PyUnresolvedReferences
#if config.get("database", "uri").startswith("postgres"):
#    import txpostgres as adbapi
#else:
# noinspection PyPep8Naming
import twisted.enterprise.adbapi as adbapi

# noinspection PyUnresolvedReferences
dbpool = adbapi.ConnectionPool(config.get("database", "adapter"),
                               user=config.get("database", "username"),
                               database=config.get("database", "dbname"))


class RateLimitedCallHandler(CallHandler):
    def _callProcedure(self, call):
        def do_actual_call(actual_call):
            actual_call.proto.last_call = time.time()
            return CallHandler._callProcedure(self, actual_call)

        now = time.time()
        if now - call.proto.last_call < 0.01:
            # try again later
            logging.info("rate limiting...")
            delay = max(0, call.proto.last_call + 0.01 - now)
            d = task.deferLater(reactor, delay, self._callProcedure, call)
            return d
        return do_actual_call(call)


MAX_TICKER_LENGTH = 100


class AdministratorExport:
    pass


class PublicInterface:
    def __init__(self, factory):
        self.factory = factory
        self.factory.chats = []
        self.init()

    def init(self):
        # TODO: clean this up
        def _cb(res):
            result = {}
            for r in res:
                result[r[0]] = {"ticker": r[0],
                                "description": r[1],
                                "denominator": r[2],
                                "contract_type": r[3],
                                "full_description": r[4],
                                "tick_size": r[5],
                                "lot_size": r[6]}

                if result[r[0]]['contract_type'] == 'futures':
                    result[r[0]]['margin_high'] = r[7]
                    result[r[0]]['margin_low'] = r[8]

                if result[r[0]]['contract_type'] == 'prediction':
                    result[r[0]]['final_payoff'] = r[2]
            self.factory.markets = result

        return dbpool.runQuery("SELECT ticker, description, denominator, contract_type, full_description,"
                               "tick_size, lot_size, margin_high, margin_low, lot_size FROM contracts").addCallback(_cb)

    @exportRpc("get_markets")
    def get_markets(self):
        return [True, self.factory.markets]

    @exportRpc("get_trade_history")
    def get_trade_history(self, ticker, time_span=3600):
        """
        Gets a list of trades between two dates
        :param ticker: ticker of the contract to get the trade history from
        :param time_span: time span in seconds to look at
        """
        # TODO: cache this
        # TODO: make sure return format is correct

        # sanitize input
        ticker_schema = {"type": "string"}
        validate(ticker, ticker_schema)
        time_span_schema = {"type": "number"}
        validate(time_span, time_span_schema)

        time_span = int(time_span)
        time_span = min(max(time_span, 0), 365 * 24 * 3600)
        ticker = ticker[:MAX_TICKER_LENGTH]

        to_dt = datetime.datetime.utcnow()
        from_dt = to_dt - datetime.timedelta(seconds=time_span)

        def _cb(result):
            return [True, [{'contract': r[0], 'price': r[2], 'quantity': r[3],
                                  'timestamp': util.dt_to_timestamp(r[1])} for r in result]]

        #todo implement time_span checks
        return dbpool.runQuery(
            "SELECT contracts.ticker, trades.timestamp, trades.price, trades.quantity FROM trades, contracts WHERE "
            "trades.contract_id=contracts.id AND contracts.ticker=%s AND trades.timestamp >= %s "
            "AND trades.timestamp <= %s",
            (ticker, from_dt, to_dt)).addCallback(_cb)

    @exportRpc("get_order_book")
    def get_order_book(self, ticker):
        # sanitize inputs:
        validate(ticker, {"type": "string"})

        # rpc call:
        if ticker in self.factory.all_books:
            return [True, self.factory.all_books[ticker]]
        else:
            return [False, (0, "No book for %s." % ticker)]

    @exportRpc
    def make_account(self, username, password, salt, email):

        # sanitize
        validate(username, {"type": "string"})
        validate(password, {"type": "string"})
        validate(salt, {"type": "string"})
        validate(email, {"type": "string"})

        password = salt + ":" + password
        d = self.factory.administrator.make_account(username, password)
        profile = {"email": email, "nickname": "anonymous"}
        self.factory.administrator.change_profile(username, profile)

        def onAccountSuccess(result):
            return [True, username]

        def onAccountFail(failure):
            return [False, failure.value.args]

        return d.addCallbacks(onAccountSuccess, onAccountFail)


    @exportRpc
    def get_chat_history(self):
        return [True, self.factory.chats[-30:]]



class PepsiColaServerProtocol(WampCraServerProtocol):
    """
    Authenticating WAMP server using WAMP-Challenge-Response-Authentication ("WAMP-CRA").
    """

    def __init__(self):
        self.cookie = ""
        self.username = None
        self.nickname = None
        self.public_handle = None
        # noinspection PyPep8Naming
        self.clientAuthTimeout = 0
        # noinspection PyPep8Naming
        self.clientAuthAllowAnonymous = True
        self.base_uri = config.get("webserver", "base_uri")


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
        logging.info("Connection was lost: %s" % reason)

    def onSessionOpen(self):
        """
        callback performed when a session is opened,
        it registers the client to a sample pubsub topic
        and overrides some global options
        """

        logging.info("in session open")
        ## register a single, fixed URI as PubSub topic
        self.registerForPubSub(self.base_uri + "/feeds/safe_prices#", pubsub=WampCraServerProtocol.SUBSCRIBE,
                               prefixMatch=True)
        self.registerForPubSub(self.base_uri + "/feeds/trades#", pubsub=WampCraServerProtocol.SUBSCRIBE,
                               prefixMatch=True)
        self.registerForPubSub(self.base_uri + "/feeds/book#", pubsub=WampCraServerProtocol.SUBSCRIBE,
                               prefixMatch=True)

        self.registerForRpc(self.factory.public_interface,
                            self.base_uri + "/rpc/")

        self.registerForPubSub(self.base_uri + "/feeds/chat", pubsub=WampCraServerProtocol.SUBSCRIBE,
                               prefixMatch=True)

        # override global client auth options
        if (self.clientAuthTimeout, self.clientAuthAllowAnonymous) != (0, True):
            # if we never see this warning in the weeks following 02/01
            # we can get rid of this
            logging.warning("setting clientAuthTimeout and AuthAllowAnonymous in onConnect"
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
        :return: the permissions associated with that user
        """
        print 'getAuthPermissions'

        if auth_key in self.factory.cookies:
            username = self.factory.cookies[auth_key]
        else:
            username = auth_key

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

    def getAuthSecret(self, auth_key):
        """
        :param auth_key: the login
        :return: the auth secret for the given auth key or None when the auth key
        does not exist
        """

        # check for a saved session
        if auth_key in self.factory.cookies:
            return WampCraProtocol.deriveKey("cookie", {'salt': "cookie", 'keylen': 32, 'iterations': 1})

        def auth_secret_callback(result):
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

            logging.info("returning auth secret: %s" % auth_secret)
            return auth_secret

        def auth_secret_errback(fail=None):
            logging.warning("Error retrieving auth secret: %s" % fail if fail else "Error retrieving auth secret")
            # WampCraProtocol.deriveKey returns base64 encoded data. Since ":"
            # is not in the base64 character set, this can never be a valid
            # password
            #
            # However, if this is discovered, someone can use it to sign
            # messages and authenticate as a nonexistent user
            # TODO: patch autobahn to prevent this without having to leak
            # information about user existence
            return ":0xFA1CDA7A:"

        return dbpool.runQuery(
            'SELECT password, totp FROM users WHERE username=%s LIMIT 1', (auth_key,)
        ).addCallback(auth_secret_callback).addErrback(auth_secret_errback)

    # noinspection PyMethodOverriding
    def onAuthenticated(self, auth_key, perms):
        """
        fired when authentication succeeds, registers user for RPC, save user object in session
        :param auth_key: login
        :rtype : object
        :param perms: a dictionary describing the permissions associated with this user...
        from getAuthPermissions
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
            logging.info("Normal user login for: %s" % auth_key)
            self.username = auth_key
            uid = str(uuid.uuid4())
            self.factory.cookies[uid] = auth_key
            self.cookie = uid
        else:
            logging.info("Cookie login for: %s" % self.username)
            self.cookie = auth_key

        def _cb(result):
            self.nickname = result[0][0] if result[0][0] else "anonymous"
            logging.warning("SETTING SELF.NICKNAME TO %s" % self.nickname)


        # moved from onSessionOpen
        # should the registration of these wait till after onAuth?  And should they only be for the specifc user?
        #  Pretty sure yes.

        self.registerForPubSub(self.base_uri + "/feeds/orders#" + self.username, pubsub=WampCraServerProtocol.SUBSCRIBE)
        self.registerForPubSub(self.base_uri + "/feeds/fills#" + self.username, pubsub=WampCraServerProtocol.SUBSCRIBE)
        self.registerHandlerForPubSub(self, baseUri=self.base_uri + "/feeds/")

        return dbpool.runQuery("SELECT nickname FROM users where username=%s LIMIT 1",
                        (self.username,)).addCallback(_cb)

    @exportRpc("get_cookie")
    def get_cookie(self):
        return [True, self.cookie]

    @exportRpc("logout")
    def logout(self):
        if self.cookie in self.factory.cookies:
            del self.factory.cookies[self.cookie]
        self.dropConnection()

    @exportRpc("get_new_two_factor")
    def get_new_two_factor(self):
        """
        prepares new two factor authentication for an account
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

        @param charge: indication on the payment
        """
        validate(charge, {"type": "object", "properties":
            {
                "product_price": {"type": "number", "required": "true"},
                "payment_type": {"type": "string", "required": "true"},
                "send_sms": {"type": "boolean", "required": "true"},
                "currency": {"type": "string", "required": "true"}
                #todo: add which store
            }
        })
        # Make sure we received an integer qty of MXN
        if charge['product_price'] != int(charge['product_price']):
            return [False, (0, "Invalid MXN quantity sent")]

        def _cb(result):
            denominator = result[0][0]
            charge['product_price'] = charge['product_price'] / denominator
            charge['customer_name'] = self.username
            charge['customer_email'] = ''
            charge['product_name'] = ''
            charge['product_id'] = ''
            charge['image_url'] = ''

            c = compropago.Charge.from_dict(charge)
            bill = self.factory.compropago.create_bill(c) #todo, use deferred in making compropago calls
            return [True, bill]

            # todo: return instructions for the user

        dbpool.runQuery("SELECT denominator FROM contracts WHERE ticker='MXN' LIMIT 1").addCallback(_cb)


    @exportRpc("get_new_address")
    def get_new_address(self, currency):
        """
        assigns a new deposit address to a user and returns the address
        :return: the new address
        """
        validate(currency, {"type": "string"})
        currency = currency[:MAX_TICKER_LENGTH]

        def _get_new_address(txn, username):
            res = txn.query(
                "SELECT addresses.id, addresses.address FROM addresses, contracts WHERE "
                "addresses.username IS NULL AND addresses.active=FALSE AND addresses.currency=contracts.id "
                "AND contracts.ticker=%s"
                " ORDER BY id LIMIT 1", (currency,))
            if not res:
                logging.error("Out of addresses!")
                raise Exception("Out of addresses")

            a_id, a_address = res[0][0], res[0][1]
            txn.execute("UPDATE addresses SET active=FALSE WHERE username=%s", (username,))
            txn.execute("UPDATE addresses SET active=TRUE, username=%s WHERE id=%s",
                        (username, a_id))
            # TODO: Update to new API
            return a_address

        return dbpool.runInteraction(_get_new_address, self.username)

    @exportRpc("get_current_address")
    def get_current_address(self, currency):
        """
        RPC call to obtain the current address associated with a particular user
        :return: said current address
        """
        validate(currency, {"type": "string"})
        currency = currency[:MAX_TICKER_LENGTH]

        def _cb(result):
            if not result:
                logging.warning(
                    "we did not manage to get the current address associated with a user,"
                    " something's wrong")
                return ""
            else:
                return result[0][0]

        # TODO: Update to new API
        return dbpool.runQuery(
            "SELECT addresses.address FROM addresses, contracts WHERE"
            " username=%s AND active=TRUE AND addresses.currency=contracts.id AND contracts.ticker=%s"
            " ORDER BY id LIMIT 1", (self.username, currency)).addCallback(_cb)

    @exportRpc("withdraw")
    def withdraw(self, currency, withdraw_address, amount):
        """
        Makes a note in the database that a withdrawal needs to be processed
        :param currency: the currency to process the withdrawal in
        :param withdraw_address: the address to which the withdrawn money is to be sent
        :param amount: the amount of money to withdraw
        :return: true or false, depending on success
        """
        validate(currency, {"type": "string"})
        validate(withdraw_address, {"type": "string"})
        validate(amount, {"type": "number"})
        amount = int(amount)

        if amount <= 0:
            return False

        def _withdraw(txn, currency):
            logging.info('entering withdraw')
            currency_id = \
                txn.execute("SELECT id FROM contracts WHERE ticker=%s AND contract_type='cash' LIMIT 1", (currency,))[
                    0][0]

            # TODO: Update to new API
            txn.execute(
                "INSERT INTO withdrawals (username, address, amount, currency_id, entered)"
                " VALUES (%(username)s, %(address)s, %(amount)s, %(currency_id)s, %(entered)s )",
                {'username': self.username,
                 'address': withdraw_address,
                 'amount': amount,
                 'currency_id': currency_id,
                 'entered': datetime.datetime.utcnow()})

        return dbpool.runInteraction(_withdraw, currency)


    @exportRpc("get_positions")
    def get_positions(self):
        """
        Returns the user's positions
        :return: a dictionary representing the user's positions in various tickers
        """

        def _cb(result):
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
        def _cb(result):
            if not result:
                return [False, (0, "get profile failed")]
            return [True, {'nickname': result[0][0], 'email': result[0][1]}]

        return dbpool.runQuery("SELECT nickname, email FROM users WHERE username=%s", (self.username,)).addCallback(
            _cb)

    @exportRpc("change_profile")
    def change_profile(self, email, nickname):
        """
        Updates a user's nickname and email. Can't change
        the user's login, that is fixed.
        """

        # sanitize
        # TODO: make sure email is an actual email
        # TODO: make sure nickname is appropriate
        validate(email, {"type": "string"})
        validate(nickname, {"type": "string"})

        profile = {"email": email, "nickname": nickname}
        d = self.factory.administrator.change_profile(self.username, profile)

        def onProfileSuccess(result):
            return [True, profile]

        def onProfileFail(failure):
            return [False, failure.value.args]

        return d.addCallbacks(onProfileSuccess, onProfileFail)

    @exportRpc("change_password")
    def change_password(self, old_password_hash, new_password_hash):
        """
        Changes a users password.  Leaves salt and two factor untouched.
        :param old_password_hash: current password
        :param new_password_hash: new password
        """

        raise NotImplementedError()
        # sanitize
        # validate(old_password_hash, {"type": "string"})
        # validate(new_password_hash, {"type": "string"})
        #
        # if old_password_hash == self.user.password_hash:
        #     try:
        #         self.user.password_hash = new_password_hash
        #         self.session.add(self.user)
        #         self.session.commit()
        #
        #         return {'retval': True}
        #     except Exception as e:
        #         self.session.rollback()
        #         return {'retval': False, 'error': str(e), 'traceback': traceback.format_exc()}
        # else:
        #     return {'retval': False, 'error': "Invalid password", 'traceback': None}


    @exportRpc("get_open_orders")
    def get_open_orders(self):
        """
        gets open orders
        """

        def _cb(result):
            return [True, {r[6]: {'contract': r[0], 'price': r[1], 'quantity': r[2], 'quantity_left': r[3],
                           'timestamp': util.dt_to_timestamp(r[4]), 'side': r[5], 'id': r[6], 'is_cancelled': False} for r in result}]

        return dbpool.runQuery("SELECT contracts.ticker, orders.price, orders.quantity, orders.quantity_left, " +
                               "orders.timestamp, orders.side, orders.id FROM orders, contracts " +
                               "WHERE orders.contract_id=contracts.id AND orders.username=%s " +
                               "AND orders.accepted=TRUE AND orders.is_cancelled=FALSE", (self.username,)).addCallback(
            _cb)


    @exportRpc("place_order")
    def place_order(self, order):
        """
        Places an order on the engine
        :param order: the order to be placed
        :return: the order id, some error?
        :raise: some exception? need to do better error checking
        """
        # sanitize inputs:
        validate(order,
                 {"type": "object", "properties": {
                     "contract": {"type": "string", "required": True},
                     "price": {"type": "number", "required": True},
                     "quantity": {"type": "number", "required": True},
                     "side": {"type": "string", "required": True}
                 }})
        order['contract'] = order['contract'][:MAX_TICKER_LENGTH]

        # enforce minimum tick_size for prices:

        def _cb(result):
            if not result:
                raise Exception("Invalid contract ticker.")
            tick_size = result[0][0]
            lot_size = result[0][1]

            order["price"] = int(order["price"])
            order["quantity"] = int(order["quantity"])

            # Check for zero price or quantity
            if order["price"] == 0 or order["quantity"] == 0:
                return [False, (0, "invalid price or quantity")]

            # coerce tick size and lot size


            if order["price"] % tick_size != 0 \
                    or order["quantity"] % lot_size != 0 \
                    or order["price"] < 0 \
                    or order["quantity"] < 0:
                return [False, (0, "invalid price or quantity")]


            order['username'] = self.username

            return self.factory.accountant.place_order(order)

        return dbpool.runQuery("SELECT tick_size, lot_size FROM contracts WHERE ticker=%s",
                               (order['contract'],)).addCallback(_cb)

    @exportRpc("get_safe_prices")
    def get_safe_prices(self, array_of_tickers):
        validate(array_of_tickers, {"type": "array", "items": {"type": "string"}})
        if array_of_tickers:
            return {ticker: self.factory.safe_prices[ticker] for ticker in array_of_tickers}
        return self.factory.safe_prices

    @exportRpc("cancel_order")
    def cancel_order(self, order_id):
        """
        Cancels a specific order
        :param order_id: order_id of the order
        """
        # sanitize inputs:
        validate(order_id, {"type": "number"})
        print 'received order_id', order_id
        order_id = int(order_id)
        print 'formatted order_id', order_id
        print 'output from server', str({'cancel_order': {'id': order_id, 'username': self.username}})

        return self.factory.accountant.cancel_order(order_id)

    @exportSub("chat")
    def subscribe(self, topic_uri_prefix, topic_uri_suffix):
        """
        Custom topic subscription handler
        :param topic_uri_prefix: prefix of the URI
        :param topic_uri_suffix:suffix part, in this case always "chat"
        """
        logging.info("client wants to subscribe to %s%s" % (topic_uri_prefix, topic_uri_suffix))
        if self.username:
            logging.info("he's logged in as %s so we'll let him" % self.username)
            return True
        else:
            logging.info("but he's not logged in, so we won't let him")
            return False

    @exportPub("chat")
    def publish(self, topic_uri_prefix, topic_uri_suffix, event):
        """
        Custom topic publication handler
        :param topic_uri_prefix: prefix of the URI
        :param topic_uri_suffix: suffix part, in this case always "general"
        :param event: event being published, a json object
        """
        print 'string?', event
        logging.info("client wants to publish to %s%s" % (topic_uri_prefix, topic_uri_suffix))
        if not self.username:
            logging.info("he's not logged in though, so no")
            return None
        else:
            logging.info("he's logged as %s in so that's cool" % self.username)
            if type(event) not in [str, unicode]:
                logging.warning("but the event type isn't a string, that's way uncool so no")
                return None
            elif len(event) > 0:
                message = cgi.escape(event)
                if len(message) > 128:
                    message = message[:128] + u"[\u2026]"
                chat_log.info('%s:%s' % (self.nickname, message))

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
                logging.warning(self.factory.chats)
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

    @export
    def trade(self, ticker, trade):
        self.webserver.dispatch(
            self.webserver.base_uri + "/feeds/trades#%s" % ticker, trade)

    @export
    def fill(self, user, trade):
        self.webserver.dispatch(
            self.webserver.base_uri + "/feeds/fills#%s" % user, trade)

    @export
    def order(self, user, order):
        self.webserver.dispatch(
            self.webserver.base_uri + "/feeds/orders#%s" % user, order)

class PepsiColaServerFactory(WampServerFactory):
    """
    Simple broadcast server broadcasting any message it receives to all
    currently connected clients.
    """

    # noinspection PyPep8Naming
    def __init__(self, url, base_uri, debugWamp=False, debugCodePaths=False):
        WampServerFactory.__init__(
            self, url, debugWamp=debugWamp, debugCodePaths=debugCodePaths)

        self.base_uri = base_uri

        self.all_books = {}
        self.safe_prices = {}
        self.markets = {}
        self.chats = []
        self.cookies = {}
        self.public_interface = PublicInterface(self)

        self.engine_export = EngineExport(self)
        pull_share_async(self.engine_export,
                         config.get("webserver", "engine_export"))
        self.accountant = dealer_proxy_async(
            config.get("accountant", "webserver_export"))
        self.administrator = dealer_proxy_async(
            config.get("administrator", "webserver_export"))

        self.compropago = compropago.Compropago("")


class ChainedOpenSSLContextFactory(ssl.DefaultOpenSSLContextFactory):
    def __init__(self, privateKeyFileName, certificateChainFileName,
                 sslmethod=SSL.SSLv23_METHOD):
        self.privateKeyFileName = privateKeyFileName
        self.certificateChainFileName = certificateChainFileName
        self.sslmethod = sslmethod
        self.cacheContext()

    def cacheContext(self):
        ctx = SSL.Context(self.sslmethod)
        ctx.use_certificate_chain_file(self.certificateChainFileName)
        ctx.use_privatekey_file(self.privateKeyFileName)
        self._context = ctx


if __name__ == '__main__':

    logging.basicConfig(level=logging.DEBUG)
    chat_log = logging.getLogger('chat_log')

    chat_log_handler = logging.FileHandler(filename=config.get("webserver", "chat_log"))
    chat_log_formatter = logging.Formatter('%(asctime)s %(message)s')
    chat_log_handler.setFormatter(chat_log_formatter)
    chat_log.addHandler(chat_log_handler)

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
        # contextFactory = ssl.DefaultOpenSSLContextFactory(key, cert)
        contextFactory = ChainedOpenSSLContextFactory(key, cert_chain)

    address = config.get("webserver", "ws_address")
    port = config.getint("webserver", "ws_port")
    uri += "%s:%s/" % (address, port)

    factory = PepsiColaServerFactory(uri, base_uri, debugWamp=debug, debugCodePaths=debug)
    factory.protocol = PepsiColaServerProtocol

    # prevent excessively large messages
    # https://autobahn.ws/python/reference
    factory.setProtocolOptions(maxMessagePayloadSize=1000)

    listenWS(factory, contextFactory, interface=interface)

    if config.getboolean("webserver", "www"):
        web_dir = File(config.get("webserver", "www_root"))
        web = Site(web_dir)
        port = config.getint("webserver", "www_port")
        if config.getboolean("webserver", "ssl"):
            reactor.listenSSL(port, web, contextFactory, interface=interface)
        else:
            reactor.listenTCP(port, web, interface=interface)

    reactor.run()

