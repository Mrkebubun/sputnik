import treq
import json
import hmac
import hashlib
import urlparse

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue

ENDPOINTS = {"test":"https://test.bitgo.com/api/v1/",
             "production": "https://www.bitgo.com/api/v1/"}

class BitGoException(Exception):
    pass

class BadRequest(BitGoException):
    pass

class Unauthorized(BitGoException):
    pass

class MethodNotFound(BitGoException):
    pass

class BitGo(object):
    def __init__(self, use_production=False, debug=True):
        self.use_production = use_production
        self.debug = debug

        self.endpoint = ENDPOINTS["test"]
        if self.use_production:
            self.endpoint = ENDPOINTS["production"]

        self.token = None

    @inlineCallbacks
    def _call(self, method, url, data=None):
        url = urlparse.urljoin(self.endpoint, url)
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer %s" % self.token
      
        if data:
            data = json.dumps(data) # raises TypeError
        if self.debug:
            print "%s %s" % (method, url)
            print "Headers: %s" % str(headers)
            print "Data: %s" % data

        response = yield treq.request(method, url, headers=headers, data=data)
        code = response.code
        content = yield treq.content(response)

        try:
            content = json.loads(content)
        except ValueError as e:
            pass

        if code == 200:
            returnValue(content)
        elif code == 400:
            raise BadRequest(content)
        elif code == 401:
            raise Unauthorized(content)
        elif code == 404:
            raise MethodNotFound(content)
        else:
            raise BitGoException(content)

    def ping(self):
        return self._call("GET", "ping")

    def authenticate(self, email, password, otp=None):
        password = hmac.HMAC(email, password, hashlib.sha256).hexdigest()

        data = {"email":email, "password":password}
        if otp:
            data["otp"] = otp

        def save_token(data):
            self.token = data["access_token"]
            return data

        return self._call("POST", "user/login", data).addCallback(save_token)

    def logout(self):
        return self._call("GET", "user/logout")

    def session(self):
        return self._call("GET", "user/session")

    def sendOTP(self, force_sms=False):
        return self._call("GET", "user/sendotp", {"forceSMS":force_sms})

    def unlock(self, otp, duation=600):
        return self._call("POST", "user/unlock",
                          {"otp":otp, "duration":duration})

    def lock(self):
        return self._call("POST", "user/lock")

    def me(self):
        return self._call("GET", "user/me")

