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

from zmq_util import export, dealer_proxy_async, router_share_async, pull_share_async, push_proxy_sync

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
        self.deposit_limits = { 'btc': 10000000,
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
                last_trade = self.session.query(models.Trade).filter_by(
                    contract=contract).order_by(
                    models.Trade.timestamp.desc()).first()
                self.safe_prices[contract.ticker] = int(last_trade.price)
            except:
                logging.warning(
                    "warning, missing last trade for contract: %s. Using 42 as a stupid default" % contract.ticker)
                self.safe_prices[contract.ticker] = 42
            port = 4200 + contract.id
            self.engines[contract.ticker] = dealer_proxy_async("tcp://127.0.0.1:%d" % port)

        self.webserver = push_proxy_sync(config.get("webserver", "accountant_export"))

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

    def adjust_position(self, username, contract, adjustment, description='User'):
        if not self.debug:
            return [False, (0, "Position modification not allowed")]
        position = self.get_position(username, contract, description=description)
        adjustment_position = self.get_position('system', contract, 'Adjustment')

        journal = models.Journal('Adjustment')

        # Credit the user's account
        credit = models.Posting(journal, position, adjustment, 'credit')

        # Debit the system account
        debit = models.Posting(journal, adjustment_position, adjustment, 'debit')

        try:
            self.session.add_all([position, adjustment_position, credit, debit])
            self.add_journal(journal)
            self.session.commit()
        except Exception as e:
            logging.error("Unable to modify position: %s" % e)
            self.session.rollback()

    def get_position(self, username, ticker, reference_price=0, description="User"):
        """
        Return a user's position for a contact. If it does not exist,
            initialize it.
        :param username: the username
        :param contract: the contract ticker or id
        :param reference_price: the (optional) reference price for the position
        :return: the position object
        """
        logging.debug("Looking up position for %s on %s." %
                      (username, ticker))

        user = self.get_user(username)
        contract = self.get_contract(ticker)

        try:
            return self.session.query(models.Position).filter_by(
                user=user, contract=contract, description=description).one()
        except NoResultFound:
            logging.debug("Creating new position %s for %s on %s." %
                          (description, username, contract))
            position = models.Position(user, contract, description=description)
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
            self.session.delete(order)
            self.session.commit()
            return False
        else:
            logging.info("Order accepted.")
            order.accepted = True
            self.session.merge(order)
            self.session.commit()
            return True

    def add_journal(self, journal):
        self.session.add(journal)
        logging.info("Auditing journal: %s" % journal)
        journal.audit()

    def charge_fees(self, fees, username):
        """
        Credit fees to the people operating the exchange
        """
        # TODO: Make this configurable

        # Make sure the vendorshares is less than or equal to 1.0
        assert(sum(self.vendor_share_config.values()) <= 1.0)
        journal = models.Journal('Fee')

        for ticker, fee in fees.iteritems():

            user_position = self.get_position(username, ticker)

            # Debit the fee from the user's account
            debit = models.Posting(journal, user_position, fee, 'debit')
            logging.debug("Debiting user %s with fee %d %s" % (username, fee, ticker))
            self.session.add(debit)
            self.session.add(user_position)

            remaining_fee = fee
            for vendor_name, vendor_share in self.vendor_share_config.iteritems():
                vendor_position = self.get_position(vendor_name, ticker)
                vendor_credit = int(fee * vendor_share)

                remaining_fee -= vendor_credit

                # Credit the fee to the vendor's account
                credit = models.Posting(journal, vendor_position, vendor_credit, 'credit')
                logging.debug("Crediting vendor %s with fee %d %s" % (vendor_name, vendor_credit, ticker))
                self.session.add(vendor_position)
                self.session.add(credit)

            # There might be some fee leftover due to rounding,
            # we have an account for that guy
            # Once that balance gets large we distribute it manually to the
            # various share holders
            remainder_account_position = self.get_position('remainder', ticker)
            credit = models.Posting(journal, remainder_account_position, remaining_fee)
            logging.debug("Crediting 'remainder' with fee %d %s" % (remaining_fee, ticker))

            self.session.add(credit)
            self.session.add(remainder_account_position)

        self.add_journal(journal)
        self.session.commit()

    def post_transaction(self, transaction):
        """
        Update the database to reflect that the given trade happened
        :param transaction: the transaction object
        :return: None
        """
        logging.info("Processing transaction %s." % transaction)

        aggressive_username = transaction["aggressive_username"]
        passive_username = transaction["passive_username"]
        ticker = transaction["contract"]
        price = transaction["price"]
        quantity = transaction["quantity"]
        aggressive_order_id = transaction["aggressive_order_id"]
        passive_order_id = transaction["passive_order_id"]
        side = transaction["side"]
        timestamp = transaction["timestamp"]
        journal = models.Journal('Trade', timestamp=timestamp,
                                 notes="Aggressive: %d Passive: %d" % (aggressive_order_id,
                                                                       passive_order_id))

        contract = self.get_contract(ticker)

        if contract.contract_type == "futures":
            raise NotImplementedError

            # logging.debug("This is a futures trade.")
            # aggressive_cash_position = self.get_position(aggressive_username, "BTC")
            # aggressive_future_position = self.get_position(aggressive_username, ticker, price)
            #
            # # mark to current price as if everything had been entered at that
            # #   price and profit had been realized
            # aggressive_cash_position.position += \
            #     (price - aggressive_future_position.reference_price) * \
            #     aggressive_future_position.position
            # aggressive_future_position.reference_price = price
            # aggressive_cash_position.position += \
            #     (price - aggressive_future_position.reference_price) * \
            #     aggressive_future_position.position
            # aggressive_future_position.reference_price = price
            #
            # # note that even though we're transferring money to the account,
            # #   this money may not be withdrawable because the margin will
            # #   raise depending on the distance of the price to the safe price
            #
            # # then change the quantity
            # future_position.position += signed_quantity
            #
            # self.session.merge(cash_position)
            # self.session.merge(future_position)
            #
            # # TODO: Implement fees
            # fees = None

        elif contract.contract_type == "prediction":
            raise NotImplementedError

            # cash_position = self.get_position(username, "BTC")
            # prediction_position = self.get_position(username, ticker)
            #
            # cash_position.position -= signed_quantity * price
            # prediction_position.position += signed_quantity
            #
            # self.session.merge(cash_position)
            # self.session.merge(prediction_position)
            #
            # # TODO: Implement fees
            # fees = None

        elif contract.contract_type == "cash_pair":
            from_currency_ticker, to_currency_ticker = util.split_pair(ticker)

            from_currency = self.get_contract(from_currency_ticker)
            to_currency = self.get_contract(to_currency_ticker)

            from_quantity_float = float(quantity * price) / \
                               (contract.denominator * to_currency.denominator)
            from_quantity_int = int(from_quantity_float)
            if from_quantity_float != from_quantity_int:
                logging.error("Position change is not an integer.")

            # Aggressive user
            aggressive_from_position = self.get_position(aggressive_username, from_currency)
            aggressive_to_position = self.get_position(aggressive_username, to_currency)

            passive_from_position = self.get_position(passive_username, from_currency)
            passive_to_position = self.get_position(passive_username, to_currency)

            if side == 'BUY':
                sign = 1
            else:
                sign = -1

            aggressive_debit = models.Posting(journal, aggressive_from_position, sign * from_quantity_int, 'debit')
            aggressive_credit = models.Posting(journal, aggressive_from_position, sign * quantity, 'credit')

            passive_credit = models.Posting(journal, passive_from_position, sign * from_quantity_int, 'credit')
            passive_debit = models.Posting(journal, passive_to_position, sign * quantity, 'debit')

            # Double-entry
            self.session.add_all([passive_debit,
                                  passive_credit,
                                  aggressive_debit,
                                  aggressive_credit,
                                  passive_from_position,
                                  passive_to_position,
                                  aggressive_from_position,
                                  aggressive_to_position])
            self.add_journal(journal)
            self.session.commit()

            # TODO: Move this fee logic outside of "if cash_pair"
            aggressive_fees = util.get_fees(aggressive_username, contract, abs(from_quantity_int))
            passive_fees = util.get_fees(passive_username, contract, abs(from_quantity_int))

            # Credit fees to vendor
            self.charge_fees(aggressive_fees, aggressive_username)
            self.charge_fees(passive_fees, passive_username)

            aggressive_fill = {'contract': ticker,
                               'id': aggressive_order_id,
                               'quantity': quantity,
                               'price': price,
                               'side': side,
                               'timestamp': timestamp,
                               'fees': aggressive_fees
            }
            self.webserver.fill(aggressive_username, aggressive_fill)
            logging.debug('to ws: ' + str({"fills": [aggressive_username, aggressive_fill]}))

            if side == 'SELL':
                passive_side = 'BUY'
            else:
                passive_side = 'SELL'

            passive_fill = {'contract': ticker,
                 'id': passive_order_id,
                 'quantity': quantity,
                 'price': price,
                 'side': passive_side,
                 'timestamp': timestamp,
                 'fees': passive_fees
                }
            self.webserver.fill(passive_username, passive_fill)
            logging.debug('to ws: ' + str({"fills": [passive_username, passive_fill]}))

        else:
            logging.error("Unknown contract type '%s'." %
                          contract.contract_type)


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

    def transfer_position(self, ticker, from_user, to_user, quantity, from_description='User', to_description='User'):
        try:
            journal = models.Journal('Transfer')
            from_position = self.get_position(from_user, ticker, description=from_description)
            to_position = self.get_position(to_user, ticker, description=to_description)
            debit = models.Posting(journal, from_position, quantity, 'debit')
            credit = models.Posting(journal, to_position, quantity, 'credit')
            self.session.add_all([from_position, to_position, debit, credit])
            self.add_journal(journal)
            self.session.commit()
            logging.info("Journal: %s" % journal)
        except Exception as e:
            logging.error("Transfer position failed: %s" % e)
            self.session.rollback()

    def deposit_cash(self, address, total_received):
        """
        Deposits cash
        :param address:
        :param total_received:
        :return: whether that succeeded
        """
        try:
            logging.debug('received %d at %s' % (total_received, address))

            #query for db objects we want to update
            total_deposited_at_address = session.query(models.Addresses).filter_by(address=address).one()
            contract = session.query(models.Contract).filter_by(ticker=total_deposited_at_address.currency.upper()).one()

            user_cash_position = session.query(models.Position).filter_by(
                username=total_deposited_at_address.username,
                contract_id=contract.id).one()

            #prepare cash deposit
            deposit = total_received - total_deposited_at_address.accounted_for
            journal = models.Journal('Deposit')
            bank_position = self.get_position('system', contract.ticker, 'OnlineCash')
            debit = models.Posting(journal, bank_position, deposit, 'debit')

            # TODO: Put deposit limits into the DB
            # TODO: If a deposit failed, it goes into the 'deposit_overflow' account
            deposit_limit = self.deposit_limits[total_deposited_at_address.currency]
            if user_cash_position.position + deposit > deposit_limit:
                logging.error("Deposit of %d failed for address=%s because user %s exceeded deposit limit=%d" %
                              (deposit, address, total_deposited_at_address.username, deposit_limit))
                overflow_position = self.get_position('system', contract.ticker, 'DepositOverflow')
                credit = models.Posting(journal, overflow_position, deposit, 'credit')
                self.session.add(overflow_position)
            else:
                credit = models.Posting(journal, user_cash_position, deposit, 'credit')
                self.session.add(user_cash_position)

            self.session.add_all([debit, credit])
            self.add_journal(journal)
            self.session.commit()
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
    def adjust_position(self, username, ticker, adjustment, description):
        self.accountant.adjust_position(username, ticker, adjustment, description)

    @export
    def transfer_position(self, ticker, from_user, to_user, quantity, from_description, to_description):
        self.accountant.transfer_position(self, ticker, from_user, to_user, quantity, from_description, to_description)


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

