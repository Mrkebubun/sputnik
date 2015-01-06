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

def trader_wrapper(func):
    fn_name = func.__name__
    rpc_call = u"rpc.trader.%s" % fn_name

    @wamp.register(rpc_call)
    @inlineCallbacks
    def wrapper(*args, **kwargs):
        # Make sure username is not passed in
        if 'username' in kwargs:
            raise Exception("'username' passed in over RPC")

        details = kwargs.pop('details')
        username = details.authid
        if username is None:
            raise Exception("details.authid is None")
        kwargs['username'] = username
        try:
            r = yield func(*args, **kwargs)
            returnValue([True, r])
        except Exception as e:
            error("Error calling %s - args=%s, kwargs=%s" % (fn_name, args, kwargs))
            error(e)
            returnValue([False, e.args])

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

    @trader_wrapper
    def place_order(self, order, username=None):
        order["timestamp"] = util.dt_to_timestamp(datetime.datetime.utcnow())
        order['username'] = username

        # Check for zero price or quantity
        if order["price"] == 0 or order["quantity"] == 0:
            returnValue([False, "exceptions/webserver/invalid_price_quantity"])

        # check tick size and lot size in the accountant, not here

        result = yield self.accountant.proxy.place_order(username, order)
        returnValue([True, result])

    @trader_wrapper
    def request_support_nonce(self, type, username=None):
        """Get a support nonce so this user can submit a support ticket

        :param type: the type of support ticket to get the nonce for
        :returns: Deferred
        """
        result = yield self.administrator.proxy.request_support_nonce(username, type)
        returnValue([True, result])


    @trader_wrapper
    def get_permissions(self, username=None):
        """Get this user's permissions


        :returns: Deferred
        """
        permissions = yield self.db.get_permissions(username)
        returnValue([True, permissions])

    @trader_wrapper
    # TODO: This should be in the auth? Dunno what to do here - help!
    def get_new_two_factor(self, username=None):
        """prepares new two factor authentication for an account

        :returns: str
        """
        #new = otp.base64.b32encode(os.urandom(10))
        #self.user.two_factor = new
        #return new
        raise NotImplementedError()

    @trader_wrapper
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


    @trader_wrapper
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

    @trader_wrapper
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


        history = yield self.db.get_transaction_history(from_timestamp, to_timestamp, username)
        returnValue([True, history])

    @trader_wrapper
    def get_new_address(self, ticker, username=None):
        """
        assigns a new deposit address to a user and returns the address
        :param ticker:
        :type ticker: str
        :returns: Deferred
        """

        address = yield self.cashier.proxy.get_new_address(username, ticker)
        returnValue([True, address])

    @trader_wrapper
    def get_current_address(self, ticker, username=None):
        """
        RPC call to obtain the current address associated with a particular user
        :param ticker:
        :returns: Deferred
        """
        address = yield self.cashier.proxy.get_current_address(username, ticker)
        returnValue([True, address])


    @trader_wrapper
    def get_deposit_instructions(self, ticker, username=None):
        instructions = yield self.cashier.proxy.get_deposit_instructions(ticker)
        returnValue([True, instructions])

    @trader_wrapper
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

        result = yield self.accountant.proxy.request_withdrawal(username, ticker, amount, address)
        returnValue([True, result])


    @trader_wrapper
    def get_positions(self, username=None):
        """
        Returns the user's positions
        :returns: Deferred
        """
        positions = yield self.db.get_positions(username)
        returnValue([True, positions])


    @trader_wrapper
    def get_profile(self, username=None):
        """


        :returns: Deferred
        """
        profile = yield self.administrator.proxy.get_profile(username)
        returnValue([True, profile])

    @trader_wrapper
    def change_profile(self, email, nickname, locale=None, username=None):
        """
        Updates a user's nickname and email. Can't change
        the user's login, that is fixed.
        :param email:
        :param nickname:
        :returns: Deferred
        """
        # TODO: make sure email is an actual email
        # TODO: make sure nickname is appropriate
        # (These checks should be in administrator?)
        if util.malicious_looking(email) or util.malicious_looking(nickname):
            returnValue([False, ("malicious looking input")])

        if locale is not None:
            profile =  {"email": email, "nickname": nickname, 'locale': locale}
        else:
            profile = {"email": email, "nickname": nickname}

        result = yield self.administrator.proxy.change_profile(username, profile)
        profile = yield self.get_profile
        returnValue(profile)

    @trader_wrapper
    def change_password(self, old_password_hash, new_password_hash, username=None):
        """
        Changes a users password.  Leaves salt and two factor untouched.
        :param old_password_hash: current password
        :param new_password_hash: new password
        :returns: Deferred
        """


        result = yield self.administrator.proxy.reset_password_hash(username, old_password_hash, new_password_hash)
        returnValue([True, None])


    @trader_wrapper
    def get_open_orders(self, username=None):
        """gets open orders

        :returns: Deferred
        """
        orders = yield self.db.get_open_orders(username)
        returnValue([True, orders])


    @trader_wrapper
    def cancel_order(self, order_id, username=None):
        """
        Cancels a specific order
        :returns: Deferred
        :param order_id: order_id of the order
        """


        def onSuccess(result):
            return [True, result]

        def onFail(failure):
            return [False, failure.value.args]

        result = yield self.accountant.proxy.cancel_order(username, order_id)
        returnValue([True, result])

    @inlineCallbacks
    def register(self, endpoint, procedure = None, options = None):
        results = yield ServicePlugin.register(self, endpoint, procedure, options=RegisterOptions(details_arg="details", discloseCaller=True))
        returnValue(results)
