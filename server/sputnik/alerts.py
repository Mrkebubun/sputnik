from sendmail import Sendmail

class Alerts(object):
    def __init__(self, from_address, to_address, subject_prefix):
        self.factory = Sendmail(from_address)
        self.from_address = from_address
        self.to_address = to_address
        self.subject_prefix = subject_prefix

    def alert(self, message, subject):
        process = self.factory.send_mail(message, subject=self.subject_prefix + " " + subject,
                                         to_address=self.to_address)



