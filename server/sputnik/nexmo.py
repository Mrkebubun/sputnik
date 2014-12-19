__author__ = 'sameer'

import treq
import json
from twisted.python import log

class NexmoException(Exception):
    pass

class Nexmo():
    def __init__(self, api_key, api_secret, brand):
        self.api_key = api_key
        self.api_secret = api_secret
        self.brand = brand

    @property
    def params(self):
        p = {'api_key': self.api_key,
                  'api_secret': self.api_secret}
        return p

    def verify(self, number, lg=None):
        params = {'number': number,
                  'brand': self.brand}
        if lg is not None:
            params.update({'lg': lg})
        params.update(self.params)

        d = treq.get("https://api.nexmo.com/verify/json", params=params)
        def handle_response(response):
            def parse_content(content):
                result = json.loads(content)
                log.msg("Nexmo returned: %s" % content)

                if result['status'] == "0":
                    return result['request_id']
                else:
                    raise NexmoException(result['status'], result['error_text'])

            response.content().addCallback(parse_content)

        d.addCallback(handle_response)
        return d

    def check(self, request_id, code):
        params = {'request_id': request_id,
                  'code': code}
        params.update(self.params)

        d = treq.get("https://api.nexmo.com/check/json", params=params)
        def handle_response(response):
            def parse_content(content):
                result = json.loads(content)
                log.msg("Nexmo returned: %s" % content)

                if result['status'] == "0":
                    return True
                else:
                    log.msg("Verification check failed: %s/%s" % (result['status'], result['error_text']))
                    return False

            response.content().addCallback(parse_content)

        d.addCallback(handle_response)
        return d

    def sms(self, number, message):
        message_encoded = message.encode('utf-8')
        params = {'from': '12342492074',
                  'to': number,
                  'type': 'unicode',
                  'text': message_encoded
                  }
        params.update(self.params)

        d = treq.get("https://rest.nexmo.com/sms/json", params=params)
        def handle_response(response):
            def parse_content(content):
                result = json.loads(content)
                log.msg("Nexmo returned: %s" % content)
                errors = []

                for message in result['messages']:
                    if message['status'] != "0":
                        errors.append((message['status'], message['error-text']))

                if len(errors):
                    raise NexmoException(errors)

            response.content().addCallback(parse_content)

        d.addCallback(handle_response)
        return d

if __name__ == "__main__":
    from twisted.internet import reactor
    from pprint import pprint
    import sys
    log.startLogging(sys.stdout)

    nexmo = Nexmo('66315463','cea39b06', 'Test')
    d = nexmo.verify('13035694439')
    d.addCallback(pprint).addErrback(log.err)

    d = nexmo.sms('13035694439', 'hello there')
    d.addCallback(pprint).addErrback(log.err)

    reactor.run()
