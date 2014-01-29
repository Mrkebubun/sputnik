#!/usr/bin/env python

"""
Main websocket server, accepts RPC and subscription requests from clients. It's the backbone of the project,
facilitating all communications between the client, the database and the matching engine.
"""

from optparse import OptionParser
import config

parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
                  help="config file", default="../config/sputnik.ini")
(options, args) = parser.parse_args()

if options.filename:
    # noinspection PyUnresolvedReferences
    config.reconfigure(options.filename)

import cgi
import json
import logging
import sys
import datetime
import time
import onetimepass as otp
import hashlib
import uuid

from jsonschema import validate
from twisted.python import log
from twisted.internet import reactor, ssl
from twisted.web.server import Site
from twisted.web.static import File
from autobahn.websocket import listenWS
from autobahn.wamp import exportRpc, \
    WampCraProtocol, \
    WampServerFactory, \
    WampCraServerProtocol, exportSub, exportPub

from OpenSSL import SSL

from txzmq import ZmqFactory, ZmqEndpoint, ZmqPushConnection, ZmqPullConnection

zf = ZmqFactory()

# noinspection PyUnresolvedReferences
if config.get("database", "uri").startswith("postgres"):
    import txpostgres as adbapi
else:
    # noinspection PyPep8Naming
    import twisted.enterprise.adbapi as adbapi

# noinspection PyUnresolvedReferences
dbpool = adbapi.ConnectionPool(config.get("database", "adapter"),
                               user=config.get("database", "username"),
                               database=config.get("database", "dbname"))

MAX_TICKER_LENGTH = 100
RATE_LIMIT = 0.5


def limit(func):
    last_called = [0.0]

    def kick(self, *arg, **kwargs):
        elapsed = time.clock() - last_called[0]

        if elapsed < self.RATE_LIMIT:
            self.count += 1
        else:
            # forgive past floods
            self.count -= 1

        last_called[0] = time.clock()

        if self.count > 100:
            WampCraServerProtocol.dropConnection(self)
            WampCraServerProtocol.connectionLost(self,
                                                 "rate limit exceeded")
        else:
            return func(self, *arg, **kwargs)

    return kick


class PepsiColaServerProtocol(WampCraServerProtocol):
    """
    Authenticating WAMP server using WAMP-Challenge-Response-Authentication ("WAMP-CRA").
    """

    def __init__(self):
        self.cookie = ""
        # rate limit counter
        self.count = 0
        self.username = None
        # noinspection PyPep8Naming
        self.clientAuthTimeout = 0
        # noinspection PyPep8Naming
        self.clientAuthAllowAnonymous = True
        self.troll_throttle = 0

    def connectionMade(self):
        """
        Called when a connection to the protocol is made
        this is the right place to initialize stuff, not __init__()
        """
        WampCraServerProtocol.connectionMade(self)

    def connectionLost(self, reason):
        """
        triggered when the connection is lost
        :param reason: reason why the connection was lost
        """
        logging.info("Connection was lost: %s" % reason)
        self.session.close()

    def onSessionOpen(self):
        """
        callback performed when a session is opened,
        it registers the client to a sample pubsub topic
        and overrides some global options
        """

        logging.info("in session open")
        ## register a single, fixed URI as PubSub topic

        self.registerForPubSub("wss://sputnikmkt.com:8000/safe_prices#", pubsub=WampCraServerProtocol.SUBSCRIBE,
                               prefixMatch=True)
        self.registerForPubSub("wss://sputnikmkt.com:8000/trades#", pubsub=WampCraServerProtocol.SUBSCRIBE,
                               prefixMatch=True)
        self.registerForPubSub("wss://sputnikmkt.com:8000/order_book#", pubsub=WampCraServerProtocol.SUBSCRIBE,
                               prefixMatch=True)
        self.registerForRpc(self, 'wss://sputnikmkt.com:8000/procedures/',
                            methods=[PepsiColaServerProtocol.make_account])
        self.registerForRpc(self, 'wss://sputnikmkt.com:8000/procedures/',
                            methods=[PepsiColaServerProtocol.list_markets])
        self.registerForRpc('wss://sputnikmkt.com:8000/procedures/',
                            methods=[PepsiColaServerProtocol.get_trade_history])
        self.registerForRpc(self, 'wss://sputnikmkt.com:8000/procedures/',
                            methods=[PepsiColaServerProtocol.get_order_book])

        # TODO: move this to onAuthenticated
        self.registerForRpc(self, 'wss://sputnikmkt.com:8000/procedures/',
                            methods=[PepsiColaServerProtocol.get_chat_history])
        self.registerForPubSub("wss://sputnikmkt.com:8000/user/chat", pubsub=WampCraServerProtocol.SUBSCRIBE,
                               prefixMatch=True)

        # override global client auth options
        if (self.clientAuthTimeout, self.clientAuthAllowAnonymous) != (0, True):
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

        def _cb(result):
            if result:
                salt, password_hash = result[0][0].password.split(":")
                authextra = {'salt': salt, 'keylen': 32, 'iterations': 1000}
            else:
                noise = hashlib.md5("super secret" + username + "even more secret")
                salt = noise.hexdigest()[:8]
                authextra = {'salt': salt, 'keylen': 32, 'iterations': 1000}

            # TODO: clean up permissions
            return {'permissions':
                        {'pubsub': [
                            {'uri': 'wss://sputnikmkt.com:8000/safe_price#%s' % 'USD.13.7.31',
                             'prefix': True,
                             'pub': False,
                             'sub': True},
                            {'uri': 'wss://sputnikmkt.com:8000/user/open_orders#%s' % username,
                             'prefix': True,
                             'pub': False,
                             'sub': True},
                            {'uri': 'wss://sputnikmkt.com:8000/user/fills#%s' % username,
                             'prefix': True,
                             'pub': False,
                             'sub': True},
                            {'uri': 'wss://sputnikmkt.com:8000/user/cancels#%s' % username,
                             'prefix': True,
                             'pub': False,
                             'sub': True}], 'rpc': []},
                    'authextra': authextra}

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
            return WampCraProtocol.deriveKey("cookie", {'salt': "cookie", 'keylen': 32, 'iterations': 1000})

        def auth_secret_callback(result):
            if not result:
                raise Exception("No such user: %s" % auth_key)

            salt, secret = result[0][0].password.split(":")
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
            "SELECT password, totp FROM users WHERE username=%s LIMIT 1", (auth_key,)
        ).addCallback(auth_secret_callback).addErrback(auth_secret_errback)

    # noinspection PyMethodOverriding
    def onAuthenticated(self, auth_key, perms):
        """
        fired when authentication succeeds, registers user for RPC, save user object in session
        :param auth_key: login
        :rtype : object
        :param perms: a dictionary describing the permissions associated with this user...          from getAuthPermissions
        """

        self.troll_throttle = time.time()

        # based on what pub/sub we're permitted to register for, register to those
        self.registerForPubSubFromPermissions(perms['permissions'])

        ## register RPC endpoints (for now do that manually, keep in sync with perms)
        if perms is not None:
            # noinspection PyTypeChecker
            self.registerForRpc(self, baseUri="wss://sputnikmkt.com:8000/procedures/")

        # sets the user in the session...
        # search for a saved session
        username = self.factory.cookies.get(auth_key)
        if not username:
            logging.info("Normal user login for: %s" % auth_key)
            self.username = auth_key
            uid = str(uuid.uuid4())
            self.factory.cookies[uid] = auth_key
            self.cookie = uid
        else:
            logging.info("Cookie login for: %s" % username)
            self.username = username

        # moved from onSessionOpen
        # should the registration of these wait till after onAuth?  And should they only be
        # for the specific user?
        #  Pretty sure yes.
        self.registerForPubSub("wss://sputnikmkt.com:8000/user/cancels#" + username,
                               pubsub=WampCraServerProtocol.SUBSCRIBE)
        self.registerForPubSub("wss://sputnikmkt.com:8000/user/fills#" + username,
                               pubsub=WampCraServerProtocol.SUBSCRIBE)
        self.registerForPubSub("wss://sputnikmkt.com:8000/user/open_orders#" + username,
                               pubsub=WampCraServerProtocol.SUBSCRIBE)
        self.registerHandlerForPubSub(self, baseUri="wss://sputnikmkt.com:8000/user/")

    @exportRpc("get_cookie")
    @limit
    def get_cookie(self):
        return self.cookie

    @exportRpc("logout")
    @limit
    def logout(self):
        if self.cookie in self.factory.cookies:
            del self.factory.cookies[self.cookie]
        self.dropConnection()

    @exportRpc("get_new_two_factor")
    @limit
    def get_new_two_factor(self):
        """
        prepares new two factor authentication for an account
        """
        raise NotImplementedError()

    @exportRpc("disable_two_factor")
    @limit
    def disable_two_factor(self, confirmation):
        """
        disables two factor authentication for an account
        """
        raise NotImplementedError()

    @exportRpc("register_two_factor")
    @limit
    def register_two_factor(self, confirmation):
        """
        registers two factor authentication for an account
        :param confirmation: trial run of secret
        """
        raise NotImplementedError()

    @exportRpc("get_trade_history")
    @limit
    def get_trade_history(self, ticker, time_span):
        """
        Gets a list of trades between two dates
        :param ticker: ticker of the contract to get the trade history from
        :param time_span: time span in seconds to look at
        """
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

        #todo implement time_span checks
        return dbpool.runQuery(
            "SELECT trade.timestamp, trade.price, trade.quantity FROM trades, contracts WHERE trades.contract_id=contracts.id AND contracts.ticker=%s" % (
                ticker,))

    @exportRpc("get_new_address")
    @limit
    def get_new_address(self):
        """
        assigns a new deposit address to a user and returns the address
        :return: the new address
        """

        def _get_new_address(txn, username):
            res = txn.query(
                "SELECT id, address FROM addresses WHERE username IS NULL AND active=FALSE ORDER BY id LIMIT 1")
            if not res:
                logging.error("Out of addresses!")
                raise Exception("Out of addresses")

            a_id, a_address = res[0][0], res[0][1]
            txn.execute("UPDATE addresses SET active=FALSE WHERE username=%s", (username,))
            txn.execute("UPDATE addresses SET active=TRUE, username=%s WHERE id=%s",
                        (username, a_id))
            return a_address

        return dbpool.runInteraction(_get_new_address, self.username)

    @exportRpc("get_current_address")
    @limit
    def get_current_address(self):
        """
        RPC call to obtain the current address associated with a particular user
        :return: said current address
        """

        def _cb(result):
            if not result:
                logging.warning(
                    "we did not manage to get the current address associated with a user,"
                    " something's wrong")
                return ""
            else:
                return result[0][0]

        return dbpool.runQuery(
            "SELECT address FROM addresses WHERE username=%s AND active=TRUE ORDER BY id LIMIT 1").addCallback(_cb)

    @exportRpc("withdraw")
    @limit
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

            txn.execute(
                "INSERT INTO withdrawals (username, address, amount, currency_id, entered) VALUES (%(username)s, %(address)s, %(amount)s, %(currency_id)s, %(entered)s )",
                {'username': self.username,
                 'address': withdraw_address,
                 'amount': amount,
                 'currency_id': currency_id,
                 'entered': datetime.datetime.utcnow()})

        dbpool.runInteraction(_withdraw, currency)

    @exportRpc("get_positions")
    @limit
    def get_positions(self):
        """
        Returns the user's positions
        :return: a dictionary representing the user's positions in various tickers
        """

        def _cb(result):
            return {x[0]: {"ticker": x[1],
                           "position": x[2],
                           "reference_price": x[3],
                           "denominator": x[4],
                           "contract_type": x[5],
                           "inverse_quotes": x[6]}
                    for x in result}

        return dbpool.runQuery(
            "SELECT contracts.id, contracts.ticker, positions.position, positions.reference_price, positions.denominator, contracts.contract_type, contracts.inverse_quotes  FROM positions, contracts WHERE positions.contract_id = contracts.id AND positions.username=%s",
            (self.username,)).addCallback(_cb)

    @exportRpc("get_profile")
    @limit
    def get_profile(self):
        def _cb(result):
            if not result:
                return {}
            return {'nickname': result[0][0], 'email': result[0][1]}

        return dbpool.runQuery("SELECT nickname, email FROM users WHERE username=%s", (self.username,)).addCallback(
            _cb)

    @exportRpc("change_profile")
    @limit
    def change_profile(self, new_nick, new_email):
        """
        Updates a user's nickname and email. Can't change
        the user's login, that is fixed.
        """
        # sanitize
        validate(new_nick, {"type": "string"})
        validate(new_email, {"type": "string"})

        def _change(tx, params):
            tx.execute("UPDATE users SET nickname=%s, email=%s WHERE username=%s",
                       (params['new_nick'], params['new_email'], self.username))
        return dbpool.runQuery(_change, {'new_nick': new_nick, 'new_email': new_email})

    @exportRpc("change_password")
    @limit
    def change_password(self, old_password_hash, new_password_hash):
        """
        Changes a users password.  Leaves salt and two factor untouched.
        :param old_password_hash: current password
        :param new_password_hash: new password
        """
        # sanitize
        validate(old_password_hash, {"type": "string"})
        validate(new_password_hash, {"type": "string"})

        if old_password_hash == self.user.password_hash:
            try:
                self.user.password_hash = new_password_hash
                self.session.add(self.user)
                self.session.commit()

                return True
            except Exception as e:
                self.session.rollback()
                return False
        else:
            return False

    @exportRpc("make_account")
    @limit
    def make_account(self, username, password, salt, email):
        """
        creates a new user account based on a name and a password_hash
        :param name: login, username of the user
        :param password: hash of the password
        :param email: email address for the user
        """
        # sanitize
        validate(username, {"type": "string"})
        validate(password, {"type": "string"})
        validate(salt, {"type": "string"})
        validate(email, {"type": "string"})

        def _make(tx, params):
            existing = tx.execute("SELECT id FROM users WHERE username=%s", (params['username'], ))
            if existing:
                return [0, (0, "account already exists")]
            tx.execute("INSERT INTO users (username, password, email) VALUES (%s, %s, %s)",
                       (params['username'], params['password'] + ':' + params['salt'], params['email']))

            for contract in tx.execute("SELECT id FROM contracts WHERE contract_type='cash'"):
                tx.execute("INSERT INTO positions (username, contract_id) VALUES (%s, %s)", (params['username'], contract[0]))

            new_address = tx.execute("SELECT id FROM addresses WHERE active=FALSE AND username IS NULL LIMIT 1")
            if not new_address:
                logging.error("Couldn't create user, out of addresses")
                raise Exception("Out of new addresses!")
            tx.execute("UPDATE addresses SET active=TRUE, username=%s WHERE id=%s", (params['username'], new_address[0][0]))
            return [1, params['username']]

        dbpool.runInteraction(_make, {'username': username, 'password': password, 'salt': salt, 'email': email})


    @exportRpc("list_markets")
    @limit
    def list_markets(self):
        """
        Lists markets available for trading
        :return: a list of markets...
        """
        def _cb(res):
            result = {}
            for r in res:
                result[r[0]] = {"description": r[1],
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

        return dbpool.runQuery("SELECT ticker, description, denominator, contract_type, full_description, tick_size, lot_size, margin_high, margin_low, lot_size FROM contracts").addCallback(_cb)


    @exportRpc("get_chat_history")
    @limit
    def get_chat_history(self):
        """
        rpc use to load the last n lines of the chat box
        :param ticker: ticker of the book we want
        :return: the book
        """
        # rpc call:
        lastThirty = []

        with open(config.get("webserver", "chat_log")) as f:
            for line in f.read().split('\n')[-31:-1]:
                #strip the date and time from the line:
                lastThirty.append(line.split()[2])
        return lastThirty


    @exportRpc("get_order_book")
    @limit
    def get_order_book(self, ticker):
        """
        rpc used to get the cached order book
        :param ticker: ticker of the book we want
        :return: the book
        """
        # sanitize inputs:
        validate(ticker, {"type": "string"})

        # rpc call:
        if ticker in self.factory.all_books:
            return self.factory.all_books[ticker]
        else:
            return []

    @exportRpc("get_open_orders")
    @limit
    def get_open_orders(self):
        """
        gets open orders
        """
        def _cb(result):
            return [{'ticker':r[0], 'price':r[1], 'quantity':r[2], 'side':r[3], 'id':r[4]} for r in result]
        return dbpool.runQuery("SELECT ticker, price, quantity, side, id FROM orders WHERE username=%s AND accepted=TRUE AND is_cancelled=FALSE", (self.username,)).addCallback(_cb)

    @exportRpc("place_order")
    @limit
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
                     "ticker": {"type": "string"},
                     "price": {"type": "number"},
                     "quantity": {"type": "number"},
                     "side": {"type": "number"}
                 }})
        order['ticker'] = order['ticker'][:MAX_TICKER_LENGTH]

        # enforce minimum tick_size for prices:

        def _cb(result):
            if not result:
                raise Exception("Invalid contract ticker.")

            tick_size = result[0][0]
            lot_size = result[0][1]

            # coerce tick size and lot size

            order["price"] = int(order["price"])
            order["quantity"] = int(order["quantity"])
            if order["price"] % tick_size != 0 or order["quantity"] % lot_size != 0 or order["price"] < 0 or order["quantity"] < 0:
                raise Exception("invalid price or quantity")

            order['username'] = self.username
            #TODO (yury can you make this an async rep/req with TXZMQ?)
            self.factory.accountant.push(json.dumps({'place_order': order}))
            self.count += 1
            print 'place_order', self.count

        return dbpool.runQuery("SELECT tick_size, lot_size FROM contracts WHERE ticker=%s", (order['ticker'],)).addCallback(_cb)

    @exportRpc("get_safe_prices")
    @limit
    def get_safe_prices(self, array_of_tickers):
        validate(array_of_tickers, {"type": "array", "items": {"type": "string"}})
        if array_of_tickers:
            return {ticker: self.factory.safe_prices[ticker] for ticker in array_of_tickers}
        return self.factory.safe_prices

    @exportRpc("cancel_order")
    @limit
    def cancel_order(self, order_id):
        """
        Cancels a specific order
        :param order_id: order_id of the order
        """
        # sanitize inputs:
        print 'received order_id', order_id
        validate(order_id, {"type": "number"})
        print 'received order_id', order_id
        order_id = int(order_id)
        print 'formatted order_id', order_id
        print 'output from server', str({'cancel_order': {'id': order_id, 'username': self.user.username}})
        self.factory.accountant.push(json.dumps({'cancel_order': {'id': order_id, 'username': self.user.username}}))
        self.count += 1
        print 'cancel_order', self.count


    @exportSub("chat")
    def subscribe(self, topic_uri_prefix, topic_uri_suffix):
        """
        Custom topic subscription handler
        :param topic_uri_prefix: prefix of the URI
        :param topic_uri_suffix:suffix part, in this case always "chat"
        """
        logging.info("client wants to subscribe to %s%s" % (topic_uri_prefix, topic_uri_suffix))
        if self.user:
            logging.info("he's logged in as %s so we'll let him" % self.user.username)
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
        if not self.user:
            logging.info("he's not logged in though, so no")
            return None
        else:
            logging.info("he's logged as %s in so that's cool" % self.user.username)
            if type(event) not in [str, unicode]:
                logging.warning("but the event type isn't a string, that's way uncool so no")
                return None
            elif len(event) > 0:
                message = cgi.escape(event)
                if len(message) > 128:
                    message = message[:128] + u"[\u2026]"
                chat_log.info('%s:%s' % (self.user.nickname, message))

                #pause message rate if necessary
                time_span = time.time() - self.troll_throttle
                print time_span
                if time_span < 3:
                    time.sleep(time_span)
                    print 'sleeping'
                self.troll_throttle = time.time()
                print self.troll_throttle

                return [cgi.escape(self.user.nickname), message]


class PepsiColaServerFactory(WampServerFactory):
    """
    Simple broadcast server broadcasting any message it receives to all
    currently connected clients.
    """

    # noinspection PyPep8Naming
    def __init__(self, url, debugWamp=False, debugCodePaths=False):
        WampServerFactory.__init__(self, url, debugWamp=debugWamp, debugCodePaths=debugCodePaths)
        self.all_books = {}
        self.safe_prices = {}
        self.cookies = {}
        endpoint = ZmqEndpoint("bind", config.get("webserver", "zmq_address"))
        self.receiver = ZmqPullConnection(zf, endpoint)
        self.receiver.onPull = self.dispatcher

        endpoint = ZmqEndpoint("connect", config.get("accountant", "zmq_address"))
        self.accountant = ZmqPushConnection(zf, endpoint)

    def dispatcher(self, message):
        """
        Dispatches a message on the "simple" pub/sub channel... here for example purposes
        :rtype : NoneType
        :param message: message do be sent
        """

        # TODO: check if message is multipart
        for key, value in json.loads(message[0]).iteritems():
            logging.info("key, value pair for event: %s, %s", json.dumps(key), json.dumps(value))
            if key == 'book_update':
                self.all_books.update(value)
                print "wss://sputnikmkt.com:8000/order_book#%s" % value.keys()[0]
                self.dispatch("wss://sputnikmkt.com:8000/order_book#%s" % value.keys()[0], json.dumps(value))
                #logging.info("Sent:    %", message)

            elif key == 'safe_price':
                self.safe_prices.update(value)
                self.dispatch("wss://sputnikmkt.com:8000/safe_prices#%s" % value.keys()[0], value.values()[0])

            elif key == 'trade':
                self.dispatch("wss://sputnikmkt.com:8000/trades#%s" % value['ticker'], value)
                print 'search'
                print value

            elif key == 'fill':
                self.dispatch("wss://sputnikmkt.com:8000/user/fills#%s" % value[0], value[1])
                print "wss://sputnikmkt.com:8000/user/fills#%s" % value[0], value[1]

            elif key == 'cancel':
                self.dispatch("wss://sputnikmkt.com:8000/user/cancels#%s" % value[0], value[1])
                print "wss://sputnikmkt.com:8000/user/cancels#%s" % value[0], value[1]

            elif key == 'open_orders':
                '''
                note: this should be a private per user channel
                '''
                self.dispatch("wss://sputnikmkt.com:8000/user/open_orders#%s" % value[0], value[1])
                print "wss://sputnikmkt.com:8000/user/open_orders#%s" % value[0], value[1]


class ChainedOpenSSLContextFactory(ssl.DefaultOpenSSLContextFactory):
    def __init__(self, privateKeyFileName, certificateChainFileName,
                 sslmethod=SSL.SSLv23_METHOD):
        """
        @param privateKeyFileName: Name of a file containing a private key
        @param certificateChainFileName: Name of a file containing a certificate chain
        @param sslmethod: The SSL method to use
        """
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

    factory = PepsiColaServerFactory(uri, debugWamp=debug, debugCodePaths=debug)
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

