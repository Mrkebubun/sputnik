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
        toencode_values = {}
        for outer_key, outer_value in input_values.iteritems():
            if isinstance(outer_value, dict):
                for inner_key, inner_value in outer_value.iteritems():
                    toencode_values['%s[%s]' % (outer_key, inner_key)] = inner_value
            else:
                toencode_values[outer_key] = outer_value

        data = urllib.urlencode(toencode_values)
        d = treq.post('https://api.blockscore.com/verifications', auth=(self.api_key,''),
                      headers = {"Accept": "application/vnd.blockscore+json;version=3",
                                 "Content-Type": "application/x-www-form-urlencoded"},
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
  date_of_birth = '1980-08-23'
  identification = {
    'ssn': '0000'
  }
  name = {
    'first': 'John',
    'middle': 'Pearce',
    'last': 'Doe'
  }
  address = {
    'street1': '1 Infinite Loop',
    'street2': 'Apt 6',
    'city': 'Cupertino',
    'state': 'CA',
    'postal_code': '95014',
    'country_code': 'US'
  }
  values = { 'date_of_birth': date_of_birth,
             'identification': identification,
             'name': name,
             'address': address
  }

  blockscore = BlockScore('sk_test_75a2d658d257e48b4d70f3b11a3afacc')
  d = blockscore.verify(values)
  d.addCallback(pprint)
  reactor.run()