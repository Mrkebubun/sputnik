#!/usr/bin/env python
from optparse import OptionParser

from twisted.web.resource import Resource
from twisted.web.server import Site
from twisted.internet import reactor

import config
from zmq_util import dealer_proxy_async
import zmq
import models
import database as db
import logging
import bitcoinrpc

parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
                  help="config file", default="../config/sputnik.ini")
(options, args) = parser.parse_args()
if options.filename:
    config.reconfigure(options.filename)

SECONDS_TO_SLEEP = 1
MINIMUM_CONFIRMATIONS = 0
TESTNET = config.get("cashier", "testnet")
COLD_WALLET_ADDRESS = "bleh"  #make this a multisig?


logging.basicConfig(level=logging.DEBUG)
bitcoin_conf = config.get("cashier", "bitcoin_conf")

conn = bitcoinrpc.connect_to_local(bitcoin_conf)
logging.info('connecting to bitcoin client')

# push to the accountant
accountant = dealer_proxy_async(config.get("accountant", "webserver_export"))

#query the active addresses
db_session = db.make_session()

def notify_accountant(address, total_received):
    accountant.deposit_cash({'address': address, 'total_received': total_received})

def check_for_deposits():
    logging.info('checking for deposits')
    confirmed_deposits = conn.listreceivedbyaddress(MINIMUM_CONFIRMATIONS)

    total_received = {row.address: int(row.amount * int(1e8)) for row in confirmed_deposits}
    accounted_for = {row.address: row.accounted_for for row in
                     db_session.query(models.Addresses).filter_by(active=True)}

    for address in set(total_received.keys()).intersection(set(accounted_for.keys())):
        if total_received[address] > accounted_for[address]:
            notify_accountant(address, total_received[address])
            logging.info(
                'updating address: %s to %d from %d' % (address, total_received[address], accounted_for[address]))


def check_for_withdrawals():
    if safety_check():
        raise NotImplementedError()
    else:
        notify_pending_withdrawal()


def safety_check():
    '''
    1) do a query for the last 24 hours of the 'orders submitted for cancellation'  keep it under 5bt
    2) make sure we have enough btc on hand
    '''
    return False


def notify_pending_withdrawal():
    '''
    email notification of withdrawal pending
    '''
    raise NotImplementedError()


class CompropagoHook(Resource):
    isLeaf = True

    def render_POST(self, request):
        json_string = request.content.getvalue()
        logging.info('we got a compropago confirmation, do something about it: %s' % json_string)
        return "OK"


class BitcoinNotify(Resource):
    isLeaf = True

    def render_GET(self, request):
        """
        receives a notice from bitcoind containing a transaction hash
        @param request: the http request, typically containing the transaction hash
        @return: the string "OK", which isn't relevant
        """
        logging.info("Got a notification from bitcoind: %s" % request)
        check_for_deposits()
        return "OK"


if __name__ == '__main__':

    public_server = Resource()
    public_server.putChild('compropago', CompropagoHook())
    private_server = Resource()
    private_server.putChild('bitcoin', BitcoinNotify())

    reactor.listenTCP(config.get("cashier", "public_port"), Site(public_server),
                      interface=config.get("cashier", "public_interface"))
    reactor.listenTCP(config.get("cashier", "private_port"), Site(private_server),
                      interface=config.get("cashier", "private_interface"))

    reactor.run()
