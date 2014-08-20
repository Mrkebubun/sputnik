#!/usr/bin/env python
from sqlalchemy.orm.exc import NoResultFound
import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
    "../server"))

from sputnik import database, models
import bitcoinrpc
import getpass
from sputnik import config

db_session = database.make_session(username=getpass.getuser())
print config.get("cashier","bitcoin_conf")
conn = bitcoinrpc.connect_to_local(config.get("cashier", "bitcoin_conf"))

#conn.walletpassphrase('pass',10, dont_raise=True)
conn.keypoolrefill()

quantity = 100

for i in range(quantity):
    addr = conn.getnewaddress()["result"]
    BTC = db_session.query(models.Contract).filter_by(ticker='BTC').one()
    new_address = models.Addresses(None, BTC, addr)
    db_session.add(new_address)
    print 'adding: ', addr
db_session.commit()
print 'committed'

#conn.walletlock()
