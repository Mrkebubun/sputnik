#!/usr/bin/env python

"""
Main websocket server, accepts RPC and subscription requests from clients. It's the backbone of the project,
facilitating all communications between the client, the database and the matching engine.
"""
import cgi
import json
import logging
import sys
import datetime
import time
import onetimepass as otp
import os
import md5

from sqlalchemy import and_
from jsonschema import validate
from twisted.python import log
from twisted.internet import reactor, defer, ssl
from twisted.web.server import Site
from twisted.web.static import File
from autobahn.websocket import listenWS
from autobahn.wamp import exportRpc, \
    WampCraProtocol, \
    WampServerFactory, \
    WampCraServerProtocol, exportSub, exportPub

import zmq
from txzmq import ZmqFactory, ZmqEndpoint, ZmqPushConnection, ZmqPullConnection

zf = ZmqFactory()

import database as db
import models

from optparse import OptionParser
parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
    help="config file", default="../config/sputnik.ini")
(options, args) = parser.parse_args()

from ConfigParser import SafeConfigParser
config = SafeConfigParser()
config.read(options.filename)

RATE_LIMIT = 0.5
MAX_TICKER_LENGTH = 100

class PepsiColaServerProtocol(WampCraServerProtocol):
    """
    Authenticating WAMP server using WAMP-Challenge-Response-Authentication ("WAMP-CRA").
    """
    def __init__(self):
        pass

    # doesn't seem to affect the random salt value... but login doesn't work with this line deleted.
    AUTH_EXTRA = {'salt': "SALT", 'keylen': 32, 'iterations': 1000}
    #PERMISSIONS = {'pubsub': [{'uri': 'https://example.com/simple/',
    #                           'prefix': True,
    #                           'pub': True,
    #                           'sub': True}],
    #               'rpc': [{'uri': 'https://example.com/procedures/place_order',
    #                        'call': True}]}

    def limit(func):
        lastTimeCalled = [0.0]
        def kick(self,*arg, **args):
            elapsed = time.clock() - lastTimeCalled[0]

            if (elapsed < RATE_LIMIT):
                self.count += 1

            lastTimeCalled[0] = time.clock()

            if self.count > 100:
                WampCraServerProtocol.dropConnection(self)
                WampCraServerProtocol.connectionLost(self, 'rate limit exceeded')
            return func(self,*arg, **args)
        return kick

    def connectionMade(self):
        """
        Called when a connection to the protocol is made
        this is the right place to initialize stuff, not __init__()
        """
        self.db_session = db.Session()

        endpoint = ZmqEndpoint("connect",
                config.get("accountant", "zmq_address"))
        self.accountant = ZmqPushConnection(zf, endpoint)

        self.user = None
        WampCraServerProtocol.connectionMade(self)

        # build a dictionary to enforce minimum tick size on orders
        self.tick_sizes = {}
        for contract in self.db_session.query(models.Contract).all():
            self.tick_sizes[contract.ticker] = contract.tick_size

        #limit user trolling
        self.troll_throttle = time.time()
        self.count = 0

    def connectionLost(self, reason):
        """
        triggered when the connection is lost
        :param reason: reason why the connection was lost
        """
        logging.info("Connection was lost: %s" % reason)
        self.db_session.close()

    def onSessionOpen(self):
        """
        callback performed when a session is opened,
        it registers the client to a sample pubsub topic
        and overrides some global options
        """
        logging.info("in session open")
        ## register a single, fixed URI as PubSub topic

        self.registerForPubSub("https://example.com/safe_prices#", pubsub=WampCraServerProtocol.SUBSCRIBE,
                               prefixMatch=True)
        self.registerForPubSub("https://example.com/trades#", pubsub=WampCraServerProtocol.SUBSCRIBE,
                               prefixMatch=True)
        self.registerForPubSub("https://example.com/order_book#", pubsub=WampCraServerProtocol.SUBSCRIBE,
                               prefixMatch=True)
        self.registerForRpc(self, 'https://example.com/procedures/', methods=[PepsiColaServerProtocol.make_account])
        self.registerForRpc(self, 'https://example.com/procedures/', methods=[PepsiColaServerProtocol.list_markets])
        self.registerForRpc(self, 'https://example.com/procedures/', methods=[PepsiColaServerProtocol.get_trade_history])
        self.registerForRpc(self, 'https://example.com/procedures/', methods=[PepsiColaServerProtocol.get_order_book])
        self.registerForRpc(self, 'https://example.com/procedures/', methods=[PepsiColaServerProtocol.get_chat_history])


        self.registerForPubSub("https://example.com/user/chat", pubsub=WampCraServerProtocol.SUBSCRIBE, prefixMatch=True)

        # override global client auth options
        self.clientAuthTimeout = 0
        self.clientAuthAllowAnonymous = True

        # call base class method
        WampCraServerProtocol.onSessionOpen(self)

    def getAuthPermissions(self, authKey, authExtra):
        """
        Gets the permission for a login... for now it's very basic
        :param authKey: pretty much the login
        :param authExtra: extra information, like a HMAC
        :return: the permissions associated with that user
        """
        print 'getAuthPermissions'
        print self.AUTH_EXTRA

        try:
            user = self.db_session.query(models.User).filter_by(nickname=authKey).one()
            user_id = user.id
            self.AUTH_EXTRA['salt'] = user.salt
        except Exception:
            user_id = 0 

            #self.AUTH_EXTRA['salt'] = os.urandom(3).encode('hex')[:-1]
            fakeSalt = md5.md5(authKey)
            self.AUTH_EXTRA['salt'] = fakeSalt.hexdigest()[:5]


        print self.AUTH_EXTRA
        return {'permissions': {'pubsub': [{'uri':'https://example.com/safe_price#%s' %  'USD.13.7.31',
                                            'prefix':True,
                                            'pub':False,
                                            'sub':True},
                                            {'uri':'https://example.com/user/open_orders#%s' % authKey,
                                            'prefix':True,
                                            'pub':False,
                                            'sub':True},
                                            {'uri':'https://example.com/user/fills#%s' % authKey,
                                            'prefix':True,
                                            'pub':False,
                                            'sub':True},
                                            {'uri':'https://example.com/user/cancels#%s' % authKey,
                                            'prefix':True,
                                            'pub':False,
                                            'sub':True} ], 'rpc': []},
                'authextra': self.AUTH_EXTRA}

    def getAuthSecret(self, authKey):
        """
        :param authKey: the login
        :return: the auth secret for the given auth key or None when the auth key
        does not exist
        """
        #todo, understand how this deferred actually works
        #d = defer.Deferred()

        #implement this now:
        #return str(otp.get_totp('JBSWY3DPEHPK3PXP'))+ self.db_session.query(models.User).filter_by(nickname=authKey).one().password_hash
        #do a db mibrations and make obama's otp = secret.  See what happens
        
        try:
            secret = self.db_session.query(models.User).filter_by(nickname=authKey).one().two_factor
            test = otp.get_totp(secret)
        except Exception as e:
            secret = ''     
            test = ''

        try:
            password_hash = str(test) + self.db_session.query(models.User).filter_by(nickname=authKey).one().password_hash
        except Exception as e:
            logging.warning('exceptions, line 107: %s' %e)
            password_hash = ''

        #hash password again to interpolate str(test):
        password_hash = WampCraProtocol.deriveKey(str(password_hash), {'salt': 'onetimepass', 'keylen': 32, 'iterations': 10})

        logging.info("returning password hash %s" % password_hash)
        return password_hash

    # noinspection PyMethodOverriding
    def onAuthenticated(self, authKey, perms):
        """
        fired when authentication succeeds, registers user for RPC, save user object in session
        :param authKey: login
        :rtype : object
        :param perms: a dictionary describing the permissions associated with this user... from getAuthPermissions
        """
        # based on what pub/sub we're permitted to register for, register to those
        self.registerForPubSubFromPermissions(perms['permissions'])

        ## register RPC endpoints (for now do that manually, keep in sync with perms)
        if perms is not None:
            # noinspection PyTypeChecker
            self.registerForRpc(self, baseUri="https://example.com/procedures/")

        # sets the user in the session... I'm not certain it's a 100% safe to store it like this
        #todo: what if the users logs in from different location? To keep an eye on.
        self.user = self.db_session.query(models.User).filter_by(nickname=authKey).one()

        # moved from onSessionOpen
        # should the registration of these wait till after onAuth?  And should they only be for the specifc user?  Pretty sure yes.
        self.registerForPubSub("https://example.com/user/cancels#" + authKey, pubsub=WampCraServerProtocol.SUBSCRIBE)
        self.registerForPubSub("https://example.com/user/fills#" + authKey, pubsub=WampCraServerProtocol.SUBSCRIBE)
        self.registerForPubSub("https://example.com/user/open_orders#" + authKey, pubsub=WampCraServerProtocol.SUBSCRIBE)
        self.registerHandlerForPubSub(self, baseUri="https://example.com/user/")

    @exportRpc("get_new_two_factor")
    @limit
    def get_new_two_factor(self):
        """
        prepares new two factor authentication for an account
        """
        new = otp.base64.b32encode(os.urandom(10))
        self.user.two_factor = new
        return new


    @exportRpc("disable_two_factor")
    @limit
    def disable_two_factor(self,confirmation):
        """
        disables two factor authentication for an account
        """
        secret = self.db_session.query(models.User).filter_by(nickname = self.user.nickname).one().two_factor
        logging.info('in disable, got secret: %s' % secret)
        totp = otp.get_totp(secret)

        if confirmation == totp:
            try:
                logging.info(self.user)
                self.user.two_factor = None
                logging.info('should be None till added user')
                logging.info(self.user.two_factor)
                self.db_session.add(self.user)
                logging.info('added user')
                self.db_session.commit()
                logging.info('commited')
                return True
            except:
                self.db_session.rollBack()
                return False


    @exportRpc("register_two_factor")
    @limit
    def register_two_factor(self, confirmation):
        """
        registers two factor authentication for an account
        :param secret: secret to store
        :param confirmation: trial run of secret
        """
        # sanitize input
        confirmation_schema = {"type": "number"}
        validate(confirmation, confirmation_schema)

        #there should be a db query here, or maybe we can just refernce self.user..
        #secret = 'JBSWY3DPEHPK3PXP' # = self.user.two_factor

        logging.info('two factor in register: %s' % self.user.two_factor)
        secret = self.user.two_factor
        test = otp.get_totp(secret)
        logging.info(test)

        #compare server totp to client side totp:
        if confirmation == test:
            try:
                self.db_session.add(self.user)
                self.db_session.commit()
                return True
            except Exception as e:
                self.db_session.rollBack()
                return False
        else:
            return False    

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

        return [[trade.timestamp.isoformat(), trade.price, trade.quantity] for trade in
                self.db_session.query(models.Trade).join(models.Contract).filter_by(ticker=ticker)] #.filter(and_( models.Trade.timestamp >= from_dt, models.Trade.timestamp < to_dt))]

    @exportRpc("get_new_address")
    @limit
    def get_new_address(self):
        """
        assigns a new deposit address to a user and returns the address
        :return: the new address
        """
        try:
            old_addresses = self.db_session.query(models.Addresses).filter_by(user=self.user).all()
            for addr in old_addresses:
                print addr
                print addr.active
                addr.active = False
                self.db_session.add(addr)

            new_address = self.db_session.query(models.Addresses).filter_by(active=True,user=None).first()
            new_address.active = True
            new_address.user = self.user
            self.db_session.add(new_address)
            self.db_session.commit()
            return new_address.address


        except  Exception as e:
            self.db_session.rollback()
            logging.warning("we did not manage to assign a new address to a user, something's wrong")
            return ""

    @exportRpc("get_current_address")
    @limit
    def get_current_address(self):
        """
        RPC call to obtain the current address associated with a particular user
        :return: said current address
        """
        try:
            current_address = self.db_session.query(models.Addresses).filter_by(user=self.user, active=True).first()
            return current_address.address

        except Exception as e:
            self.db_session.rollback()
            logging.warning("we did not manage to get the current address associated with a user, something's wrong")
            return ""


    @exportRpc("withdraw")
    @limit
    def withdraw(self, currency, address, amount):
        """
        Makes a note in the database that a withdrawal needs to be processed
        :param currency: the currency to process the withdrawal in
        :param address: the address to which the withdrawn money is to be sent
        :param amount: the amount of money to withdraw
        :return: true or false, depending on success
        """
        validate(currency, {"type": "string"})
        validate(address, {"type": "string"})
        validate(amount, {"type": "number"})
        amount = int(amount)




        if amount <= 0:
            return False

        try:
            logging.info('entering withdraw')
            currency = self.db_session.query(models.Contract).filter_by(ticker='BTC').one()
            print currency
            cancellation = models.Withdrawal(self.user, currency, address, amount)
            print cancellation
            self.db_session.add(cancellation)
            self.db_session.commit()
            return True
        except Exception as e:
            self.db_session.rollback()
            return False


    @exportRpc("get_positions")
    @limit
    def get_positions(self):
        """
        Returns the user's positions
        :return: a dictionary representing the user's positions in various tickers
        """
        return {x.contract.id: {"ticker": x.contract.ticker,
                                "position": x.position,
                                "reference_price": x.reference_price,
                                "denominator": x.contract.denominator,
                                "contract_type": x.contract.contract_type}
                for x in self.db_session.query(models.Position).filter_by(user=self.user)}

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

        if old_password_hash == self.user.password_hash :
            try:
                self.user.password_hash = new_password_hash
                self.db_session.add(self.user)
                self.db_session.commit()

                return True
            except Exception as e:
                self.db_session.rollback()
                return False
        else:
            return False

    @exportRpc("make_account")
    @limit
    def make_account(self, name, password_hash, salt, email, bitmessage):
        """
        creates a new user account based on a name and a password_hash
        :param name: login, nickname of the user
        :param password_hash: hash of the password
        :param email: email address for the user
        :param bitmessage: bitmessage address for the user

        """

        # sanitize
        validate(name, {"type": "string"})
        validate(password_hash, {"type": "string"})
        validate(salt, {"type": "string"})
        validate(email, {"type": "string"})
        validate(bitmessage, {"type": "string"})

        try:
            already_existing = self.db_session.query(models.User).filter_by(nickname=name).count() 
            if already_existing>0:
                raise Exception('duplicate')

            user = models.User(password_hash, salt, name, email, bitmessage)
            btc = self.db_session.query(models.Contract).filter_by(ticker='BTC').one()
            btc_pos = models.Position(user, btc)
            btc_pos.reference_price = 0

            new_address = self.db_session.query(models.Addresses).filter_by(active=True, user=None).first()
            new_address.active = True
            new_address.user = user

            self.db_session.add(new_address)
            self.db_session.add(user)
            self.db_session.add(btc_pos)
            self.db_session.commit()
            return True

        except Exception as e:
            self.db_session.rollback()
            return False



    @exportRpc("list_markets")
    @limit
    def list_markets(self):
        """
        Lists markets available for trading
        :return: a list of markets...
        """

        result = {}
        for c in self.db_session.query(models.Contract).filter_by(active=True).filter(
                        models.Contract.contract_type != 'cash'):
            result[c.ticker] = {"description": c.description,
                                "denominator": c.denominator,
                                "contract_type": c.contract_type,
                                "full_description": c.full_description,
                                "tick_size": c.tick_size}

            if c.contract_type == 'futures':
                f_c = self.db_session.query(models.FuturesContract).filter_by(contract=c).one()
                result[c.ticker]['margin_high'] = f_c.margin_high
                result[c.ticker]['margin_low'] = f_c.margin_low

            if c.contract_type == 'prediction':
                p_c = self.db_session.query(models.PredictionContract).filter_by(contract=c).one()
                result[c.ticker]['final_payoff'] = p_c.final_payoff
        return result

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
        return [
            {'ticker': order.contract.ticker,
             'price': order.price,
             'quantity': order.quantity_left,
             'side': order.side,
             'order_id': order.id}
            for order in self.db_session.query(models.Order).filter_by(
                user=self.user).filter(models.Order.quantity_left > 0) if not order.is_cancelled and order.accepted]

    
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

        # enforce minimum tick_size for prices:
        tick_size = self.tick_sizes[order["ticker"]]
        order["price"] = int((order["price"]/tick_size)*tick_size)

        order["quantity"] = int(order["quantity"])
        order['user_id'] = self.user.id
        order['nickname'] = self.user.nickname

        self.accountant.push(json.dumps({'place_order': order}))
        self.count += 1
        print 'place_order', self.count

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
        print 'output from server', str({'cancel_order': {'order_id': order_id, 'user_id': self.user.id, 'nickname':self.user.nickname}})
        self.accountant.push(json.dumps({'cancel_order': {'order_id': order_id, 'user_id': self.user.id, 'nickname':self.user.nickname}}))
        self.count += 1
        print 'cancel_order', self.count


    @exportSub("chat")
    def subscribe(self, topicUriPrefix, topicUriSuffix):
        """
        Custom topic subscription handler
        :param topicUriPrefix: prefix of the URI
        :param topicUriSuffix:suffix part, in this case always "chat"
        """
        logging.info("client wants to subscribe to %s%s" % (topicUriPrefix, topicUriSuffix))
        if self.user:
            logging.info("he's logged in as %s so we'll let him" % self.user.nickname)
            return True
        else:
            logging.info("but he's not logged in, so we won't let him")
            return False

    @exportPub("chat")
    def publish(self, topicUriPrefix, topicUriSuffix, event):
        """
        Custom topic publication handler
        :param topicUriPrefix: prefix of the URI
        :param topicUriSuffix: suffix part, in this case always "general"
        :param event: event being published, a json object
        """
        print 'string?',event
        logging.info("client wants to publish to %s%s" % (topicUriPrefix, topicUriSuffix))
        if not self.user:
            logging.info("he's not logged in though, so no")
            return None
        else:
            logging.info("he's logged as %s in so that's cool" % self.user.nickname)
            if type(event) not in [str, unicode]:
                logging.warning("but the event type isn't a string, that's way uncool so no")
                return None
            elif len(event)>0:
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

    def __init__(self, url, debugWamp=False, debugCodePaths=False):
        WampServerFactory.__init__(self, url, debugWamp=debugWamp, debugCodePaths=debugCodePaths)
        self.all_books = {}
        self.safe_prices = {}
        endpoint = ZmqEndpoint("bind", config.get("webserver", "zmq_address"))
        self.receiver = ZmqPullConnection(zf, endpoint)
        self.receiver.onPull = self.dispatcher

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
                print "https://example.com/order_book#%s"% value.keys()[0] 
                self.dispatch("https://example.com/order_book#%s"% value.keys()[0], json.dumps(value))
                #logging.info("Sent:    %", message)

            elif key == 'safe_price':
                self.safe_prices.update(value)
                self.dispatch("https://example.com/safe_prices#%s" % value.keys()[0], value.values()[0])

            elif key == 'trade':
                self.dispatch("https://example.com/trades#%s" % value['ticker'], value)
                print 'search'
                print value

            elif key == 'fill':
                self.dispatch("https://example.com/user/fills#%s" % value[0], value[1])
                print "https://example.com/user/fills#%s" % value[0], value[1]

            elif key == 'cancel':
                self.dispatch("https://example.com/user/cancels#%s" % value[0], value[1])
                print "https://example.com/user/cancels#%s" % value[0], value[1]

            elif key == 'open_orders':
                '''
                note: this should be a private per user channel
                '''
                self.dispatch("https://example.com/user/open_orders#%s" % value[0], value[1])
                print "https://example.com/user/open_orders#%s" % value[0], value[1]

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
        certificate = config.get("webserver", "ssl_cert")
        contextFactory = ssl.DefaultOpenSSLContextFactory(key, cert)

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
        web_dir = File("../../clients/www")
        web = Site(web_dir)
        port = config.getint("webserver", "www_port")
        if config.getboolean("webserver", "ssl"):
            reactor.listenSSL(port, web, contextFactory, interface=interface)
        else:
            reactor.listenTCP(port, web, interface=interface)

    reactor.run()

