import time

__author__ = 'satosushi'

import database as db
import models
import os

db_session = db.Session()

for contract in db_session.query(models.Contract).filter_by(active=True):
    print [contract.ticker, contract.id]
    os.system('python /home/arthurb/code/matching_engine/engine.py %s %d &' % (contract.ticker, contract.id))

while True:
    time.sleep(10)
