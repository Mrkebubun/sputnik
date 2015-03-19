__author__ = 'sameer'


import treq
import json
from twisted.internet import reactor
import urllib
from pprint import pprint


class BlockScore():
    def __init__(self, api_key):
        self.api_key = api_key

    def verify(self, input_values):
        data = urllib.urlencode(dict([k.encode('utf-8'),unicode(v).encode('utf-8')] for k,v in input_values.items()))
        d = treq.post('https://api.blockscore.com/people', auth=(self.api_key,''),
                      headers = {"Accept": "application/vnd.blockscore+json;version=4",
                                 "Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
                      data=data
                      )

        def handle_response(response):
            def parse_content(content):
                result = json.loads(content)
                return result

            return response.content().addCallback(parse_content)


        d.addCallback(handle_response)
        return d



if __name__ == "__main__":

  values = {'name_first': 'John',
            'name_middle': 'Pearce',
           'name_last': 'Doe',
           'document_type': 'ssn',
           'document_value': '0000',
           'birth_day': '23',
           'birth_month': '8',
           'birth_year': '1980',
           'address_street1': '1 Infinite Loop',
           'address_street2': 'Apt 6',
           'address_city': 'Cupertino',
           'address_subdivision': 'CA',
           'address_postal_code': '95014',
           'address_country_code': 'US'}


  blockscore = BlockScore('sk_test_75a2d658d257e48b4d70f3b11a3afacc')
  d = blockscore.verify(values)
  d.addCallback(pprint)
  reactor.run()