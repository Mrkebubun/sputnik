#!/usr/bin/env python
import json
from optparse import OptionParser
import logging
import functools
import bitcoinrpc


from twisted.web.resource import Resource, ErrorPage
from twisted.web.server import Site, NOT_DONE_YET
from twisted.internet import reactor, defer
from twisted.internet.task import LoopingCall

from txbitcoinrpc import BitcoinRpc
from compropago import Compropago
from watchdog import watchdog
from sendmail import Sendmail
import util

import config
from zmq_util import dealer_proxy_sync, router_share_async, pull_share_async, export
import models
import database as db
from sqlalchemy.orm.exc import NoResultFound
from datetime import datetime
import base64
from Crypto.Random.random import getrandbits
from jinja2 import Environment, FileSystemLoader

parser = OptionParser()
parser.add_option("-c", "--config", dest="filename", help="config file", default="../config/sputnik.ini")
(options, args) = parser.parse_args()
if options.filename:
    config.reconfigure(options.filename)

class CashierException(Exception):
    pass

WITHDRAWAL_NOT_FOUND = CashierException(0, "Withdrawal not found")
WITHDRAWAL_COMPLETE = CashierException(1, "Withdrawal already complete")
OUT_OF_ADDRESSES = CashierException(2, "Out of addresses")
NO_AUTOMATIC_WITHDRAWAL = CashierException(3, "No automatic withdrawals for this contract")
INSUFFICIENT_FUNDS = CashierException(4, "Insufficient funds in wallet")
WITHDRAWAL_TOO_LARGE = CashierException(5, "Withdrawal too large portion of on-line wallet")

class Cashier():
    """
    Handles communication between the outside world of deposits and withdrawals and
    the accountant. It does so by offering a public hook for Compropago and a private
    hook to the bitcoin client
    """

    def __init__(self, session, accountant, bitcoinrpc, compropago, cold_wallet_period=None,
                 sendmail=None, template_dir="admin_templates", minimum_confirmations=6):
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
        if cold_wallet_period is not None:
            for ticker in self.bitcoinrpc.keys():
                looping_call = LoopingCall(self.transfer_to_cold_wallet, ticker)
                looping_call.start(cold_wallet_period, now=False)

    def notify_accountant(self, address, total_received):
        """
        Notifies the accountant that the total received in a given address has increased
        and that this should be reflected as a deposit
        :param address: address where the deposit has been made
        :type address: str
        :param total_received: total amount received for this address
        :type total_received: int
        """
        logging.info('notifying the accountant that %s received %d' % (address, total_received))
        # note that this is *only* a notification to the accountant. We know at this point
        # that this address has received *at least* total_received. It will be up to the accountant
        # to update the "accounted_for" column to the total_received value while simultaneously
        # increasing a user's position. We might not have caught *all of the deposited* money
        # but that can happen later and we're guaranteed to never miss a deposit in the long run
        # or to double credit someone incorrectly. Increasing "accounted_for" and increasing
        # the position is an atomic transaction. Cashier is *only telling* the accountant
        # what the state of the bitcoin client is.
        self.accountant.deposit_cash(address, total_received)

    def rescan_address(self, address_str):
        """Check an address to see if deposits have been made against it
        :param address: the address we are checking
        :type address: str
        """
        # TODO: find out why this is unicode
        # probably because of the way txZMQ does things
        address_str = address_str.encode("utf-8")
        logging.info("Scaning address %s for updates." % address_str)
        # TODO: find a better way of doing this
        if address_str.startswith("compropago"):
            payment_id = address_str.split("_", 1)[1]
            def error(failure):
                logging.warn("Could not get bill for id: %s. %s" % (payment_id, str(failure)))

            # Fetch the REAL bill from Compropago.
            d = self.compropago.get_bill(payment_id)
            d.addCallbacks(self.process_compropago_payment, error)

            # You can add an errback for process_compropago_payment here.
            # Alternatively, error handle inside the method itself (recommended)
        else:
            address = self.session.query(models.Addresses).filter_by(address=address_str).one()
            ticker = address.contract.ticker

            if ticker in self.bitcoinrpc:
                denominator = address.contract.denominator
                accounted_for = address.accounted_for
                d = self.bitcoinrpc[ticker].getreceivedbyaddress(address_str, self.minimum_confirmations)

                def notifyAccountant(result):
                    total_received = long(round(result['result'] * denominator))
                    if total_received > accounted_for:
                        self.notify_accountant(address_str, total_received)
                    return True

                def error(failure):
                    logging.error("getreceivedbyaddress failed on %s: %s" % (address_str, failure))
                    raise failure.value

                d.addCallbacks(notifyAccountant, error)

        return d


    def check_for_crypto_deposits(self, ticker='BTC'):
        """
        Checks for crypto deposits in a crypto currency that offers
        a connection compatible with the bitcoind RPC (typically, litecoin, dogecoin...)
        :param currency: the btc-like currency for which to check for deposits
        :type currency: str
        """
        logging.info('checking for deposits')
        # first we get the confirmed deposits
        d = self.bitcoinrpc[ticker].listreceivedbyaddress(self.minimum_confirmations)

        def checkDeposits(result):
            confirmed_deposits = result['result']
            contract = self.session.query(models.Contract).filter_by(ticker=ticker).one()

            # ok, so now for each address get how much was received
            total_received = {row['address']: long(round(row['amount'] * contract.denominator)) for row in confirmed_deposits}
            # but how much have we already accounted for?
            accounted_for = {row['address']: row['accounted_for'] for row in
                             self.session.query(models.Addresses).filter_by(active=True)}

            # so for all the addresses we're dealing with
            for address in set(total_received.keys()).intersection(set(accounted_for.keys())):
                # if we haven't accounted for all the deposits
                if total_received[address] > accounted_for[address]:
                    # tell the accountant
                    self.notify_accountant(address, total_received[address])

        def error(failure):
            logging.error("listreceivedbyaddress failed: %s" % failure)
            raise failure.value

        d.addCallbacks(checkDeposits, error)

    def check_withdrawal(self, withdrawal):
        """
        list withdrawal requests that have been entered and processed them
        either immediately or by pushing them to manual verification
        """
        # if the transaction is innocuous enough
        logging.info("Checking withdrawal: %s" % withdrawal)
        d = self.pass_safety_check(withdrawal)

        def success(ignored):
            d = self.process_withdrawal(withdrawal.id, online=True)
            def onSuccess(result):
                return withdrawal.id

            d.addCallback(onSuccess)
            return d

        def fail(message):
            logging.debug("Safety check failed: %s" % message)
            self.notify_pending_withdrawal(withdrawal)
            return defer.succeed(withdrawal.id)

        d.addCallbacks(success, fail)
        return d


    def pass_safety_check(self, withdrawal_request):
        """
        :param withdrawal_request: a specific request for withdrawal, to be accepted for immediate
                withdrawal or wait until manual validation
        :type withdrawal_request: Withdrawal

        """
        # First check if the withdrawal is for a cryptocurrency
        if withdrawal_request.contract.ticker not in self.bitcoinrpc:
            message = "Withdrawal request for fiat: %s" % withdrawal_request
            logging.error(message)
            return defer.fail(message)

        # 1) do a query for the last 24 hours of the 'orders submitted for cancellation'  keep it under 5bt
        # (what does this mean)
        # 2) make sure we have enough btc on hand - we should have at least 10x the btc onhand than the withdrawal is for
        # 3) make sure the withdrawal is small (< 1 BTC)
        # Not yet implemented
        if withdrawal_request.amount >= 100000000:
            message = "withdrawal too large: %s" % withdrawal_request
            logging.error(message)
            return defer.fail(message)

        d = self.bitcoinrpc[withdrawal_request.contract.ticker].getbalance()

        def gotBalance(result):
            balance = result['result']
            online_cash = long(round(balance * withdrawal_request.contract.denominator))

            if online_cash / 10 <= withdrawal_request.amount:
                logging.error("withdrawal too large portion of online cash balance (%d): %s" % (online_cash,
                                                                                                withdrawal_request))
                raise WITHDRAWAL_TOO_LARGE

            # None of the checks failed, return True
            return defer.succeed(True)

        def error(failure):
            logging.error("unable to get balance from wallet: %s" % failure)
            return defer.fail(failure)

        d.addCallbacks(gotBalance, error)
        return d


    def transfer_to_cold_wallet(self, ticker):
        contract = self.session.query(models.Contract).filter_by(ticker=ticker).one()
        d = self.bitcoinrpc[contract.ticker].getbalance()

        def gotBalance(result):
            balance = result['result']
            online_cash = long(round(balance * contract.denominator))
            logging.debug("Online cash for %s is %d" % (ticker, online_cash))
            # If we exceed the limit by 10%, so we're not always sending small amounts to the cold wallet
            if online_cash > contract.hot_wallet_limit * 1.1:
                amount = online_cash - contract.hot_wallet_limit
                logging.debug("Transferring %d from hot to cold wallet at %s" % (amount, contract.cold_wallet_address))
                d = self.bitcoinrpc[ticker].sendtoaddress(contract.cold_wallet_address,
                                                          float(amount) / contract.denominator)
                def onSendSuccess(result):
                    txid = result['txid']
                    self.accountant.transfer_position(ticker, 'online_cash', 'offline_cash', amount,
                                                              "%s: %s" % (contract.cold_wallet_address, txid))

                def error(failure):
                    logging.error("Unable to send to address: %s" % failure)

                d.addCallbacks(onSendSuccess, error)

        def error(failure):
            logging.error("Unable to get wallet balance: %s" % failure)
            raise failure.value

        d.addCallbacks(gotBalance, error)

    def process_withdrawal(self, withdrawal_id, online=False, cancel=False):
        # Mark a withdrawal as complete, send the money from the BTC wallet if online=True
        # and tell the accountant that the withdrawal has happened
        # If cancel=True, then return the money to the user
        logging.info("Processing withdrawal: %d online=%s cancel=%s" % (withdrawal_id, online, cancel))
        try:
            withdrawal = self.session.query(models.Withdrawal).filter_by(id=withdrawal_id).one()
        except NoResultFound:
            logging.error("No withdrawal found for id %d" % withdrawal_id)
            raise WITHDRAWAL_NOT_FOUND

        logging.debug("Withdrawal found: %s" % withdrawal)
        if not withdrawal.pending:
            raise WITHDRAWAL_COMPLETE

        def finish_withdrawal(to_user, result):
            txid = result['result']
            try:
                self.accountant.transfer_position(withdrawal.contract.ticker, 'pendingwithdrawal', to_user,
                                                  withdrawal.amount, "%s: %s" % (withdrawal.address, txid))
                withdrawal.pending = False
                withdrawal.completed = datetime.utcnow()
                self.session.add(withdrawal)
                self.session.commit()
                return defer.succeed(txid)
            except Exception as e:
                logging.error("Exception when trying to process withdrawal: %s" % e)
                self.session.rollback()
                raise e

        if cancel:
            return finish_withdrawal(withdrawal.username, {'result': 'cancel'})
        else:
            if online:
                if withdrawal.contract.ticker in self.bitcoinrpc:
                    withdrawal_amount = float(withdrawal.amount) / withdrawal.contract.denominator
                    d = self.bitcoinrpc[withdrawal.contract.ticker].getbalance()
                    def gotBalance(result):
                        balance = result['result']
                        if balance >= withdrawal_amount:
                            d = self.bitcoinrpc[withdrawal.contract.ticker].sendtoaddress(withdrawal.address,
                                                                                          withdrawal_amount)
                            def error(failure):
                                logging.error("Unable to send to address: %s" % failure)
                                raise failure.value

                            d.addCallbacks(functools.partial(finish_withdrawal, "onlinecash"), error)
                            return d
                        else:
                            raise INSUFFICIENT_FUNDS

                    def error(failure):
                        logging.error("Unable to get wallet balance: %s" % failure)
                        raise failure.value

                    d.addCallbacks(gotBalance, error)
                    return d

                else:
                    raise NO_AUTOMATIC_WITHDRAWAL
            else:
                return finish_withdrawal('offlinecash', {'result': 'offline'})


    def request_withdrawal(self, username, ticker, address, amount):
        try:
            user = self.session.query(models.User).filter_by(username=username).one()
            contract = self.session.query(models.Contract).filter_by(ticker=ticker).one()
            withdrawal = models.Withdrawal(user, contract, address, amount)
            self.session.add(withdrawal)
            self.session.commit()

            # Check to see if we can process this automatically. If we can, then process it
            d = self.check_withdrawal(withdrawal)
            return d
        except Exception as e:
            logging.error("Exception when creating withdrawal ticket: %s" % e)
            self.session.rollback()
            raise e

    def process_compropago_payment(self, payment_info):
        """
        received payment information from a compropago payment and processes it
        :param payment_info: object representing a payment
        :type payment_info: dict
        """
        address = 'compropago_%s' % payment_info['id']
        # Convert pesos to pesocents
        # TODO: Actually get the denominator from the DB
        cents = float(payment_info['amount'])*100
        if cents != int(cents):
            logging.error("payment from compropago doesn't seem to be an integer number of cents: %f" % cents)
            raise "error couldn't process compropago payment, amount not a number of cents"

        amount = self.compropago.amount_after_fees(cents)
        return self.process_withdrawal(address, amount)

    def notify_pending_withdrawal(self, withdrawal):
        """
        email notification of withdrawal pending to the user.
        """

        # Now email the token
        t = self.jinja_env.get_template('pending_withdrawal.email')
        content = t.render(withdrawal=withdrawal).encode('utf-8')

        # Now email the token
        logging.debug("Sending mail: %s" % content)
        s = self.sendmail.send_mail(content, to_address='<%s> %s' % (withdrawal.user.email,
                                                                     withdrawal.user.nickname),
                          subject='Your withdrawal request is pending')


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
            logging.error("Unable to disable old addresses for: %s/%s: %s" % (username, ticker, e))
            self.session.rollback()
            raise e

        if address is None:
            contract = self.session.query(models.Contract).filter_by(ticker=ticker).one()
            user = self.session.query(models.User).filter_by(username=username).one()

            if ticker in self.bitcoinrpc:
                # If we have a bitcoinrpc for this ticker, generate one that way
                d = self.bitcoinrpc[ticker].getnewaddress()
            else:
                # Otherwise it is just a random string
                address = base64.b64encode(("%016X" % getrandbits(64)).decode("hex"))
                d = defer.succeed({'result': address})

            def error(failure):
                logging.error("Unable to getnewaddress: %s" % failure)
                raise failure.value

            def gotAddress(result):
                try:
                    address_str = result['result']
                    logging.debug("Got new address: %s" % address_str)
                    address = models.Addresses(user, contract, address_str)
                    address.username = username
                    address.active = True
                    self.session.add(address)
                    self.session.commit()
                    return address_str
                except Exception as e:
                    logging.error("Unable to get address for: %s/%s: %s" % (username, ticker, e))
                    self.session.rollback()
                    raise e

            d.addCallbacks(gotAddress, error)
            return d
        else:
            try:
                address.username = username
                address.active = True
                self.session.add(address)
                self.session.commit()
                return defer.succeed(address.address)
            except Exception as e:
                logging.error("Unable to get address for: %s/%s: %s" % (username, ticker, e))
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
        return contract.deposit_instructions

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
            logging.warn("Received undecodable object from Compropago: %s" % json_string)
            return "OK"
        except:
            logging.warn("Received unexpected object from Compropago: %s" % json_string)
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
        logging.info("Got a notification from bitcoind: %s" % request)
        self.cashier.check_for_crypto_deposits('BTC')
        return "OK"

class WebserverExport:
    def __init__(self, cashier):
        self.cashier = cashier

    @export
    def get_new_address(self, username, ticker):
        return self.cashier.get_new_address(username, ticker)

    @export
    def get_current_address(self, username, ticker):
        return self.cashier.get_current_address(username, ticker)

    @export
    def get_deposit_instructions(self, ticker):
        return self.cashier.get_deposit_instructions(ticker)

class AdministratorExport:
    def __init__(self, cashier):
        """

        :param cashier: the cashier we can talk to
        :type cashier: Cashier
        """
        self.cashier = cashier

    @export
    def rescan_address(self, address):
        return self.cashier.rescan_address(address)

    @export
    def process_withdrawal(self, address, online=False, cancel=False):
        return self.cashier.process_withdrawal(address, online=online, cancel=cancel)

class AccountantExport:
    def __init__(self, cashier):
        self.cashier = cashier

    @export
    def request_withdrawal(self, username, ticker, address, amount):
        return self.cashier.request_withdrawal(username, ticker, address, amount)

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s', level=logging.DEBUG)

    accountant = dealer_proxy_sync(config.get("accountant", "cashier_export"))

    session = db.make_session()
    bitcoin_conf = config.get("cashier", "bitcoin_conf")

    logging.info('connecting to bitcoin client')

    bitcoinrpc = {'BTC': BitcoinRpc(bitcoin_conf)}
    compropago = Compropago(config.get("cashier", "compropago_key"))
    cold_wallet_period = config.getint("cashier", "cold_wallet_period")
    sendmail=Sendmail(config.get("administrator", "email"))
    minimum_confirmations = config.getint("cashier", "minimum_confirmations")

    cashier = Cashier(session, accountant, bitcoinrpc, compropago,
                      cold_wallet_period=cold_wallet_period,
                      sendmail=sendmail,
                      minimum_confirmations=minimum_confirmations)

    administrator_export = AdministratorExport(cashier)
    accountant_export = AccountantExport(cashier)
    webserver_export = WebserverExport(cashier)

    watchdog(config.get("watchdog", "cashier"))
    pull_share_async(administrator_export,
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
