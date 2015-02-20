#!/usr/bin/env python

import json
import sys, os
from optparse import OptionParser

from twisted.web.resource import Resource, ErrorPage
from twisted.web.server import Site, NOT_DONE_YET
from twisted.internet import reactor, defer
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.task import LoopingCall
from twisted.python import log

import config
from txbitcoinrpc import BitcoinRpc
from compropago import Compropago
from watchdog import watchdog
from sendmail import Sendmail
from accountant import AccountantProxy
from alerts import AlertsProxy
import util

from zmq_util import router_share_async, pull_share_async, export, ComponentExport
import models
import database as db
from sqlalchemy.orm.exc import NoResultFound
from datetime import datetime
import base64
from Crypto.Random.random import getrandbits
from jinja2 import Environment, FileSystemLoader
from rpc_schema import schema
import markdown
from util import session_aware
from exception import *
from bitgo import BitGo
from pycoin.key.validate import is_address_valid


parser = OptionParser()
parser.add_option("-c", "--config", dest="filename", help="config file")
(options, args) = parser.parse_args()
if options.filename:
    config.reconfigure(options.filename)

WITHDRAWAL_NOT_FOUND = CashierException("exceptions/cashier/withdrawal_not_found")
WITHDRAWAL_COMPLETE = CashierException("exceptions/cashier/withdrawal_complete")
OUT_OF_ADDRESSES = CashierException("exceptions/cashier/out_of_addresses")
NO_AUTOMATIC_WITHDRAWAL = CashierException("exceptions/cashier/no_automatic_withdrawal")
INSUFFICIENT_FUNDS = CashierException("exceptions/cashier/insufficient_funds")
WITHDRAWAL_TOO_LARGE = CashierException("exceptions/cashier/withdrawal_too_large")
NO_SPUTNIK_WALLET = CashierException("exceptions/cashier/no_sputnik_wallet")
NO_KEY_FILE = CashierException("exceptions/bitgo/no_key_file")
INVALID_ADDRESS = CashierException("exceptions/cashier/invalid_address")
OTP_INVALID = CashierException("exceptions/cashier/otp_invalid")

class Cashier():
    """
    Handles communication between the outside world of deposits and withdrawals and
    the accountant. It does so by offering a public hook for Compropago and a private
    hook to the bitcoin client
    """

    def __init__(self, session, accountant, bitcoinrpc, compropago, cold_wallet_period=None,
                 sendmail=None, template_dir="admin_templates", minimum_confirmations=6, alerts=None,
                 bitgo=None, bitgo_private_key_file=None, testnet=True):
        """
        Initializes the cashier class by connecting to bitcoind and to the accountant
        also sets up the db session and some configuration variables
        """

        self.session = session
        self.accountant = accountant
        self.bitcoinrpc = bitcoinrpc
        self.compropago = compropago
        self.sendmail = sendmail
        self.minimum_confirmations = minimum_confirmations
        self.jinja_env = Environment(loader=FileSystemLoader(template_dir))
        self.alerts = alerts
        self.bitgo = bitgo
        self.bitgo_private_key_file = bitgo_private_key_file
        self.testnet = testnet
        if cold_wallet_period is not None:
            for ticker in self.bitcoinrpc.keys():
                looping_call = LoopingCall(self.transfer_from_hot_wallet, ticker)
                looping_call.start(cold_wallet_period, now=False)

    @inlineCallbacks
    def notify_accountant(self, address, total_received):
        """
        Notifies the accountant that the total received in a given address has increased
        and that this should be reflected as a deposit
        :param address: address where the deposit has been made
        :type address: str
        :param total_received: total amount received for this address
        :type total_received: int
        """
        log.msg('notifying the accountant that %s received %d' % (address, total_received))
        # note that this is *only* a notification to the accountant. We know at this point
        # that this address has received *at least* total_received. It will be up to the accountant
        # to update the "accounted_for" column to the total_received value while simultaneously
        # increasing a user's position. We might not have caught *all of the deposited* money
        # but that can happen later and we're guaranteed to never miss a deposit in the long run
        # or to double credit someone incorrectly. Increasing "accounted_for" and increasing
        # the position is an atomic transaction. Cashier is *only telling* the accountant
        # what the state of the bitcoin client is.

        try:
            result = yield self.accountant.deposit_cash(address.username, address.address, total_received)
            returnValue(result)
        except Exception as e:
            # If this didn't work, we need to do a send_alert
            log.err(e)
            self.alerts.send_alert(str(e), "Deposit cash failed!")
            # We don't need to continue to propagate this error, so don't return failure

    @inlineCallbacks
    def rescan_address(self, address_str):
        """Check an address to see if deposits have been made against it
        :param address: the address we are checking
        :type address: str
        """
        # TODO: find out why this is unicode
        # probably because of the way txZMQ does things
        address_str = address_str.encode("utf-8")
        log.msg("Scanning address %s for updates." % address_str)
        # TODO: find a better way of doing this
        # if address_str.startswith("compropago"):
        #     payment_id = address_str.split("_", 1)[1]
        #     def error(failure):
        #         log.msg("Could not get bill for id: %s. %s" % (payment_id, str(failure)))
        #
        #     try:
        #         # Fetch the REAL bill from Compropago.
        #         payment_info = yield self.compropago.get_bill(payment_id)
        #     except Exception as e:
        #         log.msg("Could not get bill for id: %s: %s" % (payment_id, str(e)))
        #         raise e
        #         result = yield self.process_compropago_payment(payment_info)
        #         returnValue(result)
        #
        # else:
        address = self.session.query(models.Addresses).filter_by(address=address_str).one()
        ticker = address.contract.ticker

        if ticker in self.bitcoinrpc:
            denominator = address.contract.denominator
            accounted_for = address.accounted_for

            try:
                result = yield self.bitcoinrpc[ticker].getreceivedbyaddress(address_str, self.minimum_confirmations)
            except Exception as e:
                log.err("getreceivedbyaddress failed on %s: %s" % (address_str, str(e)))
                raise e

            total_received = long(round(result['result'] * denominator))
            if total_received > accounted_for:
                yield self.notify_accountant(address, total_received)

            returnValue(True)

    @inlineCallbacks
    def check_for_crypto_deposits(self, ticker='BTC'):
        """
        Checks for crypto deposits in a crypto currency that offers
        a connection compatible with the bitcoind RPC (typically, litecoin, dogecoin...)
        :param currency: the btc-like currency for which to check for deposits
        :type currency: str
        """
        log.msg('checking for deposits')
        # first we get the confirmed deposits
        try:
            result = yield self.bitcoinrpc[ticker].listreceivedbyaddress(self.minimum_confirmations)
        except Exception as e:
            log.err("listreceivedbyaddress failed: %s" % e)
            raise e

        confirmed_deposits = result['result']
        contract = self.session.query(models.Contract).filter_by(ticker=ticker).one()

        # ok, so now for each address get how much was received
        total_received = {row['address']: long(round(row['amount'] * contract.denominator)) for row in confirmed_deposits}
        # but how much have we already accounted for?
        accounted_for = {row.address: [row.accounted_for,row] for row in
                         self.session.query(models.Addresses).filter_by(active=True)}

        # so for all the addresses we're dealing with
        for address in set(total_received.keys()).intersection(set(accounted_for.keys())):
            # if we haven't accounted for all the deposits
            if total_received[address] > accounted_for[address][0]:
                # tell the accountant
                yield self.notify_accountant(accounted_for[address][1], total_received[address])

    @inlineCallbacks
    def check_withdrawal(self, withdrawal):
        """
        list withdrawal requests that have been entered and processed them
        either immediately or by pushing them to manual verification
        """
        # if the transaction is innocuous enough
        log.msg("Checking withdrawal: %s" % withdrawal)
        try:
            result = yield self.pass_safety_check(withdrawal)
        except Exception as e:
            log.msg("Safety check failed: %s" % str(e))
            self.notify_pending_withdrawal(withdrawal)
            returnValue(withdrawal.id)

        if not result:
            log.msg("Safety check failed")
            self.notify_pending_withdrawal(withdrawal)
            returnValue(withdrawal.id)

        # If the safety check passed, actually do the withdrawal
        yield self.process_withdrawal(withdrawal.id, online=True)
        returnValue(withdrawal.id)

    @inlineCallbacks
    def pass_safety_check(self, withdrawal_request):
        """
        :param withdrawal_request: a specific request for withdrawal, to be accepted for immediate
                withdrawal or wait until manual validation
        :type withdrawal_request: Withdrawal

        """
        # First check if the withdrawal is for a cryptocurrency
        if withdrawal_request.contract.ticker not in self.bitcoinrpc:
            log.err("Withdrawal request for fiat: %s" % withdrawal_request)
            raise NO_AUTOMATIC_WITHDRAWAL

        # 1) do a query for the last 24 hours of the 'orders submitted for cancellation'  keep it under 5bt
        # (what does this mean)
        # 2) make sure we have enough btc on hand - we should have at least 10x the btc onhand than the withdrawal is for
        # 3) make sure the withdrawal is small (< 1 BTC)
        # Not yet implemented
        if withdrawal_request.amount >= 100000000:
            log.err("withdrawal too large: %s" % withdrawal_request)
            raise WITHDRAWAL_TOO_LARGE

        try:
            result = yield self.bitcoinrpc[withdrawal_request.contract.ticker].getbalance()
        except Exception as e:
            log.err("unable to get balance from wallet: %s" % str(e))
            raise e

        balance = result['result']
        online_cash = long(round(balance * withdrawal_request.contract.denominator))

        if online_cash / 10 <= withdrawal_request.amount:
            log.err("withdrawal too large portion of online cash balance (%d): %s" % (online_cash,
                                                                                            withdrawal_request))
            raise WITHDRAWAL_TOO_LARGE

        # None of the checks failed, return True
        returnValue(True)

    @inlineCallbacks
    def transfer_from_hot_wallet(self, ticker, quantity=None, destination="multisigcash"):
        contract = self.session.query(models.Contract).filter_by(ticker=ticker).one()

        if destination == "offlinecash" or not contract.multisig_wallet_address:
            address = contract.cold_wallet_address
            to_account = "offlinecash"
        else:
            address = contract.multisig_wallet_address
            to_account = "multisigcash"

        if quantity is None:
            try:
                online_cash = self.session.query(models.Positions).filter_by(username="onlinecash").filter_by(contract=contract).one()
            except NoResultFound:
                log.msg("No position in %s for onlinecash" % ticker)
                returnValue(None)
            else:
                # If we exceed the limit by 10%, so we're not always sending small amounts to the cold wallet
                if online_cash.position > contract.hot_wallet_limit * 1.1:
                    quantity = online_cash.position - contract.hot_wallet_limit
                else:
                    returnValue(None)

        log.msg("Transferring %d from hot to %s wallet at %s" % (quantity, destination, address))
        result = yield self.send_to_address(ticker, address, quantity)
        txid = result['txid']

        # Charge the fee to 'customer'
        fee = result['fee']
        fee_uid = util.get_uid()
        note = "%s: %s" % (address, txid)

        # CREDIT online cash (decrease)
        fee_d1 = self.accountant.transfer_position('onlinecash', ticker, "credit", fee,
                                               note, fee_uid)

        # DEBIT the customer (decrease)
        fee_d2 = self.accountant.transfer_position('customer', ticker, "debit", fee,
                                                   note, fee_uid)

        uid = util.get_uid()

        # CREDIT THE FROM ACCOUNT (decrease)
        d1=self.accountant.transfer_position('onlinecash', ticker, 'credit', quantity,
                                          note, uid)
        # DEBIT THE TO ACCOUNT (increase)
        d2=self.accountant.transfer_position(to_account, ticker, 'debit', quantity, note, uid)
        yield defer.gatherResults([d1, d2, fee_d1, fee_d2], consumeErrors=True)
        returnValue(txid)

    @inlineCallbacks
    def transfer_from_multisig_wallet(self, ticker, quantity, destination, multisig):
        contract = util.get_contract(self.session, ticker)
        if destination == "onlinecash":
            address = yield self.get_current_address("multisigcash", ticker)
        elif destination == "offlinecash":
            address = contract.cold_wallet_address
        else:
            raise NotImplementedError

        result = yield self.send_to_address(ticker, address, quantity, multisig=multisig)
        txid = result['txid']
        fee = result['fee']

        # Record fees
        fee_uid = util.get_uid()
        note = "%s: %s" % (address, txid)

        # CREDIT the from account
        fee_d1 = self.accountant.transfer_position('multisigcash', ticker, 'credit', fee, note, fee_uid)

        # DEBIT the customer account
        fee_d2 = self.accountant.transfer_position('customer', ticker, 'debit', fee, note, fee_uid)
        yield defer.gatherResults([fee_d1, fee_d2], consumeErrors=True)

        if destination == "offlinecash":
            # Record the transfer
            uid = util.get_uid()
            # CREDIT the from account
            d1=self.accountant.transfer_position('multisigcash', ticker, 'credit', quantity,
                                              note, uid)
            # DEBIT the to account
            d2=self.accountant.transfer_position('offlinecash', ticker, 'debit', quantity, note, uid)
            yield defer.gatherResults([d1, d2])
        else:
            # If going to online cash the transfer will get recorded when the btc arrives
            pass

        returnValue(txid)

    @inlineCallbacks
    def send_to_address(self, ticker, address, amount, multisig={}):
        if self.testnet:
            network = "XTN"
        else:
            network = "BTC"

        if is_address_valid(address) != network:
            raise INVALID_ADDRESS

        contract = util.get_contract(self.session, ticker)
        if not multisig:
            withdrawal_amount = util.quantity_from_wire(contract, amount)
            try:
                result = yield self.bitcoinrpc[ticker].getbalance()
            except Exception as e:
                log.err("Unable to get wallet balance: %s" % str(e))
                raise e

            balance = result['result']
            if balance >= withdrawal_amount:
                try:
                    result = yield self.bitcoinrpc[ticker].sendtoaddress(address, withdrawal_amount)
                    txid = result['result']
                    tx = yield self.bitcoinrpc[ticker].gettransaction(txid)
                    # The fee shows up from gettransaction as a negative number,
                    # but we want a positive number
                    fee = abs(long(round(tx['result']['fee'] * contract.denominator)))

                except Exception as e:
                    log.err("Unable to send to address: %s" % str(e))
                    raise e
            else:
                raise INSUFFICIENT_FUNDS
        else:
            self.bitgo.token = multisig['token'].encode('utf-8')
            try:
                yield self.bitgo.unlock(multisig['otp'])
            except Exception as e:
                log.err("Unable to unlock multisig")
                raise OTP_INVALID

            wallet_id = contract.multisig_wallet_address
            try:
                wallet = yield self.bitgo.wallets.get(wallet_id)
            except Exception as e:
                log.err("Unable to get wallet details")
                log.err(e)
                raise e

            balance = wallet.balance
            if balance < amount:
                raise INSUFFICIENT_FUNDS

            if not os.path.exists(self.bitgo_private_key_file):
                raise NO_KEY_FILE
            else:
                with open(self.bitgo_private_key_file, "rb") as f:
                    key_data = json.load(f)
                    passphrase = key_data['passphrase']

            try:
                result = yield wallet.sendCoins(address=address, amount=amount,
                        passphrase=passphrase)
                txid = result['tx']
                fee = result['fee']
            except Exception as e:
                log.err("Unable to sendCoins")
                log.err(e)
                raise e

        returnValue({'txid': txid,
                     'fee': fee})

    @inlineCallbacks
    def process_withdrawal(self, withdrawal_id, online=False, cancel=False, admin_username=None, multisig={}):
        # Mark a withdrawal as complete, send the money from the BTC wallet if online=True
        # and tell the accountant that the withdrawal has happened
        # If cancel=True, then return the money to the user
        log.msg("Processing withdrawal: %d online=%s cancel=%s" % (withdrawal_id, online, cancel))
        try:
            withdrawal = self.session.query(models.Withdrawal).filter_by(id=withdrawal_id).one()
        except NoResultFound:
            log.err("No withdrawal found for id %d" % withdrawal_id)
            raise WITHDRAWAL_NOT_FOUND

        log.msg("Withdrawal found: %s" % withdrawal)
        if not withdrawal.pending:
            raise WITHDRAWAL_COMPLETE

        # Figure out what to do with this withdrawal, and send to address if an online withdrawal
        if cancel:
            txid = "cancel"
            to_user = withdrawal.username
            fee = None
        else:
            if online:
                # Actually process via the hot or warm wallet
                if withdrawal.contract.ticker in self.bitcoinrpc:
                    if not multisig:
                        to_user = "onlinecash"
                    else:
                        to_user = "multisig"

                    result = yield self.send_to_address(withdrawal.contract.ticker, withdrawal.address, withdrawal.amount,
                                                      multisig=multisig)
                    txid = result['txid']
                    fee = result['fee']
                else:
                    raise NO_AUTOMATIC_WITHDRAWAL
            else:
                fee = None
                txid = "offline"
                to_user = "offlinecash"

        # Notify the accountant
        try:
            if admin_username is not None:
                note = "%s: %s (%s)" % (withdrawal.address, txid, admin_username)
            else:
                note = "%s: %s" % (withdrawal.address, txid)

            # If there was a fee
            if fee is not None:
                fee_uid = util.get_uid()
                fee_d1 = self.accountant.transfer_position(to_user, withdrawal.contract.ticker, 'credit', fee,
                                                           note, fee_uid)
                fee_d2 = self.accountant.transfer_position('customer', withdrawal.contract.ticker, 'debit', fee,
                                                           note, fee_uid)
                yield defer.gatherResults([fee_d1, fee_d2], consumeErrors=True)

            uid = util.get_uid()


            d1 = self.accountant.transfer_position('pendingwithdrawal', withdrawal.contract.ticker, 'debit',
                                              withdrawal.amount,
                                              note, uid)
            d2 = self.accountant.transfer_position(to_user, withdrawal.contract.ticker, 'credit', withdrawal.amount,
                                              note, uid)
            yield defer.gatherResults([d1, d2], consumeErrors=True)
        except Exception as e:
            log.err(e)
            self.alerts.send_alert(str(e), "Transfer position failed in process_withdrawal")
            raise e

        # Update the DB
        try:
            withdrawal.pending = False
            withdrawal.completed = datetime.utcnow()
            self.session.add(withdrawal)
            self.session.commit()
        except Exception as e:
            log.err("Exception when trying to mark withdrawal complete: %s" % e)
            self.session.rollback()
            raise e

        returnValue(txid)

    def request_withdrawal(self, username, ticker, address, amount):
        try:
            user = self.session.query(models.User).filter_by(username=username).one()
            contract = self.session.query(models.Contract).filter_by(ticker=ticker).one()
            withdrawal = models.Withdrawal(user, contract, address, amount)
            self.session.add(withdrawal)
            self.session.commit()
        except Exception as e:
            log.err("Exception when creating withdrawal ticket: %s" % e)
            self.session.rollback()
            raise e

        # Check to see if we can process this automatically. If we can, then process it
        return self.check_withdrawal(withdrawal)

    # def process_compropago_payment(self, payment_info):
    #     """
    #     received payment information from a compropago payment and processes it
    #     :param payment_info: object representing a payment
    #     :type payment_info: dict
    #     """
    #     address = 'compropago_%s' % payment_info['id']
    #     # Convert pesos to pesocents
    #     # TODO: Actually get the denominator from the DB
    #     cents = float(payment_info['amount'])*100
    #     if cents != int(cents):
    #         log.err("payment from compropago doesn't seem to be an integer number of cents: %f" % cents)
    #         raise "error couldn't process compropago payment, amount not a number of cents"
    #
    #     amount = self.compropago.amount_after_fees(cents)
    #     # TODO: This needs to change to id, not address
    #     return self.process_withdrawal(address, amount)

    def notify_pending_withdrawal(self, withdrawal):
        """
        email notification of withdrawal pending to the user.
        """

        # Now email the notification
        t = util.get_locale_template(withdrawal.user.locale, self.jinja_env, 'pending_withdrawal.{locale}.email')
        content = t.render(withdrawal=withdrawal).encode('utf-8')

        # Now email the token
        log.msg("Sending mail: %s" % content)
        s = self.sendmail.send_mail(content, to_address='<%s> %s' % (withdrawal.user.email,
                                                                     withdrawal.user.nickname),
                          subject='Your withdrawal request is pending')

    @inlineCallbacks
    def get_new_address(self, username, ticker):
        try:
            address = self.session.query(models.Addresses).join(models.Contract).filter(
                                                        models.Addresses.active == False,
                                                        models.Addresses.username == None,
                                                        models.Contract.ticker == ticker).order_by(models.Addresses.id).first()

            old_addresses = self.session.query(models.Addresses).join(models.Contract).filter(
                                                                    models.Addresses.username == username,
                                                                    models.Addresses.active == True,
                                                                    models.Contract.ticker == ticker).all()
            for old in old_addresses:
                old.active = False
                self.session.add(old)

            self.session.commit()
        except Exception as e:
            log.err("Unable to disable old addresses for: %s/%s: %s" % (username, ticker, e))
            self.session.rollback()
            raise e

        if address is None:
            contract = self.session.query(models.Contract).filter_by(ticker=ticker).one()
            user = self.session.query(models.User).filter_by(username=username).one()

            if ticker in self.bitcoinrpc:
                # If we have a bitcoinrpc for this ticker, generate one that way
                try:
                    result = yield self.bitcoinrpc[ticker].getnewaddress()
                    address_str = result['result']
                except Exception as e:
                    log.err("Unable to getnewaddress: %s" % str(e))
                    raise e
            else:
                # Otherwise it is just a random string
                address_str = base64.b64encode(("%016X" % getrandbits(64)).decode("hex"))

            log.msg("Got new address: %s" % address_str)

            try:
                address = models.Addresses(user, contract, address_str)
                address.username = username
                address.active = True
                self.session.add(address)
                self.session.commit()
            except Exception as e:
                log.err("Unable to save new address to DB")
                log.err(e)
                raise e

            returnValue(address_str)
        else:
            try:
                address.username = username
                address.active = True
                self.session.add(address)
                self.session.commit()
                returnValue(address.address)
            except Exception as e:
                log.err("Unable to assign address: %s/%s: %s" % (username, ticker, e))
                log.err(e)
                self.session.rollback()
                raise e


    def get_current_address(self, username, ticker):
        address = self.session.query(models.Addresses).join(models.Contract).filter(models.Addresses.username==username,
                                                    models.Addresses.active==True,
                                                    models.Contract.ticker==ticker).first()
        if address is None:
            return self.get_new_address(username, ticker)
        else:
            return defer.succeed(address.address)

    def get_deposit_instructions(self, ticker):
        contract = self.session.query(models.Contract).filter_by(ticker=ticker).one()
        return markdown.markdown(contract.deposit_instructions,
                extensions=["extra", "sane_lists", "nl2br"])

class CompropagoHook(Resource):
    """
    Resource URL for compropago to give us callbacks
    """
    isLeaf = True

    def __init__(self, cashier):
        """
        :param cashier: The cashier we talk to
        """
        Resource.__init__(self)
        self.cashier = cashier
        self.compropago = cashier.compropago

    def render(self, request):
        """
        Compropago will post transaction details to us
        :param request: a json object representing the transaction details
        :type request: twisted.web.http.Request
        :returns: str - anything as long as it's code 200
        """
        json_string = request.content.getvalue()
        try:
            cgo_notification = json.loads(json_string)
            bill = self.compropago.parse_existing_bill(cgo_notification)
        except ValueError:
            log.msg("Received undecodable object from Compropago: %s" % json_string)
            return "OK"
        except:
            log.msg("Received unexpected object from Compropago: %s" % json_string)
            return "OK"

        payment_id = bill["id"]
        d = self.cashier.rescan_address("compropago_" + payment_id)
        def onSuccess(result):
            request.write("OK")
            request.finish()

        def onFail(failure):
            request.write(failure.value.args)
            request.finish()

        d.addCallbacks(onSuccess, onFail)
        return NOT_DONE_YET


class BitcoinNotify(Resource):
    """
    A hook for the bitcoind client to notify us via curl or wget

    """
    isLeaf = True

    def __init__(self, cashier_):
        """
        :param cashier_: the cashier we can talk to
        :type cashier_: Cashier
        :return:
        """
        Resource.__init__(self)
        self.cashier = cashier_

    def render_GET(self, request):
        """
        receives a notice from bitcoind containing a transaction hash
        :param request: the http request, typically containing the transaction hash
        :type request: twisted.web.http.Request
        :returns: str - the string "OK", which isn't relevant
        """
        log.msg("Got a notification from bitcoind: %s" % request)
        d = self.cashier.check_for_crypto_deposits('BTC')

        def _err(failure):
            # TODO: let someone know the bitcoind call timed out
            log.err("Check for crypto deposits timed out.")
            pass

        d.addErrback(_err)
        return "OK"

class WebserverExport(ComponentExport):
    def __init__(self, cashier):
        self.cashier = cashier
        ComponentExport.__init__(self, cashier)

    @export
    @session_aware
    @schema("rpc/cashier.json#get_new_address")
    def get_new_address(self, username, ticker):
        return self.cashier.get_new_address(username, ticker)

    @export
    @session_aware
    @schema("rpc/cashier.json#get_current_address")
    def get_current_address(self, username, ticker):
        return self.cashier.get_current_address(username, ticker)

    @export
    @session_aware
    @schema("rpc/cashier.json#get_deposit_instructions")
    def get_deposit_instructions(self, ticker):
        return self.cashier.get_deposit_instructions(ticker)

class AdministratorExport(ComponentExport):
    def __init__(self, cashier):
        """

        :param cashier: the cashier we can talk to
        :type cashier: Cashier
        """
        self.cashier = cashier
        ComponentExport.__init__(self, cashier)

    @export
    @session_aware
    @schema("rpc/cashier.json#rescan_address")
    def rescan_address(self, address):
        return self.cashier.rescan_address(address)

    @export
    @session_aware
    @schema("rpc/cashier.json#process_withdrawal")
    def process_withdrawal(self, id, online=False, cancel=False, admin_username=None, multisig=None):
        return self.cashier.process_withdrawal(id, online=online, cancel=cancel, admin_username=admin_username, multisig=multisig)

    @export
    @session_aware
    @schema("rpc/cashier.json#get_current_address")
    def get_current_address(self, username, ticker):
        return self.cashier.get_current_address(username, ticker)

    @export
    @session_aware
    @schema("rpc/cashier.json#transfer_from_multisig_wallet")
    def transfer_from_multisig_wallet(self, ticker, quantity, destination, multisig):
        return self.cashier.transfer_from_multisig_wallet(ticker, quantity, destination, multisig)

    @export
    @session_aware
    @schema("rpc/cashier.json#transfer_from_hot_wallet")
    def transfer_from_hot_wallet(self, ticker, quantity, destination):
        return self.cashier.transfer_from_hot_wallet(ticker, quantity, destination)

class AccountantExport(ComponentExport):
    def __init__(self, cashier):
        self.cashier = cashier
        ComponentExport.__init__(self, cashier)

    @export
    @session_aware
    @schema("rpc/cashier.json#request_withdrawal")
    def request_withdrawal(self, username, ticker, address, amount):
        return self.cashier.request_withdrawal(username, ticker, address, amount)

if __name__ == '__main__':
    log.startLogging(sys.stdout)

    accountant = AccountantProxy("dealer",
            config.get("accountant", "cashier_export"),
            config.getint("accountant", "cashier_export_base_port"))

    session = db.make_session()
    bitcoin_conf = config.get("cashier", "bitcoin_conf")

    log.msg('connecting to bitcoin client')

    bitcoinrpc = {'BTC': BitcoinRpc(bitcoin_conf, 1)}
    compropago = Compropago(config.get("cashier", "compropago_key"))
    cold_wallet_period = config.getint("cashier", "cold_wallet_period")
    sendmail=Sendmail(config.get("administrator", "email"))
    minimum_confirmations = config.getint("cashier", "minimum_confirmations")
    alerts_proxy = AlertsProxy(config.get("alerts", "export"))
    bitgo_config = {'use_production': not config.getboolean("cashier", "testnet"),
                    'client_id': config.get("bitgo", "client_id"),
                    'client_secret': config.get("bitgo", "client_secret")}
    bitgo = BitGo(**bitgo_config)
    bitgo_private_key_file = config.get("cashier", "bitgo_private_key_file")

    cashier = Cashier(session, accountant, bitcoinrpc, compropago,
                      cold_wallet_period=cold_wallet_period,
                      sendmail=sendmail,
                      minimum_confirmations=minimum_confirmations,
                      alerts=alerts_proxy,
                      bitgo=bitgo,
                      bitgo_private_key_file=bitgo_private_key_file,
                      testnet=config.getboolean("cashier", "testnet"),
    )

    administrator_export = AdministratorExport(cashier)
    accountant_export = AccountantExport(cashier)
    webserver_export = WebserverExport(cashier)

    watchdog(config.get("watchdog", "cashier"))
    router_share_async(administrator_export,
                     config.get("cashier", "administrator_export"))
    pull_share_async(accountant_export,
                    config.get("cashier", "accountant_export"))
    router_share_async(webserver_export,
                       config.get("cashier", "webserver_export"))

    public_server = Resource()
    public_server.putChild('compropago', CompropagoHook(cashier))
    private_server = Resource()
    private_server.putChild('bitcoin', BitcoinNotify(cashier))


    if config.getboolean("webserver", "ssl"):
        key = config.get("webserver", "ssl_key")
        cert = config.get("webserver", "ssl_cert")
        cert_chain = config.get("webserver", "ssl_cert_chain")
        contextFactory = util.ChainedOpenSSLContextFactory(key, cert_chain)

        reactor.listenSSL(config.getint("cashier", "public_port"),
                      Site(public_server), contextFactory,
                      interface=config.get("cashier", "public_interface"))
    else:
        reactor.listenTCP(config.getint("cashier", "public_port"),
                      Site(public_server),
                      interface=config.get("cashier", "public_interface"))

    reactor.listenTCP(config.getint("cashier", "private_port"), Site(private_server),
                      interface=config.get("cashier", "private_interface"))

    reactor.run()
