#!/usr/bin/env python
import json
from optparse import OptionParser
import logging



from twisted.web.resource import Resource, ErrorPage
from twisted.web.server import Site
from twisted.internet import reactor, defer

import bitcoinrpc
from compropago import Compropago
import util

import config
from zmq_util import dealer_proxy_sync, router_share_async, pull_share_async, export
import models
import database as db
from sqlalchemy.orm.exc import NoResultFound
from datetime import datetime
import base64
from Crypto.Random.random import getrandbits

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

class Cashier():
    """
    Handles communication between the outside world of deposits and withdrawals and
    the accountant. It does so by offering a public hook for Compropago and a private
    hook to the bitcoin client
    """
    minimum_confirmations = 6

    def __init__(self, session, accountant, bitcoinrpc, compropago):
        """
        Initializes the cashier class by connecting to bitcoind and to the accountant
        also sets up the db session and some configuration variables
        """
        self.cold_wallet_address = 'xxxx'

        self.session = session
        self.accountant = accountant
        self.bitcoinrpc = bitcoinrpc
        self.compropago = compropago

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

    def rescan_address(self, address):
        """Check an address to see if deposits have been made against it
        :param address: the address we are checking
        :type address: str
        """
        # TODO: find out why this is unicode
        # probably because of the way txZMQ does things
        address = address.encode("utf-8")
        logging.info("Scaning address %s for updates." % address)
        # TODO: find a better way of doing this
        if address.startswith("compropago"):
            payment_id = address.split("_", 1)[1]
            def error(failure):
                logging.warn("Could not get bill for id: %s. %s" % (payment_id, str(failure)))

            # Fetch the REAL bill from Compropago.
            d = self.compropago.get_bill(payment_id)
            d.addCallbacks(self.process_compropago_payment, error)

            # You can add an errback for process_compropago_payment here.
            # Alternatively, error handle inside the method itself (recommended)
        else:
            # TODO: do not assume BTC
            # TODO: add error checks
            total_received = int(self.bitcoinrpc["BTC"].getreceivedbyaddress(address, self.minimum_confirmations) * int(1e8))
            accounted_for = self.session.query(models.Addresses).filter_by(address=address).one().accounted_for
            if total_received > accounted_for:
                self.notify_accountant(address, total_received)

    def check_for_crypto_deposits(self, currency='BTC'):
        """
        Checks for crypto deposits in a crypto currency that offers
        a connection compatible with the bitcoind RPC (typically, litecoin, dogecoin...)
        :param currency: the btc-like currency for which to check for deposits
        :type currency: str
        """
        logging.info('checking for deposits')
        # first we get the confirmed deposits
        confirmed_deposits = self.bitcoinrpc[currency].listreceivedbyaddress(self.minimum_confirmations)
        # ok, so now for each address get how much was received
        total_received = {row.address: int(row.amount * int(1e8)) for row in confirmed_deposits}
        # but how much have we already accounted for?
        accounted_for = {row.address: row.accounted_for for row in
                         self.session.query(models.Addresses).filter_by(active=True)}

        # so for all the addresses we're dealing with
        for address in set(total_received.keys()).intersection(set(accounted_for.keys())):
            # if we haven't accounted for all the deposits
            if total_received[address] > accounted_for[address]:
                # tell the accountant
                self.notify_accountant(address, total_received[address])

    def check_withdrawal(self, withdrawal):
        """
        list withdrawal requests that have been entered and processed them
        either immediately or by pushing them to manual verification
        :raises: NotImplementedError
        """
        # if the transaction is innocuous enough
        logging.info("Checking withdrawal: %s" % withdrawal)
        if self.pass_safety_check(withdrawal):
            self.process_withdrawal(withdrawal.id, online=True)
        else:
            pass
            # TODO: Email the user
            #self.notify_pending_withdrawal(withdrawal)

    def pass_safety_check(self, withdrawal_request):
        """
        :param withdrawal_request: a specific request for withdrawal, to be accepted for immediate
                withdrawal or wait until manual validation
        :type withdrawal_request: dict

        NOT IMPLEMENTED
        """

        # 1) do a query for the last 24 hours of the 'orders submitted for cancellation'  keep it under 5bt
        # (what does this mean)
        # 2) make sure we have enough btc on hand - we should have at least 10x the btc onhand than the withdrawal is for
        # 3) make sure the withdrawal is small (< 1 BTC)
        # Not yet implemented
        if withdrawal_request.amount >= 100000000:
            logging.error("withdrawal too large, failing safety check")
            return False
        else:
            online_cash = self.accountant.get_position('onlinecash', withdrawal_request.contract.ticker)
            logging.error("withdrawal too large portion of online cash balance, failing safety check")
            if online_cash / 10 <= withdrawal_request.amount:
                return False

        # None of the checks failed, return True
        return True

    def process_withdrawal(self, withdrawal_id, online=False, cancel=False):
        # Mark a withdrawal as complete, send the money from the BTC wallet if online=True
        # and tell the accountant that the withdrawal has happened
        # If cancel=True, then return the money to the user
        logging.info("Processing withdrawal: %d online=%s cancel=%s" % (withdrawal_id, online, cancel))
        try:
            try:
                withdrawal = self.session.query(models.Withdrawal).filter_by(id=withdrawal_id).one()
            except NoResultFound:
                logging.error("No withdrawal found for id %d" % withdrawal_id)
                raise WITHDRAWAL_NOT_FOUND

            logging.debug("Withdrawal found: %s" % withdrawal)
            if not withdrawal.pending:
                raise WITHDRAWAL_COMPLETE

            if cancel:
                to_user = withdrawal.username
            else:
                if online:
                    self.bitcoinrpc[withdrawal.contract.ticker].sendtoaddress(withdrawal.address, float(withdrawal.amount / 1e8))
                    to_user = 'onlinecash'
                else:
                    to_user = 'offlinecash'

            self.accountant.transfer_position(withdrawal.contract.ticker, 'pendingwithdrawal', to_user, withdrawal.amount)
            withdrawal.pending = False
            withdrawal.completed = datetime.utcnow()
            self.session.add(withdrawal)
            self.session.commit()
        except Exception as e:
            logging.error("Exception when trying to process withdrawal: %s" % e)
            self.session.rollback()
            raise e

    def request_withdrawal(self, username, ticker, address, amount):
        try:
            user = self.session.query(models.User).filter_by(username=username).one()
            contract = self.session.query(models.Contract).filter_by(ticker=ticker).one()
            withdrawal = models.Withdrawal(user, contract, address, amount)
            self.session.add(withdrawal)
            self.session.commit()

            self.check_withdrawal(withdrawal)
        except Exception as e:
            logging.error("Exception when creating withdrawal ticket: %s" % e)
            self.session.rollback()


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
        self.notify_accountant(address, amount)

    def notify_pending_withdrawal(self):
        """
        email notification of withdrawal pending to the user.
        NOT IMPLEMENTED

        :raises: NotImplementedError:
        """
        raise NotImplementedError()

    def get_new_address(self, username, ticker):
        address = self.session.query(models.Addresses).join(models.Contract).filter(models.Addresses.username == username,
                                                    models.Addresses.active == False,
                                                    models.Contract.ticker == ticker).order_by(models.Addresses.id).first()

        if address is None:
            if ticker == "BTC":
                # TODO: Generate new BTC addresses as needed
                raise OUT_OF_ADDRESSES
            else:
                try:
                    address_str = base64.b64encode(("%016X" % getrandbits(64)).decode("hex"))
                    contract = self.session.query(models.Contract).filter_by(ticker=ticker).one()
                    user = self.session.query(models.User).filter_by(username=username).one()

                    address = models.Addresses(user, contract, address_str)
                    address.active = True
                    self.session.add(address)
                    self.session.commit()
                    return address.address
                except Exception as e:
                    logging.error("Unable to create new address for: %s/%s: %s" % (username, ticker, e))
                    self.session.rollback()
                    raise e
        else:
            address.active = True
            try:
                self.session.add(address)
                self.session.commit()
            except Exception as e:
                logging.error("Exception while activating address %s: %s" % (address, e))
                self.session.rollback()
                raise e

            return address.address

    def get_current_address(self, username, ticker):
        address = self.session.query(models.Addresses).join(models.Contract).filter(models.Addresses.username==username,
                                                    models.Addresses.active==True,
                                                    models.Contract.ticker==ticker).first()
        if address is None:
            return self.get_new_address(username, ticker)
        else:
            return address.address

    def get_deposit_instructions(self, ticker):
        if ticker == "BTC":
            return "Deposit using BTC to this address"
        else:
            return "Go to the bank and use this code in the special notes"

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
        self.cashier.rescan_address("compropago_" + payment_id)

        return "OK"


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
        self.cashier.rescan_address(address)

    @export
    def process_withdrawal(self, address, online=False, cancel=False):
        self.cashier.process_withdrawal(address, online=online, cancel=cancel)

class AccountantExport:
    def __init__(self, cashier):
        self.cashier = cashier

    @export
    def request_withdrawal(self, username, ticker, address, amount):
        self.cashier.request_withdrawal(username, ticker, address, amount)

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s', level=logging.DEBUG)

    accountant = dealer_proxy_sync(config.get("accountant", "cashier_export"))

    session = db.make_session()
    bitcoin_conf = config.get("cashier", "bitcoin_conf")

    logging.info('connecting to bitcoin client')

    bitcoinrpc = {'BTC': bitcoinrpc.connect_to_local(bitcoin_conf)}
    compropago = Compropago(config.get("cashier", "compropago_key"))

    cashier = Cashier(session, accountant, bitcoinrpc, compropago)

    administrator_export = AdministratorExport(cashier)
    accountant_export = AccountantExport(cashier)
    webserver_export = WebserverExport(cashier)

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
        # contextFactory = ssl.DefaultOpenSSLContextFactory(key, cert)
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
