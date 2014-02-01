#!/usr/bin/env python
from sqlalchemy.orm.exc import NoResultFound
import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
    "../server"))

from sputnik import database, models
import bitcoinrpc
import getpass

db_session = database.make_session(username=getpass.getuser())
conn = bitcoinrpc.connect_to_local('../dist/config/bitcoin.conf')

#conn.walletpassphrase('pass',10, dont_raise=True)
conn.keypoolrefill()

quantity = 100

for i in range(quantity):
    addr = conn.getnewaddress()
    new_address = models.Addresses(None,'btc', addr)
    db_session.add(new_address)
    print 'adding: ', addr
db_session.commit()
print 'committed'

#conn.walletlock()
