__author__ = 'satosushi'

"""
The risk manager manages the financial risk taken by the exchange when extending trading margins.
For now this just means pinging the accountant regularly to see if everyone's margin is in check
"""


from sqlalchemy.orm.exc import NoResultFound
import zmq
import models
import database
import logging
import json


NAP_TIME_SECONDS = 10

from optparse import OptionParser
parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
    help="config file", default="../config/sputnik.ini")
(options, args) = parser.parse_args()

from ConfigParser import SafeConfigParser
config = SafeConfigParser()
config.read(options.filename)

session = database.Session()

context = zmq.Context()
safe_price_subscriber = context.socket(zmq.SUB)
safe_price_subscriber.connect(config.get("safe_price_forwader", "zmq_backend_address"))


# main loop
while True:

    # todo we should loop on the union of of safe price and message from the accountant asking us to take action
    safe_prices = safe_price_subscriber.recv_json()
    for user in session.query(models.User).filter_by(active=True):
        print "Here, check the margin of this user and deal with it appropriately"

