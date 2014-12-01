import config

from optparse import OptionParser
parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
    help="config file", default="../config/sputnik.ini")
(options, args) = parser.parse_args()
if options.filename:
    config.reconfigure(options.filename)

import re
import datetime

__author__ = 'satosushi'

"""
The risk manager manages the financial risk taken by the exchange when extending trading margins.
For now this just means pinging the accountant regularly to see if everyone's margin is in check
"""


from sqlalchemy.orm.exc import NoResultFound
import models
import database
import margin
import util
from sendmail import Sendmail

from twisted.python import log
from twisted.internet import reactor
from zmq_util import connect_subscriber
import json
from jinja2 import Environment, FileSystemLoader
import time
import sys

class RiskManager():
    def __init__(self, session, sendmail, safe_price_subscriber, admin_templates='admin_templates', nap_time_seconds=60):
        self.session = session
        self.nap_time_seconds = nap_time_seconds
        self.jinja_env = Environment(loader=FileSystemLoader(admin_templates))
        self.sendmail = sendmail
        self.safe_price_subscriber = safe_price_subscriber
        self.last_call_time = 0
        self.safe_price_subscriber.subscribe('')
        self.safe_price_subscriber.gotMessage = self.on_safe_prices
        self.cash_positions = {}
        self.timestamps = {}
        self.low_margin_users = {}
        self.bad_margin_users = {}

        self.BTC = self.session.query(models.Contract).filter_by(ticker='BTC').one()

    def email_user(self, user, cash_position, low_margin, high_margin, severe):
        """

        :param user:
        :type user: User
        :param cash_position:
        :type cash_position: int
        :param low_margin:
        :type low_margin: int
        :param high_margin:
        :type high_margin: int
        :param severe:
        :type severe: bool
        """
        template_file = "margin_call.{locale}.email" if severe else "low_margin.{locale}.email"
        t = util.get_locale_template(user.locale, self.jinja_env, template_file)
        content = t.render(cash_position=util.quantity_fmt(self.BTC, cash_position),
                           low_margin=util.quantity_fmt(self.BTC, low_margin),
                           high_margin=util.quantity_fmt(self.BTC, high_margin), user=user).encode('utf-8')

        # Now send the mail
        log.msg("Sending mail: %s" % content)
        d = self.sendmail.send_mail(content, to_address=user.email,
                                    subject="Margin Call" if severe else "Margin Warning")
        d.addErrback(log.err)

        return d

    def on_safe_prices(self, *args):
        this_call_time = time.time()
        safe_prices = json.loads(args[0])
        # Don't run more than once per minute
        if this_call_time - self.last_call_time > self.nap_time_seconds:
            self.last_call_time = this_call_time


            self.session.expire_all()
            for user in self.session.query(models.User).filter_by(active=True).filter_by(type='Liability'):
                low_margin, high_margin, cash_spent = margin.calculate_margin(user.username, self.session, safe_prices)
                try:
                    cash_position_db = self.session.query(models.Position).filter_by(contract=self.BTC, user=user).one()
                except NoResultFound:
                    self.cash_positions[user.username] = 0
                else:
                    # Use calculated position
                    if user.username in self.timestamps:
                        self.cash_positions[user.username], self.timestamps[user.username] = \
                            util.position_calculated(cash_position_db, self.session, checkpoint=self.cash_positions[user.username],
                                                     start=self.timestamps[user.username])
                    else:
                        self.cash_positions[user.username], self.timestamps[user.username] = \
                            util.position_calculated(cash_position_db, self.session)


                if self.cash_positions[user.username] < low_margin:
                    if user.username not in self.bad_margin_users:
                        self.bad_margin_users[user.username] = datetime.datetime.utcnow()
                        self.email_user(user, self.cash_positions[user.username], low_margin, high_margin, severe=True)
                    result = "WARNING"
                elif self.cash_positions[user.username] < high_margin:
                    if user.username not in self.low_margin_users:
                        self.low_margin_users[user.username] = datetime.datetime.utcnow()
                        self.email_user(user, self.cash_positions[user.username], low_margin, high_margin, severe=False)
                    result = "CALL"
                else:
                    if user.username in self.low_margin_users:
                        del self.low_margin_users[user.username] # resolved
                    if user.username in self.bad_margin_users:
                        del self.bad_margin_users[user.username] # resolved
                    result = "OK"

                log.msg("%s: %s / %d %d %d" % (result, user.username, low_margin, high_margin,
                                                     self.cash_positions[user.username]))


if __name__ == "__main__":
    log.startLogging(sys.stdout)

    session = database.make_session()

    safe_price_subscriber = connect_subscriber(config.get("safe_price_forwarder", "zmq_backend_address"))
    safe_price_subscriber.subscribe('')
    sendmail = Sendmail(config.get("riskmanager", "from_email"))
    riskmanager = RiskManager(session, sendmail, safe_price_subscriber)

    reactor.run()
