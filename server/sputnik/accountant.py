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
    dealer_proxy_sync, push_proxy_async, RemoteCallTimedOut, RemoteCallException

from twisted.internet import reactor, defer
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import DataError
from datetime import datetime, date
from watchdog import watchdog

import logging
import time
import uuid

class AccountantException(Exception):
    pass

INSUFFICIENT_MARGIN = AccountantException(0, "Insufficient margin")
TRADE_NOT_PERMITTED = AccountantException(1, "Trading not permitted")
WITHDRAW_NOT_PERMITTED = AccountantException(2, "Withdrawals not permitted")
INVALID_CURRENCY_QUANTITY = AccountantException(3, "Invalid currency quantity")

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
        def on_success(result):
            try:
                for posting in postings:
                    position = self.get_position(posting['username'], posting['contract'])
                    user = self.get_user(posting['username'])
                    if posting['direction'] is 'debit':
                        if user.type == 'Asset':
                            sign = 1
                        else:
                            sign = -1
                    else:
                        if user.type == 'Asset':
                            sign = -1
                        else:
                            sign = 1

                    position.position += sign * posting['quantity']
                    self.session.merge(position)
                self.session.commit()
            finally:
                self.session.rollback()

        def on_fail_ledger(failure):
            e = failure.trap(ledger.LedgerException)
            logging.error("Ledger exception:")
            logging.error(str(failure.value))
            self.alerts_proxy.send_alert("Exception in ledger. See logs.")
            raise e

        def on_fail_rpc(failure):
            e = failure.trap(RemoteCallException)
            if isinstance(e, RemoteCallTimedOut):
                logging.error("Ledger call timed out.")
                self.alerts_proxy.send_alert("Ledger call timed out. Ledger may be overloaded.")
            else:
                logging.error("Improper ledger RPC invocation:")
                logging.error(str(failure.value))
            raise e

        def publish_transactions(result):
            for posting in postings:
                transaction = {'contract': posting['contract'],
                          'timestamp': posting['timestamp'],
                          'quantity': posting['quantity'],
                          'type': posting['type'],
                          'direction': posting['direction']
                }
                self.webserver.transaction(posting['username'], transaction)

        d = self.ledger.post(*postings)
        d.addCallback(on_success).addCallback(publish_transactions)
        d.addErrback(on_fail_ledger)
        d.addErrback(on_fail_rpc)
        return d

    # This will go away once everything starts using post_or_fail
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

        uid = util.get_uid()
        d1 = self.transfer_position(username, ticker, 'credit', quantity, 'Adjustment', uid)
        d2 = self.transfer_position('adjustments', ticker, 'debit', quantity, None, uid)
        return defer.DeferredList([d1, d2])

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
        user_postings = []
        vendor_postings = []
        remainder_postings = []
        last = time.time()
        user = self.get_user(user)

        for ticker, fee in fees.iteritems():
            contract = self.get_contract(ticker)

            # Debit the fee from the user's account
            user_posting = ledger.create_posting("Trade", user.username,
                    contract.ticker, fee, 'debit')
            user_postings.append(user_posting)

            remaining_fee = fee
            for vendor_name, vendor_share in self.vendor_share_config.iteritems():
                vendor_user = self.get_user(vendor_name)
                vendor_credit = int(fee * vendor_share)

                remaining_fee -= vendor_credit

                # Credit the fee to the vendor's account
                vendor_posting = ledger.create_posting("Trade",
                        vendor_user.username, contract.ticker, vendor_credit,
                        'credit')
                vendor_postings.append(vendor_posting)

            # There might be some fee leftover due to rounding,
            # we have an account for that guy
            # Once that balance gets large we distribute it manually to the
            # various share holders
            remainder_user = self.get_user('remainder')
            remainder_posting = ledger.create_posting("Trade",
                    remainder_user.username, contract.ticker, remaining_fee,
                    'credit')
            remainder_postings.append(remainder_posting)
            next = time.time()
            elapsed = (next - last) * 1000
            last = next
            logging.debug("charge_fees: %s: %.3f ms." % (ticker, elapsed))

        return user_postings, vendor_postings, remainder_postings



    def post_transaction(self, transaction):
        """Update the database to reflect that the given trade happened. Charge fees.

        :param transaction: the transaction object
        :type transaction: dict
        """
        logging.info("Processing transaction %s." % transaction)
        last = time.time()

        username = transaction["username"]
        aggressive = transaction["aggressive"]
        ticker = transaction["contract"]
        order = transaction["order"]
        side = transaction["side"]
        price = transaction["price"]
        quantity = transaction["quantity"]
        timestamp = transaction["timestamp"]
        uid = transaction["uid"]

        contract = self.get_contract(ticker)
        user = self.get_user(username)

        next = time.time()
        elapsed = (next - last) * 1000
        last = next
        logging.debug("post_transaction: part 1: %.3f ms." % elapsed)

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
                # TODO: abort?

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
                # TODO: abort?
        else:
            logging.error("Unknown contract type '%s'." %
                          contract.contract_type)
            raise NotImplementedError

        next = time.time()
        elapsed = (next - last) * 1000
        last = next
        logging.debug("post_transaction: part 2: %.3f ms." % elapsed)

        if side == "BUY":
            denominated_direction = "debit"
            payout_direction = "credit"
        else:
            denominated_direction = "credit"
            payout_direction = "debit"

        if aggressive:
            ap = "aggressive"
        else:
            ap = "passive"

        note = "{%s order: %s}" % (ap, order)

        user_denominated = ledger.create_posting("Trade", user,
                denominated_contract, cash_spent_int, denominated_direction,
                note)
        user_payout = ledger.create_posting("Trade", user, payout_contract,
                quantity, payout_direction, note)

        # calculate fees
        # We aren't charging the liquidity provider
        fees = {}
        fees = util.get_fees(username, contract,
                abs(cash_spent_int), trial_period=self.trial_period)
        if not aggressive:
            for fee in fees:
                fees[fee] = 0

        user_fees, vendor_fees, remainder_fees = self.charge_fees(fees, user)

        next = time.time()
        elapsed = (next - last) * 1000
        logging.debug("post_transaction: part 3: %.3f ms." % elapsed)

        # Submit to ledger
        # (user denominated, user payout, remainder) x 2 = 6
        count = 6 + 2 * len(user_fees) + 2 * len(vendor_fees)
        postings = [user_denominated, user_payout]
        postings.extend(user_fees,)
        postings.extend(vendor_fees)
        postings.extend(remainder_fees)

        for posting in postings:
            posting["count"] = count
            posting["uid"] = uid

        d = self.post_or_fail(*postings)
        
        def notify_fill(result):
            last = time.time()
            # Send notifications
            fill = {'contract': ticker,
                    'id': order,
                    'quantity': quantity,
                    'price': price,
                    'side': side,
                    'timestamp': timestamp,
                    'fees': fees
                   }
            self.webserver.fill(username, fill)
            logging.debug('to ws: ' + str({"fills": [username, fill]}))

            next = time.time()
            elapsed = (next - last) * 1000
            logging.debug("post_transaction: part 6: %.3f ms." % elapsed)

        d.addCallback(notify_fill)
        return d

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

    def transfer_position(self, username, ticker, direction, quantity, note, uid):
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
        posting = ledger.create_posting("Transfer", username, ticker, quantity,
                direction, note)
        posting['count'] = 2
        posting['uid'] = uid
        d = self.post_or_fail(posting)
        return d

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
            contract = self.get_contract(ticker)

            if self.trial_period:
                logging.error("Withdrawals not permitted during trial period")
                raise WITHDRAW_NOT_PERMITTED

            logging.debug("Withdrawal request for %s %s for %d to %s received" % (username, ticker, amount, address))
            user = self.get_user(username)
            if not user.permissions.withdraw:
                logging.error("Withdraw request for %s failed due to no permissions" % username)
                raise WITHDRAW_NOT_PERMITTED

            if amount % contract.lot_size != 0:
                logging.error("Withdraw request for a wrong lot_size qty: %d" % amount)
                raise INVALID_CURRENCY_QUANTITY

            uid = util.get_uid()
            credit_posting = ledger.create_posting("Withdrawal",
                    'pendingwithdrawal', ticker, amount, 'credit', note=address)
            credit_posting['uid'] = uid
            credit_posting['count'] = 2
            debit_posting = ledger.create_posting("Withdrawal", user.username,
                    ticker, amount, 'debit')
            debit_posting['uid'] = uid
            debit_posting['count'] = 2

            # Check margin now
            low_margin, high_margin = margin.calculate_margin(username,
                    self.session, self.safe_prices,
                    withdrawals={ticker:amount},
                    trial_period=self.trial_period)
            if not self.check_margin(username, low_margin, high_margin):
                logging.info("Insufficient margin for withdrawal %d / %d" % (low_margin, high_margin))
                raise INSUFFICIENT_MARGIN
            else:
                d = self.post_or_fail(credit_posting, debit_posting)
                def onSuccess(result):
                    self.cashier.request_withdrawal(username, ticker, address, amount)
                    return True

                d.addCallback(onSuccess)
                return d
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

            # compute deposit _before_ marking amount as accounted for
            if total:
                deposit = received - total_deposited_at_address.accounted_for
                total_deposited_at_address.accounted_for = received
            else:
                deposit = received
                total_deposited_at_address.accounted_for += deposit

            # update address
            self.session.add(total_deposited_at_address)
            self.session.commit()

            #prepare cash deposit
            postings = []
            debit_posting = ledger.create_posting("Deposit", 'onlinecash',
                                                  contract.ticker,
                                                  deposit,
                                                  'debit',
                                                  note=address)
            postings.append(debit_posting)

            credit_posting = ledger.create_posting("Deposit", user.username,
                                                   contract.ticker,
                                                   deposit,
                                                   'credit')
            postings.append(credit_posting)

            if total_deposited_at_address.contract.ticker in self.deposit_limits:
                deposit_limit = self.deposit_limits[total_deposited_at_address.contract.ticker]
            else:
                deposit_limit = float("inf")

            potential_new_position = user_cash_position.position + deposit
            excess_deposit = 0
            if not user.permissions.deposit:
                logging.error("Deposit of %d failed for address=%s because user %s is not permitted to deposit" %
                              (deposit, address, user.username))

                # The user's not permitted to deposit at all. The excess deposit is the entire value
                excess_deposit = deposit
            elif potential_new_position > deposit_limit:
                logging.error("Deposit of %d failed for address=%s because user %s exceeded deposit limit=%d" %
                              (deposit, address, total_deposited_at_address.username, deposit_limit))
                excess_deposit = potential_new_position - deposit_limit

            if excess_deposit > 0:
                # There was an excess deposit, transfer that amount into overflow cash
                excess_debit_posting = ledger.create_posting("Deposit",
                        user.username, contract.ticker, excess_deposit,
                        'debit', note="Excess Deposit")

                excess_credit_posting = ledger.create_posting("Deposit",
                        'depositoverflow', contract.ticker, excess_deposit,
                        'credit')

                postings.append(excess_debit_posting)
                postings.append(excess_credit_posting)

            count = len(postings)
            uid = util.get_uid()
            for posting in postings:
                posting['count'] = count
                posting['uid'] = uid

            d = self.post_or_fail(*postings)
            return d
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

#    def get_transaction_history(self, username, from_timestamp, to_timestamp):
#        """Get the history of a user's transactions
#
#        :param username: the user
#        :type username: str, models.User
#        :param from_timestamp: Starting time
#        :type from_timestamp: int
#        :param end_timestamp: Ending time
#        :type end_timestamp: int
#        :returns: list -- an array of ledger entries
#        """
#
#        from_dt = util.timestamp_to_dt(from_timestamp)
#        to_dt = util.timestamp_to_dt(to_timestamp)
#
#        transactions = []
#        postings = self.session.query(models.Posting).filter_by(username=username).join(models.Journal).filter(
#            models.Journal.timestamp <= to_dt,
#            models.Journal.timestamp >= from_dt
#        )
#        for posting in postings:
#            transactions.append({'contract': posting.contract.ticker,
#                            'timestamp': util.dt_to_timestamp(posting.journal.timestamp),
#                            'quantity': posting.quantity,
#                            'type': posting.journal.type})
#        return transactions

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
        return self.accountant.post_transaction(transaction)


class CashierExport:
    """Accountant functions exposed to the cashier

    """
    def __init__(self, accountant):
        self.accountant = accountant

    @export
    def deposit_cash(self, address, received, total=True):
        return self.accountant.deposit_cash(address, received, total=total)

    @export
    def transfer_position(self, username, ticker, direction, quantity, note, uid):
        return self.accountant.transfer_position(username, ticker, direction, quantity, note, uid)

    @export
    def get_position(self, username, ticker):
        position = self.accountant.get_position(username, ticker)
        return position.position

class AccountantExport:
    """Accountant private chit chat link

    """
    def __init__(self, accountant):
        self.accountant = accountant

    @export
    def remote_post(self, *postings):
        self.accountant.post_or_fail(*postings)
        # we do not want or need this to propogate back to the caller
        return None


class AdministratorExport:
    """Accountant functions exposed to the administrator

    """
    def __init__(self, accountant):
        self.accountant = accountant

    @export
    def adjust_position(self, username, ticker, quantity):
        return self.accountant.adjust_position(username, ticker, quantity)

    @export
    def transfer_position(self, username, ticker, direction, quantity, note, uid):
        return self.accountant.transfer_position(username, ticker, direction, quantity, note, uid)

    @export
    def change_permission_group(self, username, id):
        self.accountant.change_permission_group(username, id)

    @export
    def new_permission_group(self, name, permissions):
        self.accountant.new_permission_group(name, permissions)

    @export
    def deposit_cash(self, address, received, total=True):
        self.accountant.deposit_cash(address, received, total=total)

class AccountantProxy:
    def __init__(self, mode, uri, base_port):
        self.num_procs = config.getint("accountant", "num_procs")
        self.proxies = []
        for i in range(self.num_procs):
            if mode == "dealer":
                proxy = dealer_proxy_async(uri % (base_port + i))
            elif mode == "push":
                proxy = push_proxy_async(uri % (base_port + i))
            else:
                raise Exception("Unsupported proxy mode: %s." % mode)
            self.proxies.append(proxy)

    def __getattr__(self, key):
        if key.startswith("__") and key.endswith("__"):
            raise AttributeError

        def routed_method(username, *args, **kwargs):
            proxy = self.proxies[ord(username[0]) % self.num_procs]
            return getattr(proxy, key)(*args, **kwargs)

        return routed_method

if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s', level=logging.DEBUG)
    accountant_number = args[0]
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
                       config.get("accountant", "webserver_export") %
                       (config.getint("accountant", "webserver_export_base_port") + accountant_number))
    pull_share_async(engine_export,
                     config.get("accountant", "engine_export") %
                     (config.getint("accountant", "engine_export_base_port") + accountant_number))
    router_share_async(cashier_export,
                        config.get("accountant", "cashier_export") %
                        (config.getint("accountant", "cashier_export_base_port") + accountant_number))
    router_share_async(administrator_export,
                     config.get("accountant", "administrator_export") %
                     (config.getint("accountant", "administrator_export_base_port") + accountant_number))

    reactor.run()

