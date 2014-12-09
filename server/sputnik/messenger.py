__author__ = 'sameer'

from email.mime.text import MIMEText
from twisted.mail import smtp
from jinja2 import Environment, FileSystemLoader, TemplatesNotFound
import util
import treq
import json
from twisted.python import log

class Sendmail(object):
    def __init__(self, from_address=None):
        self.from_address = from_address

    def send_mail(self, message, subject=None, to_address=None, to_nickname=None):
        msg = MIMEText(message, _charset='utf-8')
        msg['Subject'] = subject
        msg['From'] = self.from_address
        if to_nickname is not None:
            msg['To'] = '%s <%s>' % (to_nickname, to_address)
        else:
            msg['To'] = to_address

        smtp.sendmail("localhost", self.from_address, to_address, msg.as_string())

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
        params = {'from': '12342492074',
                  'to': number,
                  'type': 'unicode',
                  'text': message
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

class Messenger(object):
    def __init__(self, sendmail, nexmo=None, template_dir='admin_templates'):
        self.sendmail = sendmail
        self.nexmo = nexmo
        self.jinja_env = Environment(loader=FileSystemLoader(template_dir))

    def send_message(self, user, subject, template, **kwargs):
        if user.preference != "sms" and user.email is not None:
            try:
                t = util.get_locale_template(user.locale, self.jinja_env, "%s.{locale}.email" % template)
                content = t.render(user=user, **kwargs).encode('utf-8')
                log.msg("Sending mail to %s: %s" % (user.email, content))
                self.sendmail.send_mail(content, subject=subject, to_address=user.email)
            except TemplatesNotFound:
                log.msg("Can't find template %s/email" % template)

        if user.preference != "email" and user.phone is not None and self.nexmo is not None:
            try:
                t = util.get_locale_template(user.locale, self.jinja_env, "%s.{locale}.sms" % template)
                content = t.render(user=user, **kwargs).encode('utf-8')
                log.msg("Sending SMS to %s: %s" % (user.phone, content))
                self.nexmo.sms(user.phone, content)
            except TemplatesNotFound:
                log.msg("Can't find template %s/sms" % template)

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
