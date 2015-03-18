#!/usr/bin/env python
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
from messenger import Messenger, Sendmail, Nexmo
from accountant import AccountantProxy

from twisted.python import log
from twisted.internet import reactor
from zmq_util import connect_subscriber
import json
from jinja2 import Environment, FileSystemLoader
import time
import sys

class RiskManager():
    def __init__(self, session, messenger, safe_price_subscriber, accountant, admin_templates='admin_templates', nap_time_seconds=60):
        self.session = session
        self.nap_time_seconds = nap_time_seconds
        self.jinja_env = Environment(loader=FileSystemLoader(admin_templates))
        self.messenger = messenger
        self.safe_price_subscriber = safe_price_subscriber
        self.accountant = accountant
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
        template = "margin_call" if severe else "low_margin"
        subject = "Margin Call" if severe else "Margin Warning"

        self.messenger.send_message(user, subject, template, 'margin',
                           cash_position=util.quantity_fmt(self.BTC, cash_position),
                           low_margin=util.quantity_fmt(self.BTC, low_margin),
                           high_margin=util.quantity_fmt(self.BTC, high_margin))


    def on_safe_prices(self, *args):
        this_call_time = time.time()
        safe_prices = json.loads(args[0])
        log.msg("Safe prices received: %s" % safe_prices)
        # Don't run more than once per minute
        if this_call_time - self.last_call_time > self.nap_time_seconds:
            self.last_call_time = this_call_time


            self.session.expire_all()
            for user in self.session.query(models.User).filter_by(active=True).filter_by(type='Liability'):
                low_margin, high_margin, cash_spent = margin.calculate_margin(user, self.session, safe_prices)
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

                    d = self.accountant.liquidate_best(user.username)
                    d.addErrback(log.err)
                    result = "CALL"
                elif self.cash_positions[user.username] < high_margin:
                    if user.username not in self.low_margin_users:
                        self.low_margin_users[user.username] = datetime.datetime.utcnow()
                        self.email_user(user, self.cash_positions[user.username], low_margin, high_margin, severe=False)
                    result = "WARNING"
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
    if config.getboolean("administrator", "nexmo_enable"):
        nexmo = Nexmo(config.get("administrator", "nexmo_api_key"),
                    config.get("administrator", "nexmo_api_secret"),
                    config.get("exchange_info", "exchange_name"),
                    config.get("administrator", "nexmo_from_code"))
        messenger = Messenger(sendmail, nexmo)
    else:
        messenger = Messenger(sendmail)

    accountant = AccountantProxy("dealer",
                                 config.get("accountant", "riskmanager_export"),
                                 config.getint("accountant", "riskmanager_export_base_port"))

    riskmanager = RiskManager(session, messenger, safe_price_subscriber, accountant)

    reactor.run()
