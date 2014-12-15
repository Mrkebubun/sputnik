from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("trader")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin
from sputnik import util
import datetime

from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import wamp
from autobahn.wamp.types import RegisterOptions


# The schema verify needs to ensure that "username" is not passed in to these
# calls

def check_details(func):
    def wrapper(*args, **kwargs):
        details = kwargs.pop('details')
        username = details.authid
        if username is None:
            raise Exception("details.authid is None")
        kwargs['username'] = username
        func(*args, **kwargs)

    return wrapper

class TraderService(ServicePlugin):
    def __init__(self):
        ServicePlugin.__init__(self)

    def init(self):
        self.accountant = self.require("sputnik.webserver.plugins.backend.accountant.AccountantProxy")
        self.alerts = self.require("sputnik.webserver.plugins.backend.alerts.AlertsProxy")
        self.administrator = self.require("sputnik.webserver.plugins.backend.administrator.AdministratorProxy")
        self.cashier = self.require("sputnik.webserver.plugins.backend.cashier.CashierProxy")
        self.db = self.require("sputnik.webserver.plugins.db.postgres.PostgresDatabase")


    @wamp.register(u"rpc.trader.place_order")
    @inlineCallbacks
    @check_details
    def place_order(self, order, username=None):
        order["timestamp"] = util.dt_to_timestamp(datetime.datetime.utcnow())
        order['username'] = username

        # Check for zero price or quantity
        if order["price"] == 0 or order["quantity"] == 0:
            returnValue([False, "exceptions/webserver/invalid_price_quantity"])

        # check tick size and lot size in the accountant, not here

        try:
            result = yield self.accountant.proxy.place_order(username, order)
            returnValue([True, result])
        except Exception as e:
            returnValue([False, e.args])

    @inlineCallbacks
    @wamp.register(u"rpc.trader.request_support_nonce")
    @check_details
    def request_support_nonce(self, type, username=None):
        """Get a support nonce so this user can submit a support ticket

        :param type: the type of support ticket to get the nonce for
        :returns: Deferred
        """
        try:
            result = yield self.administrator.proxy.request_support_nonce(username, type)
            returnValue([True, result])
        except Exception as e:
            error("exception in request_support_nonce")
            error(e)
            returnValue([False, e.args])

    @inlineCallbacks
    @wamp.register(u"rpc.trader.get_permissions")
    @check_details
    def get_permissions(self, username=None):
        """Get this user's permissions


        :returns: Deferred
        """
        try:
            permissions = yield self.db.get_permissions(username)
            returnValue([True, permissions])
        except Exception as e:
            error("Unable to get permissions")
            error(e)
            returnValue([False, e.args])

    @inlineCallbacks
    @check_details
    @wamp.register(u"rpc.trader.get_cookie")
    # TODO: This should be in the auth? Dunno what to do here - help!
    def get_cookie(self, username=None):
        """


        :returns: list - [True, cookie]
        """
        return [True, self.cookie]

    @inlineCallbacks
    @check_details
    @wamp.register(u"rpc.trader.logout")
    # TODO: This should be in the auth? Dunno what to do here - help!
    def logout(self):
        """Removes the cookie from the cache, disconnects the user


        """
        if self.cookie in self.factory.cookies:
            del self.factory.cookies[self.cookie]
        self.dropConnection()

    @inlineCallbacks
    @check_details
    @wamp.register(u"rpc.trader.get_new_two_factor")
    # TODO: This should be in the auth? Dunno what to do here - help!
    def get_new_two_factor(self, username=None):
        """prepares new two factor authentication for an account

        :returns: str
        """
        #new = otp.base64.b32encode(os.urandom(10))
        #self.user.two_factor = new
        #return new
        raise NotImplementedError()

    @inlineCallbacks
    @check_details
    @wamp.register(u"rpc.trader.disable_two_factor")
    # TODO: This should be in the auth? Dunno what to do here - help!
    def disable_two_factor(self, confirmation, username=None):
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


    @inlineCallbacks
    @check_details
    @wamp.register(u"rpc.trader.register_two_factor")
    # TODO: This should be in the auth? Dunno what to do here - help!
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
    #
    # @exportRpc("make_compropago_deposit")
    # def make_compropago_deposit(self, charge):
    #     """
    #
    #     :param charge: indication on the payment
    #     :type charge: dict
    #     :returns: Deferred, list - if the charge is invalid, return failure w/o needed to go deferred
    #     """
    #     validate(charge, {"type": "object", "properties":
    #         {
    #             "product_price": {"type": "number", "required": "true"},
    #             "payment_type": {"type": "string", "required": "true"},
    #             "send_sms": {"type": "boolean", "required": "true"},
    #             "currency": {"type": "string", "required": "true"},
    #             "customer_phone": {"type": "string", "required": "true"},
    #             "customer_email": {"type": "string", "required": "true"},
    #             "customer_phone_company": {"type": "string", "required": "true"}
    #         }
    #     })
    #     # Make sure we received an integer qty of MXN
    #     if charge['product_price'] != int(charge['product_price']):
    #         return [False, (0, "Invalid MXN quantity sent")]
    #
    #     if charge['customer_phone_company'] not in compropago.Compropago.phone_companies:
    #         return [False, (0, "Invalid phone company")]
    #
    #     if charge['payment_type'] not in compropago.Compropago.payment_types:
    #         return [False, (0, "Invalid payment type")]
    #
    #     phone_company = charge['customer_phone_company']
    #     charge['customer_phone'] = filter(str.isdigit, charge['customer_phone'])
    #
    #     del charge['customer_phone_company']
    #
    #     charge['customer_name'] = self.username
    #     charge['product_name'] = 'bitcoins'
    #     charge['product_id'] = ''
    #     charge['image_url'] = ''
    #
    #     c = compropago.Charge(**charge)
    #     d = self.factory.compropago.create_bill(c)
    #
    #     def process_bill(bill):
    #         """Process a bill that was created
    #
    #         :param bill:
    #         :returns: Deferred
    #         """
    #
    #         def save_bill(txn):
    #             """Save a cgo bill and return the instructions
    #
    #             :param txn:
    #             :returns: list - [True, instructions]
    #             """
    #             txn.execute("SELECT id FROM contracts WHERE ticker=%s", ('MXN', ))
    #             res = txn.fetchall()
    #             if not res:
    #                 log.err("Unable to find MXN contract!")
    #                 return [False, "Internal error: No MXN contract"]
    #
    #             contract_id = res[0][0]
    #             payment_id = bill['payment_id']
    #             instructions = bill['payment_instructions']
    #             address = 'compropago_%s' % payment_id
    #             if charge['send_sms']:
    #                 self.compropago.send_sms(payment_id, charge['customer_phone'], phone_company)
    #             txn.execute("INSERT INTO addresses (username,address,accounted_for,active,contract_id) VALUES (%s,%s,%s,%s,%d)", (self.username, address, 0, True, contract_id))
    #             # do not return bill as the payment_id should remain private to us
    #             return [True, instructions]
    #
    #         return dbpool.runInteraction(save_bill)
    #
    #     def error(failure):
    #         """
    #
    #         :param failure:
    #         :returns: list - [False, message]
    #         """
    #         log.err("Could not create bill: %s" % str(failure))
    #         # TODO: set a correct error code
    #         return [False, (0, "We are unable to connect to Compropago. Please try again later. We are sorry for the inconvenience.")]
    #
    #     d.addCallback(process_bill)
    #     d.addErrback(error)
    #     return d

    @inlineCallbacks
    @check_details
    @wamp.register(u"rpc.trader.get_transaction_history")
    def get_transaction_history(self, from_timestamp=None, to_timestamp=None, username=None):

        """

        :param from_timestamp:
        :param to_timestamp:
        :returns: Deferred
        """

        if from_timestamp is None:
            from_timestamp = util.dt_to_timestamp(datetime.datetime.utcnow() -
                                                             datetime.timedelta(days=30))

        if to_timestamp is None:
            to_timestamp = util.dt_to_timestamp(datetime.datetime.utcnow())

        try:
            history = yield self.db.get_transaction_history(from_timestamp, to_timestamp, username)
            returnValue([True, history])
        except Exception as e:
            error("Unable to get history for %s" % username)
            error(e)
            returnValue([False, e.args])

    @inlineCallbacks
    @check_details
    @wamp.register(u"rpc.trader.get_new_address")
    def get_new_address(self, ticker, username=None):
        """
        assigns a new deposit address to a user and returns the address
        :param ticker:
        :type ticker: str
        :returns: Deferred
        """
        try:
            address = yield self.cashier.proxy.get_new_address(username, ticker)
            returnValue([True, address])
        except Exception as e:
            error("Unable to get new address for %s:%s" % (username, ticker))
            error(e)
            returnValue([False, e.args])

    @inlineCallbacks
    @check_details
    @wamp.register(u"rpc.trader.get_current_address")
    def get_current_address(self, ticker, username=None):
        """
        RPC call to obtain the current address associated with a particular user
        :param ticker:
        :returns: Deferred
        """
        try:
            address = yield self.cashier.proxy.get_current_address(username, ticker)
            returnValue([True, address])
        except Exception as e:
            error("Unable to get current address for %s:%s" % (username, ticker))
            error(e)
            returnValue([False, e.args])

    @inlineCallbacks
    @check_details
    @wamp.register(u"rpc.trader.get_deposit_instructions")
    def get_deposit_instructions(self, ticker, username=None):
        try:
            instructions = yield self.cashier.proxy.get_deposit_instructions(ticker)
            returnValue([True, instructions])
        except Exception as e:
            error("Unable to get deposit instructions for %s" % (ticker))
            error(e)
            returnValue([False, e.args])

    @inlineCallbacks
    @check_details
    @wamp.register(u"rpc.trader.request_withdrawal")
    def request_withdrawal(self, ticker, amount, address, username=None):
        """
        Makes a note in the database that a withdrawal needs to be processed
        :param ticker: the currency to process the withdrawal in
        :param amount: the amount of money to withdraw
        :param address: the address to which the withdrawn money is to be sent
        :returns: bool, Deferred - if an invalid amount, just return False, otherwise return a deferred
        """
        if amount <= 0:
            returnValue([False, ("exceptions/webserver/invalid-withdrawal-amount")])

        try:
            result = yield self.accountant.proxy.request_withdrawal(username, ticker, amount, address)
            returnValue([True, result])
        except Exception as e:
            error("Unable to request withdrawal for %s" % username)
            error(e)
            returnValue([False, e.args])

    @inlineCallbacks
    @check_details
    @wamp.register(u"rpc.trader.get_positions")
    def get_positions(self, username=None):
        """
        Returns the user's positions
        :returns: Deferred
        """
        try:
            positions = yield self.db.get_positions(username)
            returnValue([True, positions])
        except Exception as e:
            error("Unable to get positions for %s" % username)
            error(e)
            returnValue([False, e.args])


    @inlineCallbacks
    @check_details
    @wamp.register(u"rpc.trader.get_profile")
    def get_profile(self, username=None):
        """


        :returns: Deferred
        """
        try:
            profile = yield self.db.get_profile(username)
            returnValue([True, profile])
        except Exception as e:
            error("Unable to get profile for %s" % username)
            error(e)
            returnValue([False, e.args])


    @inlineCallbacks
    @check_details
    @wamp.register(u"rpc.trader.change_profile")
    def change_profile(self, email, nickname, locale=None, username=None):
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
        if util.malicious_looking(email) or util.malicious_looking(nickname):
            returnValue([False, ("malicious looking input")])

        if locale is not None:
            profile =  {"email": email, "nickname": nickname, 'locale': locale}
        else:
            profile = {"email": email, "nickname": nickname}

        try:
            result = yield self.administrator.proxy.change_profile(username, profile)
            profile = yield self.get_profile
            returnValue(profile)
        except Exception as e:
            error("Unable to change profile: %s" % username)
            error(e)
            returnValue([False, e.args])

    @inlineCallbacks
    @check_details
    @wamp.register(u"rpc.trader.change_password")
    def change_password(self, old_password_hash, new_password_hash, username=None):
        """
        Changes a users password.  Leaves salt and two factor untouched.
        :param old_password_hash: current password
        :param new_password_hash: new password
        :returns: Deferred
        """

        try:
            result = yield self.administrator.proxy.reset_password_hash(username, old_password_hash, new_password_hash)
            returnValue([True, None])
        except Exception as e:
            error("Unable to change_password")
            error(e)
            returnValue([False, e.args])

    @inlineCallbacks
    @check_details
    @wamp.register(u"rpc.trader.get_open_orders")
    def get_open_orders(self, username=None):
        """gets open orders

        :returns: Deferred
        """
        try:
            orders = yield self.db.get_open_orders(username)
            returnValue([True, orders])
        except Exception as e:
            error("Unable to get open orders for %s" % username)
            error(e)
            returnValue([False, e.args])

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
                return [False, "exceptions/webserver/invalid_price_quantity"]

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



    @inlineCallbacks
    def onJoin(self, details):
        results = yield self.register(self, options=RegisterOptions(details_arg="details", discloseCaller=True))
        for success, result in results:
            if success:
                log("Registered %s." % self._registrations[result.id].procedure)
            else:
                error("Error registering method: %s." % result.value.args[0])

