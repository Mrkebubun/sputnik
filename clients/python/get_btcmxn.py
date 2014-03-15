# Copyright (c) 2014, Mimetic Markets, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# 1. Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
# IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
# TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
# TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

__author__ = 'sameer'

import json
import urllib2
from bs4 import BeautifulSoup
import pprint
data = {}
# Get bitstamp BTC/USD quote
url = "https://www.bitstamp.net/api/ticker/"
file_handle = urllib2.urlopen(url)
json_data = json.load(file_handle)
data['btcusd_bid'] = float(json_data['bid'])
data['btcusd_ask'] = float(json_data['ask'])

# Get google USD/MXN quote
url = "http://finance.yahoo.com/q?s=USDMXN=X"
file_handle = urllib2.urlopen(url)
soup = BeautifulSoup(file_handle)
data['usdmxn_bid'] = float(soup.find(id="yfs_b00_usdmxn=x").text)
data['usdmxn_ask'] = float(soup.find(id="yfs_a00_usdmxn=x").text)

data['btcmxn_bid'] = data['btcusd_bid'] * data['usdmxn_bid']
data['btcmxn_ask'] = data['btcusd_ask'] * data['usdmxn_ask']

pprint.pprint(data)
