from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("trader")

from sputnik.plugin import PluginException
from sputnik.webserver.plugin import ServicePlugin, authenticated, schema, error_handler
from sputnik.exception import WebserverException
from sputnik import util
import datetime

from twisted.internet.defer import inlineCallbacks, returnValue
from autobahn import wamp
from autobahn.wamp.types import RegisterOptions

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
    @error_handler
    @authenticated
    @schema(u"public/trader.json#place_order")
    def place_order(self, order, username=None):
        order["timestamp"] = util.dt_to_timestamp(datetime.datetime.utcnow())
        order['username'] = username

        # Check for zero price or quantity
        if order["price"] == 0 or order["quantity"] == 0:
            raise WebserverException("exceptions/webserver/invalid_price_quantity")

        # check tick size and lot size in the accountant, not here

        result = yield self.accountant.proxy.place_order(username, order)
        returnValue(result)

    @wamp.register(u"rpc.trader.request_support_nonce")
    @error_handler
    @authenticated
    @schema(u"public/trader.json#request_support_nonce")
    def request_support_nonce(self, type, username=None):
        """Get a support nonce so this user can submit a support ticket

        :param type: the type of support ticket to get the nonce for
        :returns: Deferred
        """
        result = yield self.administrator.proxy.request_support_nonce(username, type)
        returnValue(result)


    @wamp.register(u"rpc.trader.get_permissions")
    @error_handler
    @authenticated
    @schema(u"public/trader.json#get_permissions")
    def get_permissions(self, username=None):
        """Get this user's permissions


        :returns: Deferred
        """
        permissions = yield self.db.get_permissions(username)
        returnValue(permissions)


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

    @wamp.register(u"rpc.trader.get_transaction_history")
    @error_handler
    @authenticated
    @schema(u"public/trader.json#get_transaction_history")
    def get_transaction_history(self, start_timestamp=None, end_timestamp=None, username=None):

        """

        :param from_timestamp:
        :param to_timestamp:
        :returns: Deferred
        """

        if start_timestamp is None:
            start_timestamp = util.dt_to_timestamp(datetime.datetime.utcnow() -
                                                             datetime.timedelta(days=30))

        if end_timestamp is None:
            end_timestamp = util.dt_to_timestamp(datetime.datetime.utcnow())


        history = yield self.db.get_transaction_history(start_timestamp, end_timestamp, username)
        returnValue(history)

    @wamp.register(u"rpc.trader.get_new_address")
    @error_handler
    @authenticated
    @schema(u"public/trader.json#get_new_address")
    def get_new_address(self, ticker, username=None):
        """
        assigns a new deposit address to a user and returns the address
        :param ticker:
        :type ticker: str
        :returns: Deferred
        """

        address = yield self.cashier.proxy.get_new_address(username, ticker)
        returnValue(address)

    @wamp.register(u"rpc.trader.get_current_address")
    @error_handler
    @authenticated
    @schema(u"public/trader.json#get_current_address")
    def get_current_address(self, ticker, username=None):
        """
        RPC call to obtain the current address associated with a particular user
        :param ticker:
        :returns: Deferred
        """
        address = yield self.cashier.proxy.get_current_address(username, ticker)
        returnValue(address)


    @wamp.register(u"rpc.trader.get_deposit_instructions")
    @error_handler
    @authenticated
    @schema(u"public/trader.json#get_deposit_instructions")
    def get_deposit_instructions(self, ticker, username=None):
        instructions = yield self.cashier.proxy.get_deposit_instructions(ticker)
        returnValue(instructions)

    @wamp.register(u"rpc.trader.request_withdrawal")
    @error_handler
    @authenticated
    @schema(u"public/trader.json#request_withdrawal")
    def request_withdrawal(self, ticker, amount, address, username=None):
        """
        Makes a note in the database that a withdrawal needs to be processed
        :param ticker: the currency to process the withdrawal in
        :param amount: the amount of money to withdraw
        :param address: the address to which the withdrawn money is to be sent
        :returns: bool, Deferred - if an invalid amount, just return False, otherwise return a deferred
        """
        if amount <= 0:
            raise WebserverException("exceptions/webserver/invalid-withdrawal-amount")

        result = yield self.accountant.proxy.request_withdrawal(username, ticker, amount, address)
        returnValue(result)

    @wamp.register(u"rpc.trader.get_positions")
    @error_handler
    @authenticated
    @schema(u"public/trader.json#get_positions")
    def get_positions(self, username=None):
        """
        Returns the user's positions
        :returns: Deferred
        """
        positions = yield self.db.get_positions(username)
        returnValue(positions)


    @wamp.register(u"rpc.trader.get_profile")
    @error_handler
    @authenticated
    @schema(u"public/trader.json#get_profile")
    def get_profile(self, username=None):
        """


        :returns: Deferred
        """
        profile = yield self.administrator.proxy.get_profile(username)
        returnValue(profile)

    @wamp.register(u"rpc.trader.change_profile")
    @error_handler
    @authenticated
    @schema(u"public/trader.json#change_profile")
    def change_profile(self, profile, username=None):
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

        if malicious_looking(profile.get('email', '')) or malicious_looking(profile.get('nickname', '')):
            raise WebserverException("exceptions/webserver/malicious-looking-input")

        result = yield self.administrator.proxy.change_profile(username, profile)
        profile = yield self.get_profile(username=username)
        returnValue(profile)

    @wamp.register(u"rpc.trader.change_password")
    @error_handler
    @authenticated
    @schema(u"public/trader.json#change_password")
    def change_password(self, old_password_hash, new_password_hash, username=None):
        """
        Changes a users password.  Leaves salt and two factor untouched.
        :param old_password_hash: current password
        :param new_password_hash: new password
        :returns: Deferred
        """


        result = yield self.administrator.proxy.reset_password_hash(username, old_password_hash, new_password_hash)
        returnValue(None)


    @wamp.register(u"rpc.trader.get_open_orders")
    @error_handler
    @authenticated
    @schema(u"public/trader.json#get_open_orders")
    def get_open_orders(self, username=None):
        """gets open orders

        :returns: Deferred
        """
        orders = yield self.db.get_open_orders(username)
        returnValue(orders)


    @wamp.register(u"rpc.trader.cancel_order")
    @error_handler
    @authenticated
    @schema(u"public/trader.json#cancel_order")
    def cancel_order(self, order_id, username=None):
        """
        Cancels a specific order
        :returns: Deferred
        :param order_id: order_id of the order
        """

        result = yield self.accountant.proxy.cancel_order(username, order_id)
        returnValue(result)

    @inlineCallbacks
    def register(self, endpoint, procedure = None, options = None):
        results = yield ServicePlugin.register(self, endpoint, procedure, options=RegisterOptions(details_arg="details", discloseCaller=True))
        returnValue(results)
