#! /usr/bin/python2.7
import augmentPythonPath
import sputnik.server.pepsi.models as models
import sputnik.server.pepsi.database as db

db_session = db.Session()

activeMarkets = db_session.query(models.Contract).filter_by(active=True).all()

for market in activeMarkets:
    print market.ticker
