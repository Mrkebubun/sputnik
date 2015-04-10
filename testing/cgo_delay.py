#!/usr/bin/python
#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

from twisted.web.resource import Resource
from twisted.web.server import Site
from twisted.internet import reactor

import time

data = '{"type":"charge.pending","object":"event","data":{"object":{"id":"364a8e62-ce78-48ab-bb74-b1a26214b270","short_id":"4825e2","object":"charge","created":"2014-03-18T03:11:41.773Z","paid":true,"amount":"5.00","currency":"mxn","refunded":false,"fee":"3.15","store_mode":"test","fee_details":{"amount":"3.15","currency":"mxn","type":"compropago_fee","description":"Honorarios de ComproPago","application":null,"amount_refunded":0},"payment_details":{"object":"cash","store":"OXXO","country":"MX","product_id":"","product_price":"5.00","product_name":"bitcoins","image_url":"","success_url":"","customer_name":"4b42bab2b33c3e4bd249363d3dc113258cd6afcc857eebf4938b0aa451d826a0","customer_email":"a@b.c","customer_phone":""},"captured":true,"failure_message":null,"failure_code":null,"amount_refunded":0,"description":"Estado del pago - ComproPago","dispute":null}}}'

class CompropagoEmulator(Resource):
    def __init__(self, data):
        Resource.__init__(self)
        self.isLeaf = True
        self.data = data

    def render(self, request):
        time.sleep(5)
        return self.data

cgo_server = Resource()
cgo_server.putChild('v1', CompropagoEmulator(data))
reactor.listenTCP(20000, Site(cgo_server))
reactor.run()
