#!/usr/bin/env python
import config
from optparse import OptionParser
parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
        help="config file", default="../config/sputnik.ini")
(options, args) = parser.parse_args()
if options.filename:
    config.reconfigure(options.filename)

SECONDS_TO_SLEEP = 1
MINIMUM_CONFIRMATIONS = 0
TESTNET = True
COLD_WALLET_ADDRESS = "bleh"  #make this a multisig?
ACCOUNTANT_PORT = 4432

import zmq
import models
import database as db
import logging
import bitcoinrpc
import time


logging.basicConfig(level=logging.DEBUG)
bitcoin_conf = config.get("cashier", "bitcoin_conf")

conn = bitcoinrpc.connect_to_local(bitcoin_conf)
logging.info('connecting to bitcoin client')

# push to the accountant
context = zmq.Context()
accountant = context.socket(zmq.PUSH)
#accountant.connect('tcp://localhost:%d' % ACCOUNTANT_PORT)
accountant.connect(config.get("accountant","zmq_address"))

#query the active addresses
db_session = db.make_session()


def notify_accountant(address, total_received):
    accountant.send_json({'deposit_cash': {'address':address,
                                            'total_received':total_received
                                            }
                        })

def check_for_deposits():
    logging.info('checking for deposits')
    confirmed_deposits = conn.listreceivedbyaddress(MINIMUM_CONFIRMATIONS)

    total_received = {row.address: int(row.amount * int(1e8)) for row in confirmed_deposits}
    accounted_for = {row.address: row.accounted_for for row in db_session.query(models.Addresses).filter_by(active=True)}

    for address in set(total_received.keys()).intersection(set(accounted_for.keys())):
        if total_received[address] > accounted_for[address]:
            notify_accountant(address, total_received[address])
            logging.info('updating address: %s to %d from %d' % (address, total_received[address], accounted_for[address]))

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

blockchain_time = 0
while True:
    if blockchain_time < conn.getinfo().blocks:
        check_for_deposits()
        #check_for_withdrawals()
        #blockchain_time = conn.getinfo().blocks

    time.sleep(SECONDS_TO_SLEEP)

