#!/usr/bin/env python
__author__ = 'satosushi'

"""
A small fowarding service, every engine publishes their safe price to the frontend
and every safe price consumer subscribes to this device.
"""

import zmq

from optparse import OptionParser
parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
    help="config file", default="../config/sputnik.ini")
(options, args) = parser.parse_args()

from ConfigParser import SafeConfigParser
config = SafeConfigParser()
config.read(options.filename)


def main():

    try:
        context = zmq.Context(1)
        # Socket facing clients
        frontend = context.socket(zmq.SUB)
        frontend.bind(config.get("safe_price_forwarder", "zmq_frontend_address"))

        frontend.setsockopt(zmq.SUBSCRIBE, "")

        # Socket facing services
        backend = context.socket(zmq.PUB)
        backend.bind("zmq_backend_address")

        zmq.device(zmq.FORWARDER, frontend, backend)
    except Exception, e:
        print e
        print "bringing down zmq device"
    finally:
        pass
        frontend.close()
        backend.close()
        context.term()

if __name__ == "__main__":
    main()
