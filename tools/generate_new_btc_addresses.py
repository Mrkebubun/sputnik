#!/usr/bin/env python
from sqlalchemy.orm.exc import NoResultFound
import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
    "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
    "../dist/config"))

from sputnik import database, models
from sputnik import txbitcoinrpc
import getpass
from sputnik import config
from twisted.internet import defer, reactor

db_session = database.make_session(username=getpass.getuser())
print config.get("cashier","bitcoin_conf")
conn = txbitcoinrpc.BitcoinRpc(config.get("cashier", "bitcoin_conf"))

#conn.walletpassphrase('pass',10, dont_raise=True)
conn.keypoolrefill()

quantity = 100

dl = defer.DeferredList([conn.getnewaddress() for i in range(quantity)])

def add_addresses(results):
    for r in results:
        addr = r[1]['result']
        BTC = db_session.query(models.Contract).filter_by(ticker='BTC').one()
        new_address = models.Addresses(None, BTC, addr)
        db_session.add(new_address)
        print 'adding: ', addr
    db_session.commit()
    print 'committed'
    reactor.stop()

dl.addCallback(add_addresses)
reactor.run()
