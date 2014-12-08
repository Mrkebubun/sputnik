#!/usr/bin/env python

import config
from optparse import OptionParser
parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
    help="config file", default="../config/sputnik.ini")
(options, args) = parser.parse_args()
if options.filename:
    config.reconfigure(options.filename)

__author__ = 'satosushi'

"""
A small fowarding service, every engine publishes their safe price to the frontend
and every safe price consumer subscribes to this device.
"""

from zmq_util import bind_subscriber, bind_publisher
from twisted.internet import reactor
from twisted.python import log
import json

if __name__ == "__main__":
    import sys
    log.startLogging(sys.stdout)
    subscriber = bind_subscriber(config.get("safe_price_forwarder", "zmq_frontend_address"))
    publisher = bind_publisher(config.get("safe_price_forwarder", "zmq_backend_address"))

    subscriber.subscribe("")

    safe_prices = {}
    def onPrice(*args):
        update = json.loads(args[0])
        log.msg("received update: %s" % update)
        safe_prices.update(update)
        publisher.publish(json.dumps(safe_prices), tag=b'')

    subscriber.gotMessage = onPrice
    reactor.run()

