#!/usr/bin/env python

import config

from optparse import OptionParser

parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
                  help="config file")
(options, args) = parser.parse_args()
if options.filename:
    config.reconfigure(options.filename)

import database
import models
import margin
import util

from zmq_util import export, dealer_proxy_async, router_share_async, pull_share_async

from twisted.internet import reactor
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import DataError


import logging


class AccountantException(Exception):
    pass


class Accountant:
    def __init__(self, session, debug):
        self.session = session
        self.debug = debug
        self.btc = self.get_contract("BTC")
        # TODO: Get deposit limits from DB
        self.deposit_limits = { 'btc': 1000000,
                                'mxn': 600000
        }
        # TODO: Make this configurable
        self.vendor_share_config = { 'm2': 0.5,
                                     'mexbt': 0.5
        }
        self.safe_prices = {}
        self.engines = {}
        for contract in session.query(models.Contract).filter_by(
                active=True).all():
            try:
                last_trade = session.query(models.Trade).filter_by(
                    contract=contract).order_by(
                    models.Trade.timestamp.desc()).first()
                self.safe_prices[contract.ticker] = int(last_trade.price)
            except:
                logging.warning(
                    "warning, missing last trade for contract: %s. Using 42 as a stupid default" % contract.ticker)
                self.safe_prices[contract.ticker] = 42
            port = 4200 + contract.id
            self.engines[contract.ticker] = dealer_proxy_async("tcp://127.0.0.1:%d" % port)

    def get_user(self, username):
        """
        Return the User object corresponding to the username.
        :param username: the username to look up
        :return: the User matching the username
        """
        logging.debug("Looking up username %s." % username)

        if isinstance(username, models.User):
            return username

        try:
            return self.session.query(models.User).filter_by(
                username=username).one()
        except NoResultFound:
            raise AccountantException("No such user: '%s'." % username)

    def get_contract(self, ticker):
        """
        Return the Contract object corresponding to the ticker.
        :param ticker: the ticker to look up or a Contract id
        :return: the last (id-wise) Contract object matching the ticker
        """
        logging.debug("Looking up contract %s." % ticker)

        if isinstance(ticker, models.Contract):
            return ticker

        try:
            ticker = int(ticker)
            return self.session.query(models.Contract).filter_by(
                contract_id=ticker).one()
        except NoResultFound:
            raise AccountantException("Could not resolve contract '%s'." % ticker)
        except ValueError:
            # drop through
            pass

        try:
            return self.session.query(models.Contract).filter_by(
                ticker=ticker).order_by(models.Contract.id.desc()).first()
        except NoResultFound:
            raise AccountantException("Could not resolve contract '%s'." % ticker)

    def adjust_position(self, username, contract, adjustment):
        if not self.debug:
            return [False, (0, "Position modification not allowed")]
        position = self.get_position(username, contract)
        old_position = position.position
        position.position += adjustment
        try:
            session.add(position)
            session.commit()
            logging.info("Position for %s/%s modified from %d to %d" %
                         (username, contract, old_position, position.position))
        except Exception as e:
            logging.error("Unable to modify position: %s" % e)
            session.rollback()

    def get_position(self, username, contract, reference_price=0):
        """
        Return a user's position for a contact. If it does not exist,
            initialize it.
        :param username: the username
        :param contract: the contract ticker or id
        :param reference_price: the (optional) reference price for the position
        :return: the position object
        """
        logging.debug("Looking up position for %s on %s." %
                      (username, contract))

        user = self.get_user(username)
        contract = self.get_contract(contract)

        try:
            return self.session.query(models.Position).filter_by(
                user=user, contract=contract).one()
        except NoResultFound:
            logging.debug("Creating new position for %s on %s." %
                          (username, contract))
            position = models.Position(user, contract)
            position.reference_price = reference_price
            self.session.add(position)
            return position

    def accept_order(self, order):
        """
        Accept the order if the user has sufficient margin. Otherwise, delete
            the order.
        :param order: Order object we wish to accept
        :return success: True if there was sufficient margin, otherwise False
        """
        logging.info("Trying to accept order %s." % order)

        low_margin, high_margin = margin.calculate_margin(
            order.username, self.session, self.safe_prices, order.id)

        cash_position = self.get_position(order.username, "BTC")

        logging.info("high_margin = %d, low_margin = %d, cash_position = %d" %
                     (high_margin, low_margin, cash_position.position))

        if high_margin > cash_position.position:
            # TODO replace deleting rejected orders with marking them as
            #   rejected, using an enum

            logging.info("Order rejected due to margin.")
            session.delete(order)
            session.commit()
            return False
        else:
            logging.info("Order accepted.")
            order.accepted = True
            session.merge(order)
            session.commit()
            return True


    def credit_fees(self, fees):
        """
        Credit fees to the people operating the exchange
        """
        # TODO: Make this configurable

        # Make sure the vendorshares is less than or equal to 1.0
        assert(sum(self.vendor_share_config.values()) <= 1.0)

        for ticker, fee in fees.iteritems():
            remaining_fee = fee
            for vendor_name, vendor_share in self.vendor_share_config.iteritems():
                vendor_position = self.get_position(vendor_name, ticker)
                vendor_credit = int(fee * vendor_share)
                vendor_position.position += vendor_credit
                remaining_fee -= vendor_credit
                session.add(vendor_position)

            # There might be some fee leftover due to rounding,
            # we have an account for that guy
            # Once that balance gets large we distribute it manually to the
            # various share holders
            remainder_account_position = self.position('remainder', ticker)
            remainder_account_position.position += remaining_fee
            session.add(remainder_account_position)

    def post_transaction(self, transaction):
        """
        Update the database to reflect that the given trade happened
        :param transaction: the transaction object
        :return: None
        """
        logging.info("Processing transaction %s." % transaction)

        username = transaction["username"]
        ticker = transaction["contract"]
        price = transaction["price"]
        signed_quantity = transaction["signed_quantity"]

        contract = self.get_contract(ticker)

        if contract.contract_type == "futures":
            logging.debug("This is a futures trade.")
            cash_position = self.get_position(username, "BTC")
            future_position = self.get_position(username, ticker, price)

            # mark to current price as if everything had been entered at that
            #   price and profit had been realized
            cash_position.position += \
                (price - future_position.reference_price) * \
                future_position.position
            future_position.reference_price = price

            # note that even though we're transferring money to the account,
            #   this money may not be withdrawable because the margin will
            #   raise depending on the distance of the price to the safe price

            # then change the quantity
            future_position.position += signed_quantity

            session.merge(cash_position)
            session.merge(future_position)

        elif contract.contract_type == "prediction":
            cash_position = self.get_position(username, "BTC")
            prediction_position = self.get_position(username, ticker)

            cash_position.position -= signed_quantity * price
            prediction_position.position += signed_quantity

            session.merge(cash_position)
            session.merge(prediction_position)

        elif contract.contract_type == "cash_pair":
            from_currency_ticker, to_currency_ticker = util.split_pair(ticker)

            from_currency = self.get_contract(from_currency_ticker)
            to_currency = self.get_contract(to_currency_ticker)

            from_position = self.get_position(username, from_currency)
            to_position = self.get_position(username, to_currency)

            from_delta_float = float(signed_quantity * price) / \
                               (contract.denominator * to_currency.denominator)
            from_delta_int = int(from_delta_float)
            if from_delta_float != from_delta_int:
                logging.error("Position change is not an integer.")

            from_position.position -= from_delta_int
            to_position.position += signed_quantity

            fees = util.get_fees(username, contract, abs(from_delta_int))

            # Credit fees to vendor
            self.credit_fees(fees)

            # Deduct fees from user
            if from_currency_ticker in fees:
                from_position.position -= fees[from_currency_ticker]
            if to_currency_ticker in fees:
                to_position.position -= fees[to_currency_ticker]

            session.add(from_position)
            session.add(to_position)

        else:
            logging.error("Unknown contract type '%s'." %
                          contract.contract_type)

        session.commit()


    def cancel_order(self, order_id):
        """
        Cancel an order by id.
        :param id: The order id to cancel
        :return: None
        """
        logging.info("Received request to cancel order id %d." % order_id)

        try:
            order = session.query(models.Order).filter_by(id=order_id).one()
            return self.engines[order.contract.ticker].cancel_order(order_id)
        except NoResultFound:
            # TODO: Fix to use exceptions
            return [False, (0, "No order %d found" % order_id)]

    def place_order(self, order):
        """
        Place an order
        :param order: dictionary representing the order to be placed
        :return: id of the order placed or -1 if failure
        """
        user = self.get_user(order["username"])
        contract = self.get_contract(order["contract"])

        if not contract.active:
            # TODO: Fix to use exceptions
            return [False, (0, "Contract is not active.")]

        # do not allow orders for internally used contracts
        if contract.contract_type == 'cash':
            logging.critical("Webserver allowed a 'cash' contract!")
            return [False, (0, "Not a valid contract type.")]

        # TODO: check that the price is an integer and within a valid range

        # case of predictions
        if contract.contract_type == 'prediction':
            # contract.denominator happens to be the same as the finally payoff
            if not 0 <= order["price"] <= contract.denominator:
                return [False, (0, "Not a valid prediction price")]

        o = models.Order(user, contract, order["quantity"], order["price"], order["side"].upper())
        try:
            session.add(o)
            session.commit()
        except Exception as e:
            logging.error("Error adding data %s" % e)
            session.rollback()
            raise e

        if self.accept_order(o):
            return self.engines[o.contract.ticker].place_order(o.to_matching_engine_order())
        else:
            # TODO: Fix to use exceptions
            return [False, (0, "Not enough margin")]

    def deposit_cash(self, address, total_received):
        """
        Deposits cash
        :param address:
        :param total_received:
        :return: whether that succeeded
        """
        try:
            logging.log('received %d at %s' % (total_received, address))

            #query for db objects we want to update
            total_deposited_at_address = session.query(models.Addresses).filter_by(address=address).one()
            user_cash_position = session.query(models.Position).filter_by(
                username=total_deposited_at_address.username,
                contract=total_deposited_at_address.currency).one()

            #prepare cash deposit
            deposit = total_received - total_deposited_at_address.accounted_for
            user_cash_position.position += deposit

            # TODO: Put deposit limits into the DB
            # TODO: If a deposit failed, we have to refund the money somehow
            deposit_limit = self.deposit_limits[total_deposited_at_address.currency]
            if user_cash_position.postion > deposit_limit:
                logging.error("Deposit failed for address=%s because user exceeded deposit limit=%d" %
                              (address, deposit_limit))
                return False

            total_deposited_at_address.accounted_for = total_received
            session.add(total_deposited_at_address)
            session.add(user_cash_position)
            session.commit()

            return True
        except:
            session.rollback()
            logging.error(
                "Updating user position failed for address=%s and total_received=%d" % (address, total_received))
            return False

    def clear_contract(self, ticker):
        try:
            contract = self.get_contract(ticker)
            # disable new orders on contract
            contract.active = False
            # cancel all pending orders
            orders = session.query(models.Order).filter_by(
                contract=contract, is_cancelled=False).all()
            for order in orders:
                self.cancel_order(order.id)
            # place orders on behalf of users
            positions = session.query(models.Position).filter_by(
                contract=contract).all()
            for position in positions:
                order = {}
                order["username"] = position.username
                order["contract_id"] = position.contract_id
                if position.position > 0:
                    order["quantity"] = position.position
                    order["side"] = 0  # sell
                elif position.position < 0:
                    order["quantity"] = -position.position
                    order["side"] = 1  # buy
                #order["price"] = details["price"] #todo what's that missing details?
                self.place_order(order)
            session.commit()
        except:
            session.rollback()


class WebserverExport:
    def __init__(self, accountant):
        self.accountant = accountant

    @export
    def place_order(self, order):
        return self.accountant.place_order(order)

    @export
    def cancel_order(self, order_id):
        return self.accountant.cancel_order(order_id)


class EngineExport:
    def __init__(self, accountant):
        self.accountant = accountant

    @export
    def safe_prices(self, ticker, price):
        self.accountant.safe_prices[ticker] = price

    @export
    def post_transaction(self, transaction):
        self.accountant.post_transaction(transaction)


class CashierExport:
    def __init__(self, accountant):
        self.accountant = accountant

    @export
    def deposit_cash(self, address, total_received):
        self.accountant.deposit_cash(address, total_received)


class AdministratorExport:
    def __init__(self, accountant):
        self.accountant = accountant

    @export
    def clear_contract(self, ticker):
        self.accountant.clear_contract(ticker)

    @export
    def adjust_position(self, username, ticker, adjustment):
        self.accountant.adjust_position(username, ticker, adjustment)

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    session = database.make_session()
    debug = config.getboolean("accountant", "debug")

    accountant = Accountant(session, debug=debug)

    webserver_export = WebserverExport(accountant)
    engine_export = EngineExport(accountant)
    cashier_export = CashierExport(accountant)
    administrator_export = AdministratorExport(accountant)

    router_share_async(webserver_export,
                       config.get("accountant", "webserver_export"))
    pull_share_async(engine_export,
                     config.get("accountant", "engine_export"))
    pull_share_async(cashier_export,
                     config.get("accountant", "cashier_export"))
    router_share_async(administrator_export,
                     config.get("accountant", "administrator_export"))

    reactor.run()

