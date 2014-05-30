#!/usr/bin/env python
"""
.. module:: accountant

The accountant is responsible for user-specific data, except for login sorts of data, which are managed by the
administrator. It is responsible for the following:

* models.Position
* models.PermissionGroup

"""

import config

from optparse import OptionParser

parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
                  help="config file")
(options, args) = parser.parse_args()
if options.filename:
    config.reconfigure(options.filename)

import collections

import database
import models
import margin
import util
import ledger
from alerts import AlertsProxy

from zmq_util import export, dealer_proxy_async, router_share_async, pull_share_async, push_proxy_sync, \
    dealer_proxy_sync, RemoteCallTimedOut, RemoteCallException

from twisted.internet import reactor
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import DataError
from datetime import datetime, date
from watchdog import watchdog

import logging


class AccountantException(Exception):
    pass

INSUFFICIENT_MARGIN = AccountantException(0, "Insufficient margin")
TRADE_NOT_PERMITTED = AccountantException(1, "Trading not permitted")
WITHDRAW_NOT_PERMITTED = AccountantException(2, "Withdrawals not permitted")

class Accountant:
    """The Accountant primary class

    """
    def __init__(self, session, engines, cashier, ledger, webserver,
                 alerts_proxy, debug, trial_period=False):
        """Initialize the Accountant

        :param session: The SQL Alchemy session
        :type session:
        :param debug: Whether or not weird things can happen like position adjustment
        :type debug: bool

        """

        self.session = session
        self.debug = debug
        self.deposit_limits = {}
        # TODO: Make this configurable
        self.vendor_share_config = { 'm2': 0.5,
                                     'customer': 0.5
        }
        self.safe_prices = {}
        self.engines = engines
        self.ledger = ledger
        self.cashier = cashier
        self.trial_period = trial_period
        self.alerts_proxy = alerts_proxy
        for contract in self.session.query(models.Contract).filter_by(
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

        self.webserver = webserver
        self.audit_cache = None

    def post_or_fail(self, *postings):
        def on_success(self, result):
            try:
                for posting in postings:
                    position = self.get_positon(posting.user, posting.contract)
                    position.position += posting.quanity
                    self.session.merge(position)
                self.session.commit()
            finally:
                self.session.rollback()

        def on_fail_ledger(self, failure):
            e = failure.trap(ledger.LedgerException)
            logging.error("Ledger exception:")
            logging.error(str(failure.value))
            self.alerts_proxy.send_alert("Exception in ledger. See logs.")

        def on_fail_rpc(self, failure):
            e = failure.trap(RemoteCallException)
            if isinstance(e, RemoteCallTimedOut):
                logging.error("Ledger call timed out.")
                self.alerts_proxy.send_alert("Ledger call timed out. Ledger may be overloaded.")
            else:
                logging.error("Improper ledger RPC invocation:")
                logging.error(str(failure.value))

        d = self.ledger.post(*postings)
        d.addCallback(on_success)
        d.addErrback(on_fail_ledger)
        d.addErrback(on_fail_rpc)

    def publish_journal(self, journal):
        """Takes a models.Journal and sends all its postings to the webserver

        :param journal: The journal entry
        :type journal: models.Journal

        """
        for posting in journal.postings:
            transaction = {'contract': posting.contract.ticker,
                      'timestamp': util.dt_to_timestamp(posting.journal.timestamp),
                      'quantity': posting.quantity,
                      'type': posting.journal.type
            }
            self.webserver.transaction(posting.username, transaction)

    def get_user(self, username):
        """Return the User object corresponding to the username.

        :param username: the username to look up
        :type username: str, models.User
        :returns: models.User -- the User matching the username
        :raises: AccountantException
        """

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
        :type ticker: str, models.Contract
        :returns: models.Contract -- the Contract object matching the ticker
        :raises: AccountantException
        """
        return util.get_contract(self.session, ticker)

    def adjust_position(self, username, ticker, quantity):
        """Adjust a user's position, offsetting with the 'adjustment' account

        :param username: The user
        :type username: str, models.User
        :param ticker: The contract
        :type ticker: str, models.Contract
        :param quantity: the delta to apply
        :type quantity: int

        """
        if not self.debug:
            raise AccountantException(0, "Position modification not allowed")
        user = self.get_user(username)
        contract = self.get_contract(ticker)
        position = self.get_position(username, ticker)
        adjustment_user = self.get_user('adjustments')
        adjustment_position = self.get_position('adjustments', ticker)

        # Credit the user's account
        credit = models.Posting(user, contract, quantity, 'credit', update_position=True,
                                position=position)

        # Debit the system account
        debit = models.Posting(adjustment_user, contract, quantity, 'debit', update_position=True,
                               position=adjustment_position)

        try:
            self.session.add_all([position, adjustment_position, credit, debit])
            journal = models.Journal('Adjustment', [credit, debit], alerts_proxy=self.alerts_proxy)
            self.session.add(journal)
            self.session.commit()
            self.publish_journal(journal)
            logging.info("Journal: %s" % journal)
        except Exception as e:
            logging.error("Unable to modify position: %s" % e)
            self.session.rollback()

    def get_position(self, username, ticker, reference_price=0):
        """Return a user's position for a contact. If it does not exist, initialize it

        :param username: the username
        :type username: str, models.User
        :param ticker: the contract
        :type ticker: str, models.User
        :param reference_price: the (optional) reference price for the position
        :type reference_price: int
        :returns: models.Position -- the position object
        """

        user = self.get_user(username)
        contract = self.get_contract(ticker)

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

    def check_margin(self, username, low_margin, high_margin):
        cash_position = self.get_position(username, "BTC")

        logging.info("high_margin = %d, low_margin = %d, cash_position = %d" %
                     (high_margin, low_margin, cash_position.position))

        if high_margin > cash_position.position:
            return False
        else:
            return True

    def accept_order(self, order):
        """Accept the order if possible. Otherwise, delete the order

        :param order: Order object we wish to accept
        :type order: models.Order
        :raises: INSUFFICIENT_MARGIN, TRADE_NOT_PERMITTED
        """
        logging.info("Trying to accept order %s." % order)

        user = order.user
        if not user.permissions.trade:
            logging.info("order %s not accepted because user %s not permitted to trade" % (order.id, user.username))
            self.session.delete(order)
            self.session.commit()
            raise TRADE_NOT_PERMITTED

        # Make sure there is a position in the contract, if it is not a cash_pair
        # cash_pairs don't have positions
        if order.contract.contract_type != "cash_pair":
            self.get_position(order.username, order.contract)

        low_margin, high_margin = margin.calculate_margin(
            order.username, self.session, self.safe_prices, order.id,
            trial_period=self.trial_period)

        if self.check_margin(order.username, low_margin, high_margin):
            logging.info("Order accepted.")
            order.accepted = True
            self.session.merge(order)
            self.session.commit()
        else:
            logging.info("Order rejected due to margin.")
            self.session.delete(order)
            self.session.commit()
            raise INSUFFICIENT_MARGIN



    def charge_fees(self, fees, user):
        """Credit fees to the people operating the exchange
        :param fees: The fees to charge ticker-index dict of fees to charge
        :type fees: dict
        :param username: the user to charge
        :type username: str, models.User

        """
        # TODO: Make this configurable
        import time

        # Make sure the vendorshares is less than or equal to 1.0
        assert(sum(self.vendor_share_config.values()) <= 1.0)
        postings = []
        last = time.time()

        for ticker, fee in fees.iteritems():
            user_position = self.get_position(user, ticker)
            contract = self.get_contract(ticker)

            # Debit the fee from the user's account
            debit = models.Posting(user, contract, fee, 'debit', update_position=True,
                                   position=user_position)
            self.session.add(debit)
            postings.append(debit)
            self.session.add(user_position)

            remaining_fee = fee
            for vendor_name, vendor_share in self.vendor_share_config.iteritems():
                vendor_user = self.get_user(vendor_name)
                vendor_position = self.get_position(vendor_name, ticker)
                vendor_credit = int(fee * vendor_share)

                remaining_fee -= vendor_credit

                # Credit the fee to the vendor's account
                credit = models.Posting(vendor_user, contract, vendor_credit, 'credit', update_position=True,
                                        position=vendor_position)
                self.session.add(vendor_position)
                self.session.add(credit)
                postings.append(credit)

            # There might be some fee leftover due to rounding,
            # we have an account for that guy
            # Once that balance gets large we distribute it manually to the
            # various share holders
            remainder_position = self.get_position('remainder', ticker)
            remainder_user = self.get_user('remainder')
            credit = models.Posting(remainder_user, contract, remaining_fee, 'credit', update_position=True,
                                    position=remainder_position)
            self.session.add(credit)
            postings.append(credit)
            self.session.add(remainder_position)
            next = time.time()
            elapsed = (next - last) * 1000
            last = next
            logging.debug("charge_fees: %s: %.3f ms." % (ticker, elapsed))

        return postings


    def post_transaction(self, transaction):
        """Update the database to reflect that the given trade happened. Charge fees.

        :param transaction: the transaction object
        :type transaction: dict
        """
        logging.info("Processing transaction %s." % transaction)
        import time
        last = time.time()

        aggressive_username = transaction["aggressive_username"]
        passive_username = transaction["passive_username"]
        ticker = transaction["contract"]
        price = transaction["price"]
        quantity = transaction["quantity"]
        aggressive_order_id = transaction["aggressive_order_id"]
        passive_order_id = transaction["passive_order_id"]
        side = transaction["side"]
        timestamp = transaction["timestamp"]

        contract = self.get_contract(ticker)
        aggressive_user = self.get_user(aggressive_username)
        passive_user = self.get_user(passive_username)

        next = time.time()
        elapsed = (next - last) * 1000
        last = next
        logging.debug("post_transaction: part 1: %.3f ms." % elapsed)

        if side == 'BUY':
            sign = 1
        else:
            sign = -1

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
            denominated_contract = contract.denominated_contract
            payout_contract = contract

            cash_spent_float = float(quantity * price * contract.lot_size / contract.denominator)
            cash_spent_int = int(cash_spent_float)
            if cash_spent_float != cash_spent_int:
                message = "cash_spent (%f) is not an integer: (quantity=%d price=%d contract.lot_size=%d contract.denominator=%d" % \
                          (cash_spent_float, quantity, price, contract.lot_size, contract.denominator)
                logging.error(message)
                self.alerts_proxy.send_alert(message, "Integer failure")

        elif contract.contract_type == "cash_pair":
            denominated_contract = contract.denominated_contract
            payout_contract = contract.payout_contract

            cash_spent_float = float(quantity * price) / \
                               (contract.denominator * payout_contract.denominator)
            cash_spent_int = int(cash_spent_float)
            if cash_spent_float != cash_spent_int:
                message = "cash_spent (%f) is not an integer: (quantity=%d price=%d contract.denominator=%d payout_contract.denominator=%d)" % \
                              (cash_spent_float, quantity, price, contract.denominator, payout_contract.denominator)
                logging.error(message)
                self.alerts_proxy.send_alert(message, "Integer failure")
        else:
            logging.error("Unknown contract type '%s'." %
                          contract.contract_type)
            raise NotImplementedError

        next = time.time()
        elapsed = (next - last) * 1000
        last = next
        logging.debug("post_transaction: part 2: %.3f ms." % elapsed)

        aggressive_from_position = self.get_position(aggressive_username, denominated_contract)
        aggressive_to_position = self.get_position(aggressive_username, payout_contract)

        passive_from_position = self.get_position(passive_username, denominated_contract)
        passive_to_position = self.get_position(passive_username, payout_contract)

        aggressive_debit = models.Posting(aggressive_user, denominated_contract, sign * cash_spent_int, 'debit',
                                          update_position=True, position=aggressive_from_position)
        aggressive_credit = models.Posting(aggressive_user, payout_contract, sign * quantity, 'credit',
                                           update_position=True, position=aggressive_to_position)

        passive_credit = models.Posting(passive_user, denominated_contract, sign * cash_spent_int, 'credit',
                                        update_position=True, position=passive_from_position)
        passive_debit = models.Posting(passive_user, payout_contract, sign * quantity, 'debit',
                                       update_position=True, position=passive_to_position)

        aggressive_fees = util.get_fees(aggressive_username, contract, abs(cash_spent_int),
                                        trial_period=self.trial_period)

        # We aren't charging the liquidity provider
        #
        # passive_fees = util.get_fees(passive_username, contract, abs(cash_spent_int))

        postings = [aggressive_credit,
                    aggressive_debit,
                    passive_credit,
                    passive_debit]

        next = time.time()
        elapsed = (next - last) * 1000
        last = next
        logging.debug("post_transaction: part 3: %.3f ms." % elapsed)

        # Commit
        try:
            self.session.add_all(postings)
            self.session.add_all([passive_from_position,
                                  passive_to_position,
                                  aggressive_from_position,
                                  aggressive_to_position])

            if not self.trial_period:
                fee_postings = self.charge_fees(aggressive_fees, aggressive_user)
                postings.extend(fee_postings)

            journal = models.Journal('Trade', postings, timestamp=util.timestamp_to_dt(timestamp),
                                     alerts_proxy=self.alerts_proxy,
                                     notes="Aggressive: %d Passive: %d" % (aggressive_order_id,
                                                                        passive_order_id))
            self.session.add(journal)
            next = time.time()
            elapsed = (next - last) * 1000
            last = next
            logging.debug("post_transaction: part 4: %.3f ms." % elapsed)

            self.session.add(journal)
            self.session.commit()
            self.publish_journal(journal)
            logging.info("Journal: %s" % journal)

            next = time.time()
            elapsed = (next - last) * 1000
            last = next
            logging.debug("post_transaction: part 5: %.3f ms." % elapsed)
        except Exception as e:
            logging.error("Unable to post_transaction: %s" % e)
            self.session.rollback()
            return

        # Send notifications
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
             'fees': {}
            }
        self.webserver.fill(passive_username, passive_fill)
        logging.debug('to ws: ' + str({"fills": [passive_username, passive_fill]}))
        next = time.time()
        elapsed = (next - last) * 1000
        last = next
        logging.debug("post_transaction: part 6: %.3f ms." % elapsed)


    def raiseException(self, failure):
        raise failure.value

    def cancel_order(self, order_id, username=None):
        """Cancel an order by id.

        :param id: The order id to cancel
        :type id: int
        :returns: tuple -- (True/False, Result/Error)
        """
        logging.info("Received request to cancel order id %d." % order_id)

        try:
            order = self.session.query(models.Order).filter_by(id=order_id).one()
            if username is not None and order.username != username:
                raise AccountantException(0, "User %s does not own the order" % username)

            d = self.engines[order.contract.ticker].cancel_order(order_id)
            d.addErrback(self.raiseException)
            return d
        except NoResultFound:
            raise AccountantException(0, "No order %d found" % order_id)

    def place_order(self, order):
        """Place an order

        :param order: dictionary representing the order to be placed
        :type order: dict
        :returns: tuple -- (True/False, Result/Error)
        """
        user = self.get_user(order["username"])
        contract = self.get_contract(order["contract"])

        if not contract.active:
            raise AccountantException(0, "Contract is not active.")

        if contract.expired:
            raise AccountantException(0, "Contract expired")

        # do not allow orders for internally used contracts
        if contract.contract_type == 'cash':
            logging.critical("Webserver allowed a 'cash' contract!")
            raise AccountantException(0, "Not a valid contract type.")

        if order["price"] % contract.tick_size != 0 or order["price"] < 0 or order["quantity"] < 0:
            raise AccountantException(0, "invalid price or quantity")

        # case of predictions
        if contract.contract_type == 'prediction':
            if not 0 <= order["price"] <= contract.denominator:
                raise Accountant(0, "invalid price or quantity")

        if contract.contract_type == "cash_pair":
            if not order["quantity"] % contract.lot_size == 0:
                raise AccountantException(0, "invalid price or quantity")

        o = models.Order(user, contract, order["quantity"], order["price"], order["side"].upper())
        try:
            self.session.add(o)
            self.session.commit()
        except Exception as e:
            logging.error("Error adding data %s" % e)
            self.session.rollback()
            raise e

        self.accept_order(o)
        d = self.engines[o.contract.ticker].place_order(o.to_matching_engine_order())
        d.addErrback(self.raiseException)
        return d

    def transfer_position(self, ticker, from_username, to_username, quantity, note):
        """Transfer a position from one user to another

        :param ticker: the contract
        :type ticker: str, models.Contract
        :param from_username: the user to transfer from
        :type from_username: str, models.User
        :param to_username: the user to transfer to
        :type to_username: str, models.User
        :param quantity: the qty to transfer
        :type quantity: int
        """
        try:
            from_user = self.get_user(from_username)
            to_user = self.get_user(to_username)

            from_position = self.get_position(from_user, ticker)
            to_position = self.get_position(to_user, ticker)

            contract = self.get_contract(ticker)

            debit = models.Posting(from_user, contract, quantity, 'debit', update_position=True,
                                   position=from_position)
            credit = models.Posting(to_user, contract, quantity, 'credit', update_position=True,
                                    position=to_position)
            self.session.add_all([from_position, to_position, debit, credit])
            journal = models.Journal('Transfer', [debit, credit], notes=note, alerts_proxy=self.alerts_proxy)
            self.session.add(journal)
            self.session.commit()
            self.publish_journal(journal)
            logging.info("Journal: %s" % journal)
        except Exception as e:
            logging.error("Transfer position failed: %s" % e)
            self.session.rollback()

    def request_withdrawal(self, username, ticker, amount, address):
        """See if we can withdraw, if so reduce from the position and create a withdrawal entry

        :param username:
        :param ticker:
        :param amount:
        :param address:
        :returns: bool
        :raises: INSUFFICIENT_MARGIN, WITHDRAW_NOT_PERMITTED
        """
        try:
            if self.trial_period:
                logging.error("Withdrawals not permitted during trial period")
                raise WITHDRAW_NOT_PERMITTED

            logging.debug("Withdrawal request for %s %s for %d to %s received" % (username, ticker, amount, address))
            user = self.get_user(username)
            if not user.permissions.withdraw:
                logging.error("Withdraw request for %s failed due to no permissions" % username)
                raise WITHDRAW_NOT_PERMITTED

            contract = self.get_contract(ticker)

            position = self.get_position(username, ticker)
            pending_withdrawal_user = self.get_user('pendingwithdrawal')
            pending_withdrawal_position = self.get_position('pendingwithdrawal', ticker)
            credit = models.Posting(pending_withdrawal_user, contract, amount, 'credit', update_position=True,
                                    position=pending_withdrawal_position)
            debit = models.Posting(user, contract, amount, 'debit', update_position=True,
                                   position=position)

            self.session.add_all([position, pending_withdrawal_position])
            self.session.add_all([debit, credit])

            # Check margin now
            low_margin, high_margin = margin.calculate_margin(username, self.session, self.safe_prices,
                                                              trial_period=self.trial_period)
            if not self.check_margin(username, low_margin, high_margin):
                logging.info("Insufficient margin for withdrawal %d / %d" % (low_margin, high_margin))
                raise INSUFFICIENT_MARGIN
            else:
                journal = models.Journal('Withdrawal', [credit, debit], notes=address, alerts_proxy=self.alerts_proxy)
                self.session.add(journal)
                self.session.commit()
                self.publish_journal(journal)
                logging.info("Journal: %s" % journal)
                self.cashier.request_withdrawal(username, ticker, address, amount)
                return True
        except Exception as e:
            self.session.rollback()
            logging.error("Exception received while attempting withdrawal: %s" % e)
            raise e

    def deposit_cash(self, address, received, total=True):
        """Deposits cash
        :param address: The address where the cash was deposited
        :type address: str
        :param received: how much total was received at that address
        :type received: int
        :param total: if True, then received is the total received on that address. If false, then received is just the most recent receipt
        :type total: bool
        """
        try:
            logging.debug('received %d at %s - total=%s' % (received, address, total))

            #query for db objects we want to update

            total_deposited_at_address = self.session.query(models.Addresses).filter_by(address=address).one()
            contract = total_deposited_at_address.contract

            user_cash_position = self.get_position(total_deposited_at_address.username,
                                                   contract.ticker)
            user = self.get_user(total_deposited_at_address.user)

            # compute deposit _before_ marking ammount as accounted for
            if total:
                deposit = received - total_deposited_at_address.accounted_for
                total_deposited_at_address.accounted_for = received
            else:
                deposit = received
                total_deposited_at_address.accounted_for += deposit

            # update address

            self.session.add(total_deposited_at_address)

            #prepare cash deposit
            postings = []
            bank_position = self.get_position('onlinecash', contract)
            bank_user = self.get_user('onlinecash')
            debit = models.Posting(bank_user, contract, deposit, 'debit', update_position=True,
                                   position=bank_position)
            self.session.add(bank_position)
            postings.append(debit)

            credit = models.Posting(user, contract, deposit, 'credit', update_position=True,
                                    position=user_cash_position)
            postings.append(credit)

            if total_deposited_at_address.contract.ticker in self.deposit_limits:
                deposit_limit = self.deposit_limits[total_deposited_at_address.contract.ticker]
            else:
                deposit_limit = float("inf")

            excess_deposit = 0
            if not user.permissions.deposit:
                logging.error("Deposit of %d failed for address=%s because user %s is not permitted to deposit" %
                              (deposit, address, user.username))

                # The user's not permitted to deposit at all. The excess deposit is the entire value
                excess_deposit = deposit
            elif user_cash_position.position > deposit_limit:
                logging.error("Deposit of %d failed for address=%s because user %s exceeded deposit limit=%d" %
                              (deposit, address, total_deposited_at_address.username, deposit_limit))
                excess_deposit = user_cash_position.position - deposit_limit

            if excess_deposit > 0:
                # There was an excess deposit, transfer that amount into overflow cash
                excess_debit = models.Posting(user, contract, excess_deposit, 'debit', update_position=True,
                                       position=user_cash_position)
                depositoverflow_user = self.get_user('depositoverflow')
                depositoverflow_position = self.get_position('depositoverflow', contract)
                excess_credit = models.Posting(depositoverflow_user, contract, excess_deposit, 'credit', update_position=True,
                                        position=depositoverflow_position)

                postings.append(excess_debit)
                postings.append(excess_credit)
                self.session.add(depositoverflow_position)

            self.session.add(user_cash_position)
            self.session.add_all(postings)
            journal = models.Journal('Deposit', postings, notes=address, alerts_proxy=self.alerts_proxy)
            self.session.add(journal)
            self.session.commit()
            self.publish_journal(journal)
            logging.info("Journal: %s" % journal)
        except Exception as e:
            self.session.rollback()
            logging.error(
                "Updating user position failed for address=%s and received=%d: %s" % (address, received, e))

    def clear_contract(self, ticker):
        """Deletes a contract

        :param ticker: the contract to delete
        :type ticker: str, models.Contract
        """
        try:
            contract = self.get_contract(ticker)
            # disable new orders on contract
            contract.active = False
            # cancel all pending orders
            orders = self.session.query(models.Order).filter_by(
                contract=contract, is_cancelled=False).all()
            for order in orders:
                self.cancel_order(order.id)
            # place orders on behalf of users
            positions = self.session.query(models.Position).filter_by(
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
            self.session.commit()
        except:
            self.session.rollback()

    # These two should go into the ledger process. We should
    # only run this once per day and cache the result
    def get_balance_sheet(self):
        """Gets the balance sheet

        :returns: dict -- the balance sheet
        """

        positions = self.session.query(models.Position).all()
        balance_sheet = {'assets': {},
                         'liabilities': {}
        }

        for position in positions:
            if position.position is not None:
                if position.user.type == 'Asset':
                    side = balance_sheet['assets']
                else:
                    side = balance_sheet['liabilities']

                position_details = { 'username': position.user.username,
                                                                    'hash': position.user.user_hash,
                                                                    'position': position.position,
                                                                    'position_fmt': position.quantity_fmt
                }
                if position.contract.ticker in side:
                    side[position.contract.ticker]['total'] += position.position
                    side[position.contract.ticker]['positions_raw'].append(position_details)
                else:
                    side[position.contract.ticker] = {'total': position.position,
                                                      'positions_raw': [position_details],
                                                      'contract': position.contract.ticker}

                side[position.contract.ticker]['total_fmt'] = \
                    ("{total:.%df}" % util.get_quantity_precision(position.contract)).format(
                        total=util.quantity_from_wire(position.contract, side[position.contract.ticker]['total'])
                )

        return balance_sheet

    def get_audit(self):
        """Gets the audit, which is the balance sheet but scrubbed of usernames

        :returns: dict -- the audit
        """
        now = util.dt_to_timestamp(datetime.utcnow())
        if self.audit_cache is not None:
            one_day = 24 * 3600 * 1000000
            if now - self.audit_cache['timestamp'] < one_day:
                # Return the cache if it's been less than a day
                return self.audit_cache

        balance_sheet = self.get_balance_sheet()
        for side in balance_sheet.values():
            for ticker, details in side.iteritems():
                details['positions'] = []
                for position in details['positions_raw']:
                    details['positions'].append((position['hash'], position['position']))
                del details['positions_raw']

        balance_sheet['timestamp'] = now
        self.audit_cache = balance_sheet
        return balance_sheet

    def get_transaction_history(self, username, from_timestamp, to_timestamp):
        """Get the history of a user's transactions

        :param username: the user
        :type username: str, models.User
        :param from_timestamp: Starting time
        :type from_timestamp: int
        :param end_timestamp: Ending time
        :type end_timestamp: int
        :returns: list -- an array of ledger entries
        """

        from_dt = util.timestamp_to_dt(from_timestamp)
        to_dt = util.timestamp_to_dt(to_timestamp)

        transactions = []
        postings = self.session.query(models.Posting).filter_by(username=username).join(models.Journal).filter(
            models.Journal.timestamp <= to_dt,
            models.Journal.timestamp >= from_dt
        )
        for posting in postings:
            transactions.append({'contract': posting.contract.ticker,
                            'timestamp': util.dt_to_timestamp(posting.journal.timestamp),
                            'quantity': posting.quantity,
                            'type': posting.journal.type})
        return transactions

    def change_permission_group(self, username, id):
        """Changes a user's permission group to something different

        :param username: the user
        :type username: str, models.User
        :param id: the permission group id
        :type id: int
        """

        try:
            logging.debug("Changing permission group for %s to %d" % (username, id))
            user = self.get_user(username)
            user.permission_group_id = id
            self.session.add(user)
            self.session.commit()
        except Exception as e:
            logging.error("Error: %s" % e)
            self.session.rollback()

    def new_permission_group(self, name, permissions):
        """Create a new permission group

        :param name: the new group's name
        :type name: str
        """

        try:
            logging.debug("Creating new permission group %s" % name)
            permission_group = models.PermissionGroup(name, permissions)
            self.session.add(permission_group)
            self.session.commit()
        except Exception as e:
            logging.error("Error: %s" % e)
            self.session.rollback()

    def get_permissions(self, username):
        """Gets the permissions for a user

        :param username: The user
        :type username: str, models.User
        :returns: dict -- a dict of the permissions for that user
        """
        user = self.get_user(username)
        permissions = user.permissions.dict
        return permissions


class WebserverExport:
    """Accountant functions that are exposed to the webserver

    """
    def __init__(self, accountant):
        self.accountant = accountant

    @export
    def place_order(self, order):
        return self.accountant.place_order(order)

    @export
    def cancel_order(self, order_id, username=None):
        return self.accountant.cancel_order(order_id, username=username)

    @export
    def get_permissions(self, username):
        return self.accountant.get_permissions(username)

    @export
    def get_audit(self):
        return self.accountant.get_audit()

    @export
    def get_transaction_history(self, username, from_timestamp, to_timestamp):
        return self.accountant.get_transaction_history(username, from_timestamp, to_timestamp)

    @export
    def request_withdrawal(self, username, ticker, amount, address):
        return self.accountant.request_withdrawal(username, ticker, amount, address)


class EngineExport:
    """Accountant functions exposed to the Engine

    """
    def __init__(self, accountant):
        self.accountant = accountant

    @export
    def safe_prices(self, ticker, price):
        self.accountant.safe_prices[ticker] = price

    @export
    def post_transaction(self, transaction):
        self.accountant.post_transaction(transaction)


class CashierExport:
    """Accountant functions exposed to the cashier

    """
    def __init__(self, accountant):
        self.accountant = accountant

    @export
    def deposit_cash(self, address, received, total=True):
        self.accountant.deposit_cash(address, received, total=total)

    @export
    def transfer_position(self, ticker, from_user, to_user, quantity, note):
        self.accountant.transfer_position(ticker, from_user, to_user, quantity, note)

    @export
    def get_position(self, username, ticker):
        position = self.accountant.get_position(username, ticker)
        return position.position


class AdministratorExport:
    """Accountant functions exposed to the administrator

    """
    def __init__(self, accountant):
        self.accountant = accountant

    @export
    def adjust_position(self, username, ticker, quantity):
        self.accountant.adjust_position(username, ticker, quantity)

    @export
    def transfer_position(self, ticker, from_user, to_user, quantity, note):
        self.accountant.transfer_position(ticker, from_user, to_user, quantity, note)

    @export
    def get_balance_sheet(self):
        return self.accountant.get_balance_sheet()

    @export
    def change_permission_group(self, username, id):
        self.accountant.change_permission_group(username, id)

    @export
    def new_permission_group(self, name, permissions):
        self.accountant.new_permission_group(name, permissions)

    @export
    def deposit_cash(self, address, received, total=True):
        self.accountant.deposit_cash(address, received, total=total)

if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s', level=logging.DEBUG)

    session = database.make_session()
    engines = {}
    engine_base_port = config.getint("engine", "base_port")
    for contract in session.query(models.Contract).filter_by(active=True).all():
        engines[contract.ticker] = dealer_proxy_async("tcp://127.0.0.1:%d" %
                                                      (engine_base_port + int(contract.id)))
    ledger = dealer_proxy_sync(config.get("ledger", "accountant_export"))
    webserver = push_proxy_sync(config.get("webserver", "accountant_export"))
    cashier = push_proxy_sync(config.get("cashier", "accountant_export"))
    alerts_proxy = AlertsProxy(config.get("alerts", "export"))
    debug = config.getboolean("accountant", "debug")
    trial_period = config.getboolean("accountant", "trial_period")

    accountant = Accountant(session, engines, cashier, ledger, webserver, alerts_proxy,
                            debug=debug,
                            trial_period=trial_period)

    webserver_export = WebserverExport(accountant)
    engine_export = EngineExport(accountant)
    cashier_export = CashierExport(accountant)
    administrator_export = AdministratorExport(accountant)

    watchdog(config.get("watchdog", "accountant"))

    router_share_async(webserver_export,
                       config.get("accountant", "webserver_export"))
    pull_share_async(engine_export,
                     config.get("accountant", "engine_export"))
    router_share_async(cashier_export,
                        config.get("accountant", "cashier_export"))
    router_share_async(administrator_export,
                     config.get("accountant", "administrator_export"))

    reactor.run()

