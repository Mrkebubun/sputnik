__author__ = 'arthurb'


import treq

import logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s')

from jsonschema import validate


class ReCaptcha:
    def __init__(self, private_key, public_key):
        """

        :param private_key:
        :type private_key: str
        :param public_key:
        :type public_key: str
        """
        self.private_key, self.public_key = private_key, public_key

    def verify(self, remote_ip, challenge, response):
        """

        :param remote_ip:
        :param challenge:
        :param response:
        :returns: Deferred
        :raises: Exception
        """

        def handle_response(response):

            def parse_content(content):
                if response.code != 200:
                    logging.warn('Received code: %d from Google for recaptcha' % response.code)
                    raise Exception("Recaptacha returned code: %d" % response.code)
                c = content.splitlines().append('') #being cheeky here
                if len(c) < 2:
                    logging.error("Received unexpected response from recaptcha: %s" % content)
                    raise Exception("Received unexpected response from recaptcha: %s" % content)
                return [c[0] == "true", c[1]] #eheh c[1] always exist

            return response.content().addCallback(parse_content)

        d = treq.post(self.url, data={
            'privatekey': self.private_key,
            'remoteip': remote_ip,
            'challenge': challenge,
            'response': response}, timeout=5)

        d.addCallback(handle_response)
        return d

