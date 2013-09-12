#! /usr/bin/python2.7

import models
import database as db

db_session = db.Session()

activeMarkets = db_session.query(models.Contract).filter_by(active=True).all()

for market in activeMarkets:
    print market.ticker
