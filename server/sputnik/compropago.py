__author__ = 'satosushi'

import json
import requests

from jsonschema import validate
from jsonschema import Validator


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

    def validate_response(self, payment_info):
        t = lambda x: dict(type=x, required=True)
        validate(payment_info, {
            'type': 'object',
            'properties': {
                'object': t('string'),
                'type': {'type': ['string', 'null']},
                'data': {'type': 'object',
                         'required': True,
                         'properties': {
                             'object': {'type': 'object',
                                        'required': True,
                                        'properties': {
                                            'id': t('string'),
                                            'short_id': t('string'),
                                            'store_mode': t('string'),
                                            'object': t('string'),
                                            'created': t('string'),
                                            'paid': t('boolean'),
                                            'amount': t('string'),
                                            'currency': t('string'),
                                            'refunded': t('boolean'),
                                            'fee': t('string'),
                                            'fee_details': {'type': 'object', 'required': True,
                                                            'properties': {
                                                                'amount': t('string'),
                                                                'currency': t('string'),
                                                                'type': t('string'),
                                                                'description': t('string'),
                                                                'application': {'type': ['string', 'null'], 'required': True},
                                                                'amount_refunded': t('number')
                                                            }
                                            },
                                            'payment_details': {'type': 'object', 'required': True,
                                                                'properties': {
                                                                    'object': t('string'),
                                                                    'store': t('string'),
                                                                    'country': t('string'),
                                                                    'product_id': t('string'),
                                                                    'product_price': t('string'),
                                                                    'product_name': t('string'),
                                                                    'image_url': t('string'),
                                                                    'success_url': t('string'),
                                                                    'customer_name': t('string'),
                                                                    'customer_email': t('string'),
                                                                    'customer_phone': t('string'),
                                                                }
                                            },
                                            'captured': t('boolean'),
                                            'failure_message': {'type': ['string', 'null'], 'required': True},
                                            'failure_code': {'type': ['string', 'null'], 'required': True},
                                            'amount_refunded': t('number'),
                                            'description': t('string'),
                                            'dispute': {'type': ['string', 'null'], 'required': True}
                                        }}}}}})
        return payment_info['data']['object']


# 'sk_test_5b82f569d4833add'
if __name__ == '__main__':
    abtest = Compropago('sk_test_5b82f569d4833add')
    bill = abtest.create_bill(Charge(11000, 'Satoshi Nakamoto', 'satoshi@bitcoin.it', '2221515801', 'OXXO'))
    print bill
    status = abtest.get_bill(bill['payment_id'])
    print status
    abtest.validate_response(status)
    #print abtest.get_all()



