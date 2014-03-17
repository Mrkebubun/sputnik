#!/usr/bin/env python

__author__ = 'sameer'

import requests


cgo_response = {}
requests.post('http://localhost:8181/', data=cgo_response)