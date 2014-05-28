__author__ = 'sameer'

from email.mime.text import MIMEText
from twisted.mail import smtp

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

