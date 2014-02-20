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
