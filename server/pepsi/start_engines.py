import time

__author__ = 'satosushi'

import database as db
import models
import os

db_session = db.Session()
BASE = os.getcwd()

for contract in db_session.query(models.Contract).filter_by(active=True):
    print [contract.ticker, contract.id]
    os.system('python %s/engine.py %s %d &' % (BASE, contract.ticker, contract.id))

