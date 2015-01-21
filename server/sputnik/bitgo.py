import requests
import treq
import json
import hmac
import hashlib

ENDPOINTS = {"test":"https://test.bitgo.com/api/v1/",
             "prod": "https://www.bitgo.com/api/v1/"}

class BitGo(object):

    def __init__(self, test=False, async=False, debug=False):
        self.test = test
        self.async = async
        self.debug = debug

        self.endpoint = ENDPOINTS["prod"]
        if self.test:
            self.endpoint = ENDPOINTS["test"]
       
        self.agent = requests
        if self.async:
            self.agent = treq

        self.token = None

    def __getattr__(self, key):
        if key.startswith("__") and key.endswith("__"):
            raise AttributeError

        def remote_method(*args, **kwargs):
            url = self.endpoint + key + "/" + "/".join(args)

            headers = {"Content-Type": "application/json"}
            if self.token:
                headers["Authorization"] = "Bearer %s" % self.token

            if len(kwargs) == 0:
                d = self.agent.get(url, headers=headers)
            else:
                d = self.agent.post(url, headers=headers,
                                    data=json.dumps(kwargs))

            if self.async:
                return d.addCallback(treq.json_content)
            return d.json()

        return remote_method

    def login(self, email, password, otp="0000000"):
        password = hmac.HMAC(email, password, hashlib.sha256).hexdigest()
        d = self.user("login", email=email, password=password, otp=otp)
        if self.async:
            def save_token(data):
                self.token = data["access_token"]
                return data
            d.addCallback(save_token)
        else:
            self.token = d["access_token"]

        return d

b = BitGo(test=True, async=False, debug=True)
b.login("janedoe@bitgo.com", "mypassword", otp="0000000")

