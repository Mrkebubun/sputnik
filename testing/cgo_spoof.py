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
                        "id": "fe92a1a5-abec-49e3-877c-5024c1464dc3",
                        "object": "charge",
                        "created_at": "2013-12-09T18:59:28.048Z",
                        "paid": True,
                        "amount": "150.00",
                        "currency": "mxn",
                        "refunded": False,
                        "fee": "7.50",
                        "fee_details": {
                            "amount": "7.50",
                            "currency": "mxn",
                            "type": "compropago_fee",
                            "description": "Honorarios de ComproPago",
                            "application": None,
                            "amount_refunded": 0,
                        },
                        "payment_details": {
                            "object": "cash",
                            "store": "OXXO",
                            "country": "MX",
                            "product_id": "SMGCURL1",
                            "product_price": "150.00",
                            "product_name": "SAMSUNG GOLD CURL",
                            "image_url": "https://test.amazon.com/5f4373",
                            "success_url": "",
                            "customer_name": "Alejandra Leyva",
                            "customer_email": "noreply@compropago.com",
                            "customer_phone": "2221515801",
                        },
                        "captured": True,
                        "failure_message": None,
                        "failure_code": None,
                        "amount_refunded": 0,
                        "description": "Estado del pago - ComproPago",
                        "dispute": None
                    }

requests.post('http://localhost:8181/compropago', data=json.dumps(cgo_response))