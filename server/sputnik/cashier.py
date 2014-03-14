#!/usr/bin/env python
import json
from optparse import OptionParser
import logging

from twisted.web.resource import Resource, ErrorPage
from twisted.web.server import Site
from twisted.internet import reactor

import bitcoinrpc
from compropago import Compropago

import config
from zmq_util import dealer_proxy_async
import models
import database as db
from jsonschema import ValidationError


parser = OptionParser()
parser.add_option("-c", "--config", dest="filename", help="config file", default="../config/sputnik.ini")
(options, args) = parser.parse_args()
if options.filename:
    config.reconfigure(options.filename)


class Cashier():
    """
    Handles communication between the outside world of deposits and withdrawals and
    the accountant. It does so by offering a public hook for Compropago and a private
    hook to the bitcoin client
    """
    minimum_confirmations = 0

    def __init__(self):
        """
        Initializes the cashier class by connecting to bitcoind and to the accountant
        also sets up the db session and some configuration variables
        """
        self.testnet = config.get('cashier', 'testnet')
        self.cold_wallet_address = 'xxxx'
        self.bitcoin_conf = config.get("cashier", "bitcoin_conf")
        self.accountant = dealer_proxy_async(config.get("accountant", "cashier_export"))
        logging.info('connecting to bitcoin client')
        self.conn = {'btc': bitcoinrpc.connect_to_local(self.bitcoin_conf)}
        self.session = db.make_session()
        self.compropago = Compropago(self)

    def notify_accountant(self, address, total_received):
        # tells the accountant an address has an updated "total received" amount
        """
        Notifies the accountant that the total received in a given address has increased
        and that this should be reflected as a deposit
        @param address: address where the deposit has been made
        @param total_received: total amount received for this address
        """
        logging.info('notifying the accountant that %s received %d' % (address, total_received))
        # note that this is *only* a notification to the accountant. We know at this point
        # that this address has received *at least* total_received. It will be up to the accountant
        # to update the "accounted_for" column to the total_received value while simulateously
        # increasing a user's position. We might not have caught *all of the deposited* money
        # but that can happen later and we're guaranteed to never miss a deposit in the long run
        # or to double credit someone incorrectly. Increasing "accounted_for" and increasing
        # the position is an atomic transaction. Cashier is *only telling* the accountant
        # what the state of the bitcoin client is.
        self.accountant.deposit_cash({'address': address, 'total_received': total_received})

    def check_for_crypto_deposits(self, currency='btc'):
        """
        Checks for crypto deposits in a crypto currency that offers
        a connection compatible with the bitcoind RPC (typically, litecoin, dogecoin...)
        @param currency: the btc-like currency for which to check for deposits
        """
        logging.info('checking for deposits')
        # first we get the confirmed deposits
        confirmed_deposits = self.conn[currency].listreceivedbyaddress(self.minimum_confirmations)
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

    def check_for_withdrawals(self):
        """
        list withdrawal requests that have been entered and processed them
        either immediately or by pushing them to manual verification
        @raise NotImplementedError:
        """
        # if the transaction is innocuous enough
        if self.pass_safety_check(None):
            raise NotImplementedError()
        # otherwise tell the user he'll have to wait
        else:
            self.notify_pending_withdrawal()

    def pass_safety_check(self, withdrawal_request):
        """
        @param withdrawal_request: a specific request for withdrawal, to be accepted for immediate
                withdrawal or wait until manual validation
        """
        # 1) do a query for the last 24 hours of the 'orders submitted for cancellation'  keep it under 5bt
        # 2) make sure we have enough btc on hand
        return False

    def process_compropago_payment(self, payment_info):
        """
        received payment information from a compropago payment and processes it
        @param payment_info: object representing a payment
        """
        address = 'compropago_%s' % payment_info['id']
        self.notify_accountant(address, payment_info['amount'])

    def notify_pending_withdrawal(self):
        """
        email notification of withdrawal pending to the user

        @raise NotImplementedError:
        """
        raise NotImplementedError()

class CompropagoHook(Resource):
    """
    Resource URL for compropago to give us callbacks
    @param cashier_: instance of the cashier
    """
    isLeaf = True

    def __init__(self, cashier_):
        Resource.__init__(self)
        self.cashier = cashier_

    def render_POST(self, request):
        """
        Compropago will post transaction details to us
        @param request: a json object representing the transaction details
        @return: anything as long as it's code 200
        """
        json_string = request.content.getvalue()
        #todo: re-request from compropago ourselves to avoid being fed
        #spoofed information

        logging.info('we got a compropago confirmation, do something about it: %s' % json_string)
        try:
            logging.info('validating the response')
            payment_info = self.compropago.validate_response(json.loads(json_string))
            self.cashier.process_compropago_payment(payment_info)
        except ValidationError:
            logging.error("Error in the input %s" % json_string)
            return ErrorPage()



        return "OK"


class BitcoinNotify(Resource):
    """
    A hook for the bitcoind client to notify us via curl or wget
    @param cashier:
    """
    isLeaf = True

    def __init__(self, cashier_):
        Resource.__init__(self)
        self.cashier = cashier_

    def render_GET(self, request):
        """
        receives a notice from bitcoind containing a transaction hash
        @param request: the http request, typically containing the transaction hash
        @return: the string "OK", which isn't relevant
        """
        logging.info("Got a notification from bitcoind: %s" % request)
        self.cashier.check_for_crypto_deposits('btc')
        return "OK"


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    cashier = Cashier()

    public_server = Resource()
    public_server.putChild('compropago', CompropagoHook(cashier))
    private_server = Resource()
    private_server.putChild('bitcoin', BitcoinNotify(cashier))

    reactor.listenTCP(config.getint("cashier", "public_port"), Site(public_server),
                      interface=config.get("cashier", "public_interface"))
    reactor.listenTCP(config.getint("cashier", "private_port"), Site(private_server),
                      interface=config.get("cashier", "private_interface"))

    reactor.run()
