#!/usr/bin/env python
from sqlalchemy.orm.exc import NoResultFound
import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
    "../server"))

from sputnik import database, models
import bitcoinrpc

db_session = database.Session()
TESTNET = True

if TESTNET:
    conn = bitcoinrpc.connect_to_remote('bitcoinrpc','E39Vf7y6S8sRAW2YrDqaLJxtPRWekyVw4E6Sv3z8R4N8',port=18332)
else:
    raise NotImplementedError()
    #conn = bitcoinrpc.connect_to_local()


conn.walletpassphrase('pass',10, dont_raise=True)
conn.keypoolrefill()

quantity = 100

for i in range(quantity):
    addr = conn.getnewaddress()
    new_address = models.Addresses(None,'btc', addr)
    db_session.add(new_address)
    print 'adding: ', addr
db_session.commit()
print 'committed'

conn.walletlock()
