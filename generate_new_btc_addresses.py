from sqlalchemy.orm.exc import NoResultFound
import models
import database as db
import bitcoinrpc

db_session = db.Session()
TESTNET = True

if TESTNET:
    conn = bitcoinrpc.connect_to_remote('bitcoinrpc','E39Vf7y6S8sRAW2YrDqaLJxtPRWekyVw4E6Sv3z8R4N8',port=18332)
else:
    raise NotImplementedError()
    #conn = bitcoinrpc.connect_to_local()

quantity = 100

for i in range(quantity):
    addr = conn.getnewaddress()
    new_address = models.Addresses(None,'btc', addr)
    db_session.add(new_address)
db_session.commit()
