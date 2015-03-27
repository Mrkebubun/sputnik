#!/usr/bin/env python
#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

__author__ = 'sameer'

import requests
import json

cgo_response = {
  "type": None,
  "object": "event",
  "data": {
    "object": {
      "id": "364a8e62-ce78-48ab-bb74-b1a26214b270",
      "short_id": "63d870",
      "object": "charge",
      "created": "2014-03-12T07:02:32.536Z",
      "paid": True,
      "amount": "4.00",
      "currency": "mxn",
      "refunded": False,
      "fee": "3.12",
      "store_mode": "test",
      "fee_details": {
        "amount": "3.12",
        "currency": "mxn",
        "type": "compropago_fee",
        "description": "Honorarios de ComproPago",
        "application": None,
        "amount_refunded": 0
      },
      "payment_details": {
        "object": "cash",
        "store": "OXXO",
        "country": "MX",
        "product_id": "",
        "product_price": "4.00",
        "product_name": "bitcoins",
        "image_url": "",
        "success_url": "",
        "customer_name": "59d305fe6ee621477299ef63a6ecd8890c7f2412a3e77997deb03a4e87a0d497",
        "customer_email": "a@b.c",
        "customer_phone": ""
      },
      "captured": True,
      "failure_message": None,
      "failure_code": None,
      "amount_refunded": 0,
      "description": "Estado del pago - ComproPago",
      "dispute": None
    }
  }
}

requests.post('http://localhost:8181/compropago', data=json.dumps(cgo_response))
