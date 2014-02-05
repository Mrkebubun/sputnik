import json

__author__ = 'satosushi'
import urllib2

import requests

class Charge:
    def __init__(self,
                 price,
                 customer_name,
                 customer_email,
                 customer_phone,
                 payment_type,
                 send_sms=False,
                 currency='MXN',
                 product_name='MEXBT',
                 product_id='MXN',
                 image_url='http://www.sputnik.com/BC_Logo_.png'):
        self.price, self.currency = price, currency
        self.customer_name, self.customer_email, self.customer_phone = customer_name, customer_email, customer_phone
        self.payment_type, self.send_sms = payment_type, send_sms
        self.product_name, self.product_id = product_name, product_id
        self.image_url = image_url


class Compropago:
    base_URL = 'http://api.compropago.com'
    charge_URL = base_URL + '/v1/charges'
    headers = {'Accept': 'application/compropago+json',
               'Content-Type': 'application/json'}
    def __init__(self, key):
        self.key = key

    def create_bill(self, charge):
        r = requests.post(self.charge_URL,
                          data=json.dumps(charge.__dict__),
                          headers=self.headers, auth=(self.key, ''))
        return r.json()


    def get_bill(self, payment_id):
        r = requests.get(self.charge_URL + '/' + payment_id, auth=(self.key, ''))
        return r.json()

    def get_all(self):
        r = requests.get(self.charge_URL, auth=(self.key, ''))
        print r.text
        return r.json()




# 'sk_test_5b82f569d4833add'
abtest = Compropago('sk_test_5b82f569d4833add')
#bill = abtest.create_bill(Charge(11000, 'Satoshi Nakamoto', 'satoshi@bitcoin.it', '2221515801', 'OXXO'))
#print bill
#status = abtest.get_bill(bill['payment_id'])
#print status
print abtest.get_all()



