from decimal import Decimal
import hashlib
import hmac
import httplib
import json
import urllib

__author__ = 'arthurb'


from selenium import webdriver
import re
import time
import btceapi


def buy_a_ton_of_ltc(amount_in_btc):
    handler = btceapi.KeyHandler('btc_e_session.txt')
    key = handler.getKeys()[0]
    trade_api = btceapi.TradeAPI(key, handler)
    trade_api.trade('ltc_btc', 'buy', Decimal('0.05'), 20 * amount_in_btc)
    exit()


chrome = webdriver.Chrome()
ltc_re = re.compile(r'litecoin', re.IGNORECASE | re.MULTILINE)

while True:
    chrome.get('http://www.mtgox.com')
    content = chrome.find_element_by_tag_name('body').get_attribute('innerHTML')
    if ltc_re.search(content):
        buy_a_ton_of_ltc(amount_in_btc=67.05)
    else:
        print "NO litecoin :("
    time.sleep(10)



