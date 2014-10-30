#!/usr/bin/env python
"""
.. module:: accountant

The accountant is responsible for user-specific data, except for login sorts of data, which are managed by the
administrator. It is responsible for the following:

* models.Position
* models.PermissionGroup

"""

import config
import sys
from rpc_schema import schema

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
import ledger
from alerts import AlertsProxy

from ledger import create_posting

from zmq_util import export, dealer_proxy_async, router_share_async, pull_share_async, \
    push_proxy_async, RemoteCallTimedOut, RemoteCallException, ComponentExport

from twisted.internet import reactor
from twisted.internet import reactor, defer, task
from twisted.python import log
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import SQLAlchemyError
from watchdog import watchdog

import time
from datetime import datetime

class AccountantException(Exception):
    pass

INSUFFICIENT_MARGIN = AccountantException(0, "Insufficient margin")
TRADE_NOT_PERMITTED = AccountantException(1, "Trading not permitted")
WITHDRAW_NOT_PERMITTED = AccountantException(2, "Withdrawals not permitted")
INVALID_CURRENCY_QUANTITY = AccountantException(3, "Invalid currency quantity")
DISABLED_USER = AccountantException(4, "Account disabled. Please try again in five minutes.")
CONTRACT_EXPIRED = AccountantException(5, "Contract expired")
CONTRACT_NOT_EXPIRED = AccountantException(6, "Contract not expired")
NON_CLEARING_CONTRACT = AccountantException(7, "Contract not clearable")
CONTRACT_NOT_ACTIVE = AccountantException(8, "Contract not active")

class Accountant:
    """The Accountant primary class

    """
    def __init__(self, session, engines, cashier, ledger, webserver, accountant_proxy,
                 alerts_proxy, accountant_number=0, debug=False, trial_period=False,
                 mimetic_share=0.5):
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
        self.vendor_share_config = { 'm2': mimetic_share,
                                     'customer': 1.0-mimetic_share
        }
        self.safe_prices = {}
        self.engines = engines
        self.ledger = ledger
        self.cashier = cashier
        self.accountant_proxy = accountant_proxy
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
                log.msg(
                    "warning, missing last trade for contract: %s. Using 42 as a stupid default" % contract.ticker)
                self.safe_prices[contract.ticker] = 42

        self.webserver = webserver
        self.disabled_users = {}
        self.accountant_number = accountant_number

    def post_or_fail(self, *postings):
        # This is the core ledger communication method.
        # Posting happens as follows:
        # 1. All affected positions have a counter incremented to keep track of
        #    pending postings.
        # 2. The ledger's RPC post() is invoked.
        # 3. When the call returns, the position counters are decremented. This
        #    happens whether or not there was an error.
        # 4a. If there was no error, positions are updated and the webserver is
        #     notified.
        # 4b. If there was an error, an effort is made to determine what caused
        #     it. If the error was severe, send_alert() is called to let us
        #     know. In all cases, the error is propogated downstream to let
        #     whoever called post_or_fail know that the post was not successful.
        # Note: It is *important* that all invocations of post_or_fail attach
        #       an errback (even if it is just log.err) to catch the
        #       propogating error.

        def update_counters(increment=False):
            change = 1 if increment else -1

            try:
                for posting in postings:
                    position = self.get_position(
                            posting['username'], posting['contract'])
                    position.pending_postings += change
                    # make sure the position exists
                    self.session.add(position)
                self.session.commit()
            except SQLAlchemyError, e:
                log.err("Could not update counters: %s" % e)
                self.alerts_proxy.send_alert("Exception in ledger. See logs.")
                self.session.rollback()
            finally:
                self.session.rollback()

        def on_success(result):
            log.msg("Post success: %s" % result)
            try:
                for posting in postings:
                    position = self.get_position(posting['username'], posting['contract'])
                    user = self.get_user(posting['username'])
                    if posting['direction'] == 'debit':
                        sign = 1 if user.type == 'Asset' else -1
                    else:
                        sign = -1 if user.type == 'Asset' else 1

                    log.msg("Adjusting position %s by %d %s" % (position, posting['quantity'], posting['direction']))
                    position.position += sign * posting['quantity']
                    log.msg("New position: %s" % position)
                    #self.session.merge(position)
                self.session.commit()
            finally:
                self.session.rollback()

        def on_fail_ledger(failure):
            e = failure.trap(ledger.LedgerException)
            log.err("Ledger exception:")
            log.err(failure.value)
            self.alerts_proxy.send_alert("Exception in ledger. See logs.")
            # propogate error downstream
            return failure

        def on_fail_rpc(failure):
            e = failure.trap(RemoteCallException)
            if isinstance(failure.value, RemoteCallTimedOut):
                log.err("Ledger call timed out.")
                self.alerts_proxy.send_alert("Ledger call timed out. Ledger may be overloaded.")
            else:
                log.err("Improper ledger RPC invocation:")
                log.err(failure)
            # propogate error downstream
            return failure

        def on_fail_other(failure):
            log.err("Error in processing posting result. This should be handled downstream.")
            log.err(failure)
            # propogate error downstream
            return failure

        def publish_transactions(result):
            for posting in postings:
                transaction = {'contract': posting['contract'],
                          'timestamp': posting['timestamp'],
                          'quantity': posting['quantity'],
                          'type': posting['type'],
                          'direction': posting['direction'],
                          'note': posting['note']
                }
                self.webserver.transaction(posting['username'], transaction)

        def decrement_counters(result):
            update_counters(increment=False)
            return result

        update_counters(increment=True)

        d = self.ledger.post(*postings)

        d.addBoth(decrement_counters)
        d.addCallback(on_success).addCallback(publish_transactions)
        d.addErrback(on_fail_ledger).addErrback(on_fail_rpc)

        # Just in case there are no error handlers downstream, log any leftover
        # errors here.
        d.addErrback(on_fail_other)

        return d

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
        try:
            return util.get_contract(self.session, ticker)
        except:
            raise AccountantException("No such contract: '%s'." % ticker)

    def adjust_position(self, username, ticker, quantity, admin_username):
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
        credit = create_posting("Transfer", username, ticker, quantity,
                "credit", "Adjustment (%s)" % admin_username)
        debit = create_posting("Transfer", "adjustments", ticker, quantity,
                "debit", "Adjustment (%s)" % admin_username)
        credit["count"] = 2
        debit["count"] = 2
        credit["uid"] = uid
        debit["uid"] = uid
        return self.post_or_fail(credit, debit).addErrback(log.err)

    def get_position_value(self, username, ticker):
        """Return the numeric value of a user's position for a contact. If it does not exist, return 0.

        :param username: the username
        :type username: str, models.User
        :param ticker: the contract
        :type ticker: str, models.User
        :returns: int -- the position value
        """
        user = self.get_user(username)
        contract = self.get_contract(ticker)
        try:
            return self.session.query(models.Position).filter_by(
                user=user, contract=contract).one().position
        except NoResultFound:
            return 0

    def get_position(self, username, ticker, reference_price=0):
        """Return a user's position for a contact. If it does not exist, initialize it. WARNING: If a position is created, it will be added to the session.

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
            log.msg("Creating new position for %s on %s." %
                          (username, contract))
            position = models.Position(user, contract)
            position.reference_price = reference_price
            self.session.add(position)
            return position

    def check_margin(self, username, low_margin, high_margin):
        cash = self.get_position_value(username, "BTC")

        log.msg("high_margin = %d, low_margin = %d, cash_position = %d" %
                     (high_margin, low_margin, cash))

        if high_margin > cash:
            return False
        else:
            return True

    def accept_order(self, order):
        """Accept the order if possible. Otherwise, delete the order

        :param order: Order object we wish to accept
        :type order: models.Order
        :raises: INSUFFICIENT_MARGIN, TRADE_NOT_PERMITTED
        """
        log.msg("Trying to accept order %s." % order)

        user = order.user

        # Audit the user
        if not self.is_user_enabled(user):
            log.msg("%s user is disabled" % user.username)
            try:
                self.session.delete(order)
                self.session.commit()
            except:
                self.alerts_proxy.send_alert("Could not remove order: %s" % order)
            finally:
                self.session.rollback()
            raise DISABLED_USER

        if not user.permissions.trade:
            log.msg("order %s not accepted because user %s not permitted to trade" % (order.id, user.username))
            try:
                self.session.delete(order)
                self.session.commit()
            except:
                self.alerts_proxy.send_alert("Could not remove order: %s" % order)
            finally:
                self.session.rollback()
            raise TRADE_NOT_PERMITTED

        # Make sure there is a position in the contract, if it is not a cash_pair
        # cash_pairs don't have positions
        if order.contract.contract_type != "cash_pair":
            try:
                position = self.get_position(order.username, order.contract)
                # this should be unnecessary, but just in case
                self.session.add(position)
                self.session.commit()
            except Exception, e:
                self.session.rollback()
                log.err(e)
                log.err("Could not initialize position %s for %s." % (order.contract.ticker, user.username))
                self.alerts_proxy.send_alert("Could not initialize position %s for %s." % (order.contract.ticker, user.username))
                #TODO: DO NOT INITIALIZE POSITION HERE

        user = self.get_user(order.username)
        low_margin, high_margin, max_cash_spent = margin.calculate_margin(
            user, self.session, self.safe_prices, order.id,
            trial_period=self.trial_period)

        if self.check_margin(order.username, low_margin, high_margin):
            log.msg("Order accepted.")
            order.accepted = True
            try:
                # self.session.merge(order)
                self.session.commit()
            except:
                self.alerts_proxy.send_alert("Could not merge order: %s" % order)
            finally:
                self.session.rollback()
        else:
            log.msg("Order rejected due to margin.")
            try:
                self.session.delete(order)
                self.session.commit()
            except:
                self.alerts_proxy.send_alert("Could not remove order: %s" % order)
            finally:
                self.session.rollback()
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
            user_posting = create_posting("Trade", user.username,
                    contract.ticker, fee, 'debit', note="Fee")
            user_postings.append(user_posting)

            remaining_fee = fee
            for vendor_name, vendor_share in self.vendor_share_config.iteritems():
                vendor_user = self.get_user(vendor_name)
                vendor_credit = int(fee * vendor_share)

                remaining_fee -= vendor_credit

                # Credit the fee to the vendor's account
                vendor_posting = create_posting("Trade",
                        vendor_user.username, contract.ticker, vendor_credit,
                        'credit', note="Vendor Credit")
                vendor_postings.append(vendor_posting)

            # There might be some fee leftover due to rounding,
            # we have an account for that guy
            # Once that balance gets large we distribute it manually to the
            # various share holders
            remainder_user = self.get_user('remainder')
            remainder_posting = create_posting("Trade",
                    remainder_user.username, contract.ticker, remaining_fee,
                    'credit')
            remainder_postings.append(remainder_posting)
            next = time.time()
            elapsed = (next - last) * 1000
            last = next
            log.msg("charge_fees: %s: %.3f ms." % (ticker, elapsed))

        return user_postings, vendor_postings, remainder_postings

    def get_cash_spent(self, contract, price, quantity):
        if contract.contract_type == "futures":
            raise NotImplementedError

            # log.msg("This is a futures trade.")
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
                log.err(message)
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
                log.err(message)
                self.alerts_proxy.send_alert(message, "Integer failure")
                # TODO: abort?
        else:
            log.err("Unknown contract type '%s'." %
                          contract.contract_type)
            raise NotImplementedError

        return denominated_contract, payout_contract, cash_spent_int

    def post_transaction(self, username, transaction):
        """Update the database to reflect that the given trade happened. Charge fees.

        :param transaction: the transaction object
        :type transaction: dict
        """
        log.msg("Processing transaction %s." % transaction)
        last = time.time()
        if username != transaction["username"]:
            raise RemoteCallException("username does not match transaction")

        aggressive = transaction["aggressive"]
        ticker = transaction["contract"]
        order = transaction["order"]
        other_order = transaction["other_order"]
        side = transaction["side"]
        price = transaction["price"]
        quantity = transaction["quantity"]
        timestamp = transaction["timestamp"]
        uid = transaction["uid"]

        contract = self.get_contract(ticker)
        if not contract.active:
            raise CONTRACT_NOT_ACTIVE


        user = self.get_user(username)

        next = time.time()
        elapsed = (next - last) * 1000
        last = next
        log.msg("post_transaction: part 1: %.3f ms." % elapsed)

        denominated_contract, payout_contract, cash_spent = self.get_cash_spent(contract, price, quantity)

        next = time.time()
        elapsed = (next - last) * 1000
        last = next
        log.msg("post_transaction: part 2: %.3f ms." % elapsed)

        if side == "BUY":
            denominated_direction = "debit"
            payout_direction = "credit"
        else:
            denominated_direction = "credit"
            payout_direction = "debit"

        if aggressive:
            ap = "Aggressive"
        else:
            ap = "Passive"

        note = "%s order: %s" % (ap, order)

        user_denominated = create_posting("Trade", username,
                denominated_contract.ticker, cash_spent, denominated_direction,
                note)
        user_payout = create_posting("Trade", username, payout_contract.ticker,
                quantity, payout_direction, note)

        # calculate fees
        fees = util.get_fees(user, contract,
                abs(cash_spent), trial_period=self.trial_period, ap="aggressive" if aggressive else "passive")

        user_fees, vendor_fees, remainder_fees = self.charge_fees(fees, user)

        next = time.time()
        elapsed = (next - last) * 1000
        log.msg("post_transaction: part 3: %.3f ms." % elapsed)

        # Submit to ledger
        # (user denominated, user payout) x 2 = 4
        count = 4 + 2 * len(remainder_fees) + 2 * len(user_fees) + 2 * len(vendor_fees)
        postings = [user_denominated, user_payout]
        postings.extend(user_fees)
        #postings.extend(vendor_fees)
        #postings.extend(remainder_fees)


        for posting in postings + vendor_fees + remainder_fees:
            posting["count"] = count
            posting["uid"] = uid


        for fee in vendor_fees:
            self.accountant_proxy.remote_post(fee["username"], fee)

        if len(remainder_fees):
            self.accountant_proxy.remote_post("remainder", *remainder_fees)

        if aggressive:
            try:
                aggressive_order = self.session.query(models.Order).filter_by(id=order).one()
                passive_order = self.session.query(models.Order).filter_by(id=other_order).one()

                trade = models.Trade(aggressive_order, passive_order, price, quantity)
                self.session.add(trade)
                self.session.commit()
                log.msg("Trade saved to db with posted=false: %s" % trade)
            except Exception as e:
                self.session.rollback()
                log.err("Exception while creating trade: %s" % e)

        d = self.post_or_fail(*postings)

        def update_order(result):
            try:
                db_order = self.session.query(models.Order).filter_by(id=order).one()
                db_order.quantity_left -= quantity
                # self.session.add(db_order)
                self.session.commit()
                log.msg("Updated order: %s" % db_order)
            except Exception as e:
                self.session.rollback()
                log.err("Unable to update order: %s" % e)

            self.webserver.order(username, db_order.to_webserver())
            log.msg("to ws: " + str({"order": [username, db_order.to_webserver()]}))
            return result

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
            log.msg('to ws: ' + str({"fills": [username, fill]}))

            next = time.time()
            elapsed = (next - last) * 1000
            log.msg("post_transaction: notify_fill: %.3f ms." % elapsed)

        def publish_trade(result):
            try:
                trade.posted = True
                # self.session.add(trade)
                self.session.commit()
                log.msg("Trade marked as posted: %s" % trade)
            except Exception as e:
                self.session.rollback()
                log.err("Exception when marking trade as posted %s" % e)

            self.webserver.trade(ticker, trade.to_webserver())
            log.msg("to ws: " + str({"trade": [ticker, trade.to_webserver()]}))
            return result

        # TODO: add errbacks for these
        d.addBoth(update_order)
        d.addCallback(notify_fill)
        if aggressive:
            d.addCallback(publish_trade)

        return d.addErrback(log.err)

    def raiseException(self, failure):
        raise failure.value

    def cancel_order(self, username, order_id):
        """Cancel an order by id.

        :param id: The order id to cancel
        :type id: int
        :returns: tuple -- (True/False, Result/Error)
        """
        log.msg("Received request to cancel order id %d." % order_id)

        try:
            order = self.session.query(models.Order).filter_by(id=order_id).one()
        except NoResultFound:
            raise AccountantException(0, "No order %d found" % order_id)

        if username is not None and order.username != username:
            raise AccountantException(0, "User %s does not own the order" % username)

        if order.is_cancelled:
            raise AccountantException(0, "Order %d is already cancelled" % order_id)

        d = self.engines[order.contract.ticker].cancel_order(order_id)

        def update_order(result):
            try:
                order.is_cancelled = True
                # self.session.add(order)
                self.session.commit()
            except Exception as e:
                self.session.rollback()
                log.err("Unable to commit order cancellation")
                raise e

            return result

        def publish_order(result):
            self.webserver.order(username, order.to_webserver())
            return result

        d.addCallback(update_order)
        d.addCallback(publish_order)
        d.addErrback(self.raiseException)
        return d

    def cancel_order_engine(self, username, id):
        log.msg("Received msg from engine to cancel order id %d" % id)

        try:
            order = self.session.query(models.Order).filter_by(id=id).one()
        except NoResultFound:
            raise AccountantException(0, "No order %d found" % id)

        if username is not None and order.username != username:
            raise AccountantException(0, "User %s does not own the order" % username)

        if order.is_cancelled:
            raise AccountantException(0, "Order %d is already cancelled" % id)

        order.is_cancelled = True
        try:
            # self.session.add(order)
            self.session.commit()
        except:
            self.alerts_proxy.send_alert("Could not merge cancelled order: %s" % order)
        finally:
            self.session.rollback()

        self.webserver.order(username, order.to_webserver())


    def place_order(self, username, order):
        """Place an order

        :param order: dictionary representing the order to be placed
        :type order: dict
        :returns: tuple -- (True/False, Result/Error)
        """
        user = self.get_user(order["username"])
        contract = self.get_contract(order["contract"])

        if not contract.active:
            raise CONTRACT_NOT_ACTIVE

        if contract.expired:
            raise CONTRACT_EXPIRED

        # do not allow orders for internally used contracts
        if contract.contract_type == 'cash':
            log.err("Webserver allowed a 'cash' contract!")
            raise AccountantException(0, "Not a valid contract type.")

        if order["price"] % contract.tick_size != 0 or order["price"] < 0 or order["quantity"] < 0:
            raise AccountantException(0, "invalid price or quantity")

        # case of predictions
        if contract.contract_type == 'prediction':
            if not 0 <= order["price"] <= contract.denominator:
                raise AccountantException(0, "invalid price or quantity")

        if contract.contract_type == "cash_pair":
            if not order["quantity"] % contract.lot_size == 0:
                raise AccountantException(0, "invalid price or quantity")

        o = models.Order(user, contract, order["quantity"], order["price"], order["side"].upper(),
                         timestamp=util.timestamp_to_dt(order['timestamp']))
        try:
            self.session.add(o)
            self.session.commit()
        except Exception as e:
            log.err("Error adding data %s" % e)
            self.session.rollback()
            raise e

        self.accept_order(o)
        d = self.engines[o.contract.ticker].place_order(o.to_matching_engine_order())

        def mark_order_dispatched(result):
            o.dispatched = True
            try:
                # self.session.add(o)
                self.session.commit()
            except:
                self.alerts_proxy.send_alert("Could not mark order as dispatched: %s" % o)
            finally:
                self.session.rollback()
            return result

        def publish_order(result):
            self.webserver.order(username, o.to_webserver())
            return result

        d.addErrback(self.raiseException)
        d.addCallback(mark_order_dispatched)
        d.addCallback(publish_order)

        return o.id

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
        posting = create_posting("Transfer", username, ticker, quantity,
                direction, note)
        posting['count'] = 2
        posting['uid'] = uid
        return self.post_or_fail(posting).addErrback(log.err)

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
                log.err("Withdrawals not permitted during trial period")
                raise WITHDRAW_NOT_PERMITTED

            log.msg("Withdrawal request for %s %s for %d to %s received" % (username, ticker, amount, address))
            user = self.get_user(username)
            if not user.permissions.withdraw:
                log.err("Withdraw request for %s failed due to no permissions" % username)
                raise WITHDRAW_NOT_PERMITTED

            if amount % contract.lot_size != 0:
                log.err("Withdraw request for a wrong lot_size qty: %d" % amount)
                raise INVALID_CURRENCY_QUANTITY

            uid = util.get_uid()
            credit_posting = create_posting("Withdrawal",
                    'pendingwithdrawal', ticker, amount, 'credit', note=address)
            credit_posting['uid'] = uid
            credit_posting['count'] = 2
            debit_posting = create_posting("Withdrawal", user.username,
                    ticker, amount, 'debit', note=address)
            debit_posting['uid'] = uid
            debit_posting['count'] = 2

            # Audit the user
            if not self.is_user_enabled(user):
                log.err("%s user is disabled" % user.username)
                raise DISABLED_USER

            # Check margin now
            low_margin, high_margin, max_cash_spent = margin.calculate_margin(user,
                    self.session, self.safe_prices,
                    withdrawals={ticker:amount},
                    trial_period=self.trial_period)
            if not self.check_margin(username, low_margin, high_margin):
                log.msg("Insufficient margin for withdrawal %d / %d" % (low_margin, high_margin))
                raise INSUFFICIENT_MARGIN
            else:
                self.accountant_proxy.remote_post('pendingwithdrawal', credit_posting)
                d = self.post_or_fail(debit_posting)
                def onSuccess(result):
                    self.cashier.request_withdrawal(username, ticker, address, amount)
                    return True

                d.addCallback(onSuccess)
                return d.addErrback(log.err)
        except Exception as e:
            self.session.rollback()
            log.err("Exception received while attempting withdrawal: %s" % e)
            raise e

    def deposit_cash(self, username, address, received, total=True, admin_username=None):
        """Deposits cash
        :param username: The username for this address
        :type username: str
        :param address: The address where the cash was deposited
        :type address: str
        :param received: how much total was received at that address
        :type received: int
        :param total: if True, then received is the total received on that address. If false, then received is just the most recent receipt
        :type total: bool
        """
        try:
            log.msg('received %d at %s - total=%s' % (received, address, total))

            #query for db objects we want to update

            total_deposited_at_address = self.session.query(models.Addresses).filter_by(address=address).one()
            contract = total_deposited_at_address.contract

            user_cash = self.get_position_value(total_deposited_at_address.username, contract.ticker)
            user = self.get_user(total_deposited_at_address.user)

            # compute deposit _before_ marking amount as accounted for
            if total:
                deposit = received - total_deposited_at_address.accounted_for
                total_deposited_at_address.accounted_for = received
            else:
                deposit = received
                total_deposited_at_address.accounted_for += deposit

            # update address
            # self.session.add(total_deposited_at_address)
            self.session.commit()

            #prepare cash deposit
            my_postings = []
            remote_postings = []
            if admin_username is not None:
                note = "%s (%s)" % (address, admin_username)
            else:
                note = address

            debit_posting = create_posting("Deposit", 'onlinecash',
                                                  contract.ticker,
                                                  deposit,
                                                  'debit',
                                                  note=note)
            remote_postings.append(debit_posting)

            credit_posting = create_posting("Deposit", user.username,
                                                   contract.ticker,
                                                   deposit,
                                                   'credit',
                                                   note=note)
            my_postings.append(credit_posting)

            if total_deposited_at_address.contract.ticker in self.deposit_limits:
                deposit_limit = self.deposit_limits[total_deposited_at_address.contract.ticker]
            else:
                deposit_limit = float("inf")

            potential_new_position = user_cash + deposit
            excess_deposit = 0
            if not user.permissions.deposit:
                log.err("Deposit of %d failed for address=%s because user %s is not permitted to deposit" %
                              (deposit, address, user.username))

                # The user's not permitted to deposit at all. The excess deposit is the entire value
                excess_deposit = deposit
            elif potential_new_position > deposit_limit:
                log.err("Deposit of %d failed for address=%s because user %s exceeded deposit limit=%d" %
                              (deposit, address, total_deposited_at_address.username, deposit_limit))
                excess_deposit = potential_new_position - deposit_limit

            if excess_deposit > 0:
                if admin_username is not None:
                    note = "Excess Deposit: %s (%s)" % (address, admin_username)
                else:
                    note = "Excess Deposit: %s" % address
                # There was an excess deposit, transfer that amount into overflow cash
                excess_debit_posting = create_posting("Deposit",
                        user.username, contract.ticker, excess_deposit,
                        'debit', note=note)

                excess_credit_posting = create_posting("Deposit",
                        'depositoverflow', contract.ticker, excess_deposit,
                        'credit', note=note)

                my_postings.append(excess_debit_posting)
                remote_postings.append(excess_credit_posting)

            count = len(remote_postings + my_postings)
            uid = util.get_uid()
            for posting in my_postings + remote_postings:
                posting['count'] = count
                posting['uid'] = uid

            d = self.post_or_fail(*my_postings)
            for posting in remote_postings:
                self.accountant_proxy.remote_post(posting['username'], posting)

            return d.addErrback(log.err)
        except Exception as e:
            self.session.rollback()
            log.err(
                "Updating user position failed for address=%s and received=%d: %s" % (address, received, e))

    def change_permission_group(self, username, id):
        """Changes a user's permission group to something different

        :param username: the user
        :type username: str, models.User
        :param id: the permission group id
        :type id: int
        """

        try:
            log.msg("Changing permission group for %s to %d" % (username, id))
            user = self.get_user(username)
            user.permission_group_id = id
            # self.session.add(user)
            self.session.commit()
        except Exception as e:
            log.err("Error: %s" % e)
            self.session.rollback()
   
    def disable_user(self, user):
        user = self.get_user(user)
        log.msg("Disabling user: %s" % user.username)
        self.cancel_user_orders(user)
        self.disabled_users[user.username] = True

    def enable_user(self, user):
        user = self.get_user(user)
        log.msg("Enabling user: %s" % user.username)
        if user.username in self.disabled_users:
            del self.disabled_users[user.username]

    def is_user_enabled(self, user):
        user = self.get_user(user)
        if user.username in self.disabled_users:
            return False
        else:
            return True

    def cancel_user_orders(self, user):
        user = self.get_user(user)
        orders = self.session.query(models.Order).filter_by(
            username=user.username).filter(
            models.Order.quantity_left>0).filter_by(
            is_cancelled=False
        )
        return self.cancel_many_orders(orders)

    def cancel_many_orders(self, orders):
        deferreds = []
        for order in orders:
            log.msg("Cancelling user %s order %d" % (order.username, order.id))
            d = self.cancel_order(order.username, order.id)

            def cancel_failure(failure):
                log.err(failure)
                # Try again?
                log.msg("Trying again-- Cancelling user %s order %d" % (order.username, order.id))
                d = self.cancel_order(order.username, order.id)
                d.addErrback(cancel_failure)
                return d

            d.addErrback(cancel_failure)
            deferreds.append(d)

        return defer.DeferredList(deferreds)

    def get_my_users(self):
        users = self.session.query(models.User)
        my_users = []
        for user in users:
            if self.accountant_number == self.accountant_proxy.get_accountant_for_user(user.username):
                my_users.append(user)

        return my_users

    def repair_user_positions(self):
        my_users = self.get_my_users()
        for user in my_users:
            log.msg("Checking user %s" % user.username)
            for position in user.positions:
                if position.pending_postings > 0:
                    self.repair_user_position(user)
                    return

        log.msg("All users checked")

    def repair_user_position(self, user):
        user = self.get_user(user)
        log.msg("Repairing position for %s" % user.username)
        self.disable_user(user)
        try:
            for position in user.positions:
                position.pending_postings = 0
                # self.session.add(position)
            self.session.commit()
        except:
            self.session.rollback()
            self.alerts_proxy.send_alert("User %s in trouble. Cannot correct position!" % user.username)
            # Admin intervention required. ABORT!
            return

        reactor.callLater(300, self.check_user, user)

    def check_user(self, user):
        user = self.get_user(user)
        clean = True
        try:
            for position in user.positions:
                if position.pending_postings == 0:
                    # position has settled, sync with ledger
                    position.position, position.cp_timestamp = util.position_calculated(position, self.session)
                    position.position_checkpoint = position.position
                    # self.session.add(position)
                else:
                    clean = False
            if clean:
                log.msg("Correcting positions for user %s: %s" % (user.username, user.positions))
                self.session.commit()
                self.enable_user(user)
            else:
                # don't both committing, we are not ready yet anyway
                log.msg("User %s still not clean" % user.username)
                self.session.rollback()
                reactor.callLater(300, self.check_user, user)
        except:
            self.session.rollback()
            self.alerts_proxy.send_alert("User %s in trouble. Cannot correct position!" % user.username)
            # Admin intervention required. ABORT!
            return

    def clear_contract(self, username, ticker, price, uid):
        contract = self.get_contract(ticker)

        if contract.expiration is None:
            raise NON_CLEARING_CONTRACT

        # TODO: If it's an early clearing, don't check for contract expiration
        if contract.expiration >= datetime.utcnow():
            raise CONTRACT_NOT_EXPIRED

        if contract.active:
            # Mark contract inactive
            try:
                contract.active = False
                # self.session.add(contract)
                self.session.commit()
            except Exception as e:
                self.session.rollback()
                log.err("Unable to mark contract inactive %s" % e)

        my_users = [user.username for user in self.get_my_users()]

        # Cancel orders
        orders = self.session.query(models.Order).filter_by(contract=contract).filter_by(is_cancelled=False).filter(
            models.Order.quantity_left > 0).filter(
            models.Order.username.in_(my_users))
        d = self.cancel_many_orders(orders)

        def after_cancellations(results):
            # Wait until all pending postings have gone through
            pending_postings = self.session.query(models.Position.pending_postings).filter_by(contract=contract).filter(
                models.Position.username.in_(my_users))
            if sum([row[0] for row in pending_postings]) > 0:
                d = task.deferLater(reactor, 300, self.after_cancellations, results)
            else:
                all_positions = self.session.query(models.Position).filter_by(contract=contract)
                position_count = all_positions.count()
                my_positions = all_positions.filter(models.Position.username.in_(my_users))
                results = [self.clear_position(position, price, position_count, uid) for position in my_positions]
                d = defer.DeferredList(results)

            return d

        d.addCallback(after_cancellations)
        return d

    def clear_position(self, position, price, position_count, uid):
        # We use position_calculated here to be sure we get the canonical position
        position_calculated, timestamp = util.position_calculated(position, self.session)
        denominated_contract, payout_contract, cash_spent = self.get_cash_spent(position.contract,
                                                                                price, position_calculated)

        note = "Clearing transaction for %s at %d" % (position.contract.ticker, price)
        credit = create_posting("Clearing", position.username,
                denominated_contract.ticker, cash_spent, 'credit',
                note)
        debit = create_posting("Clearing", position.username, payout_contract.ticker,
                position_calculated, 'debit', note)
        for posting in credit, debit:
            posting['count'] = position_count * 2
            posting['uid'] = uid

        return self.post_or_fail(credit, debit).addErrback(log.err)

    def reload_fee_group(self, id):
        group = self.session.query(models.FeeGroup).filter_by(id=id).one()
        self.session.expire(group)

    def change_fee_group(self, username, id):
        try:
            user = self.get_user(username)
            user.fee_group_id = id
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            raise e

class WebserverExport(ComponentExport):
    """Accountant functions that are exposed to the webserver

    """
    def __init__(self, accountant):
        self.accountant = accountant
        ComponentExport.__init__(self, accountant)

    @export
    @schema("rpc/accountant.webserver.json#place_order")
    def place_order(self, username, order):
        return self.accountant.place_order(username, order)

    @export
    @schema("rpc/accountant.webserver.json#cancel_order")
    def cancel_order(self, username, id):
        return self.accountant.cancel_order(username, id)

    @export
    @schema("rpc/accountant.webserver.json#request_withdrawal")
    def request_withdrawal(self, username, ticker, quantity, address):
        return self.accountant.request_withdrawal(username, ticker, quantity, address)


class EngineExport(ComponentExport):
    """Accountant functions exposed to the Engine

    """
    def __init__(self, accountant):
        self.accountant = accountant
        ComponentExport.__init__(self, accountant)

    @export
    def safe_prices(self, ticker, price):
        self.accountant.safe_prices[ticker] = price

    @export
    @schema("rpc/accountant.engine.json#post_transaction")
    def post_transaction(self, username, transaction):
        return self.accountant.post_transaction(username, transaction)

    @export
    @schema("rpc/accountant.engine.json#cancel_order")
    def cancel_order(self, username, id):
        return self.accountant.cancel_order_engine(username, id)


class CashierExport(ComponentExport):
    """Accountant functions exposed to the cashier

    """
    def __init__(self, accountant):
        self.accountant = accountant
        ComponentExport.__init__(self, accountant)

    @export
    @schema("rpc/accountant.cashier.json#deposit_cash")
    def deposit_cash(self, username, address, received, total=True):
        return self.accountant.deposit_cash(username, address, received, total=total)

    @export
    @schema("rpc/accountant.cashier.json#transfer_position")
    def transfer_position(self, username, ticker, direction, quantity, note, uid):
        return self.accountant.transfer_position(username, ticker, direction, quantity, note, uid)

    @export
    @schema("rpc/accountant.cashier.json#get_position")
    def get_position(self, username, ticker):
        return self.accountant.get_position_value(username, ticker)

class AccountantExport(ComponentExport):
    """Accountant private chit chat link

    """
    def __init__(self, accountant):
        self.accountant = accountant
        ComponentExport.__init__(self, accountant)

    @export
    @schema("rpc/accountant.accountant.json#remote_post")
    def remote_post(self, username, *postings):
        self.accountant.post_or_fail(*postings).addErrback(log.err)
        # we do not want or need this to propogate back to the caller
        return None


class AdministratorExport(ComponentExport):
    """Accountant functions exposed to the administrator

    """
    def __init__(self, accountant):
        self.accountant = accountant
        ComponentExport.__init__(self, accountant)

    @export
    @schema("rpc/accountant.administrator.json#adjust_position")
    def adjust_position(self, username, ticker, quantity, admin_username):
        return self.accountant.adjust_position(username, ticker, quantity, admin_username)

    @export
    @schema("rpc/accountant.administrator.json#transfer_position")
    def transfer_position(self, username, ticker, direction, quantity, note, uid):
        return self.accountant.transfer_position(username, ticker, direction, quantity, note, uid)

    @export
    @schema("rpc/accountant.administrator.json#change_permission_group")
    def change_permission_group(self, username, id):
        self.accountant.change_permission_group(username, id)

    @export
    @schema("rpc/accountant.administrator.json#deposit_cash")
    def deposit_cash(self, username, address, received, total=True, admin_username=None):
        self.accountant.deposit_cash(username, address, received, total=total, admin_username=admin_username)

    @export
    @schema("rpc/accountant.administrator.json#cancel_order")
    def cancel_order(self, username, id):
        return self.accountant.cancel_order(username, id)

    @export
    @schema("rpc/accountant.administrator.json#clear_contract")
    def clear_contract(self, username, ticker, price, uid):
        return self.accountant.clear_contract(username, ticker, price, uid)

    @export
    def change_fee_group(self, username, id):
        return self.accountant.change_fee_group(username, id)

    @export
    def reload_fee_group(self, username, id):
        return self.accountant.reload_fee_group(id)


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

    def get_accountant_for_user(self, username):
        return ord(username[0]) % self.num_procs

    def __getattr__(self, key):
        if key.startswith("__") and key.endswith("__"):
            raise AttributeError

        def routed_method(username, *args, **kwargs):
            if username is None:
                return [getattr(proxy, key)(None, *args, **kwargs) for proxy in self.proxies]
            else:
                proxy = self.proxies[self.get_accountant_for_user(username)]
                return getattr(proxy, key)(username, *args, **kwargs)

        return routed_method

if __name__ == "__main__":
    log.startLogging(sys.stdout)
    accountant_number = int(args[0])
    num_procs = config.getint("accountant", "num_procs")
    log.msg("Accountant %d of %d" % (accountant_number+1, num_procs))

    session = database.make_session()
    engines = {}
    engine_base_port = config.getint("engine", "accountant_base_port")
    for contract in session.query(models.Contract).filter_by(active=True).all():
        engines[contract.ticker] = dealer_proxy_async("tcp://127.0.0.1:%d" %
                                                      (engine_base_port + int(contract.id)))
    ledger = dealer_proxy_async(config.get("ledger", "accountant_export"), timeout=0)
    webserver = push_proxy_async(config.get("webserver", "accountant_export"))
    cashier = push_proxy_async(config.get("cashier", "accountant_export"))
    accountant_proxy = AccountantProxy("push",
            config.get("accountant", "accountant_export"),
            config.getint("accountant", "accountant_export_base_port"))
    alerts_proxy = AlertsProxy(config.get("alerts", "export"))
    debug = config.getboolean("accountant", "debug")
    trial_period = config.getboolean("accountant", "trial_period")
    mimetic_share = config.getfloat("accountant", "mimetic_share")

    accountant = Accountant(session, engines, cashier, ledger, webserver, accountant_proxy, alerts_proxy,
                            accountant_number=accountant_number,
                            debug=debug,
                            trial_period=trial_period,
                            mimetic_share=mimetic_share)

    webserver_export = WebserverExport(accountant)
    engine_export = EngineExport(accountant)
    cashier_export = CashierExport(accountant)
    administrator_export = AdministratorExport(accountant)
    accountant_export = AccountantExport(accountant)

    watchdog(config.get("watchdog", "accountant") %
             (config.getint("watchdog", "accountant_base_port") + accountant_number))

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
    pull_share_async(accountant_export,
                       config.get("accountant", "accountant_export") %
                       (config.getint("accountant", "accountant_export_base_port") + accountant_number))

    reactor.callWhenRunning(accountant.repair_user_positions)
    reactor.run()

