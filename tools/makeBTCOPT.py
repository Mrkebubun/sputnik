#! /usr/bin/python2.7

import models
import database as db
import datetime

db_session = db.Session()

weekdays = ['Sn','M','T','W','Th','F','S']

ticker = 'BTC.BINARY.' + weekdays[datetime.date.today().weekday()]

newContract = models.Contract(  ticker,
                                'Binary on BTC',
                                'Week long prediction on BTC/USD started daily at current VWAP',
                                'prediction')

newContract.denominator = 100000000L
newContract.tick_size = 100000

db_session.add(newContract)

newPredictionContract = models.PredictionContract(newContract)

newPredictionContract.final_payoff = 100000000L
db_session.add(newPredictionContract)
db_session.commit()
