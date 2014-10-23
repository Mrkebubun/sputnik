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

NAP_TIME_SECONDS = 10
jinja_env = Environment(loader=FileSystemLoader('admin_templates'))
sendmail = Sendmail(config.get("riskmanager", "from_email"))

def email_user(user, cash_position, low_margin, high_margin, severe):
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
    template_file = "margin_call.email" if severe else "low_margin.email"
    t = jinja_env.get_template(template_file)
    content = t.render(cash_position=util.quantity_fmt(BTC, cash_position),
                       low_margin=util.quantity_fmt(BTC, low_margin),
                       high_margin=util.quantity_fmt(BTC, high_margin), user=user).encode('utf-8')

    # Now send the mail
    log.msg("Sending mail: %s" % content)
    d = sendmail.send_mail(content, to_address=user.email,
                                subject="Margin Call" if severe else "Margin Warning")

    return True

if __name__ == "__main__":
    import sys
    log.startLogging(sys.stdout)

    session = database.make_session()

    safe_price_subscriber = connect_subscriber(config.get("safe_price_forwarder", "zmq_backend_address"))
    safe_price_subscriber.subscribe('')

    BTC = session.query(models.Contract).filter_by(ticker='BTC').one()


    low_margin_users = {}
    bad_margin_users = {}
    cash_positions = {}
    timestamps = {}

    def on_safe_price(*args):
        safe_prices = json.loads(args[0])

        # todo we should loop on the union of of safe price and message from the accountant asking us to take action
        for user in session.query(models.User).filter_by(active=True).filter_by(type='Liability'):
            low_margin, high_margin, cash_spent = margin.calculate_margin(user.username, session, safe_prices)
            try:
                cash_position_db = session.query(models.Position).filter_by(contract=BTC, user=user).one()
            except NoResultFound:
                cash_positions[user.username] = 0
            else:
                # Use calculated position
                if user.username in timestamps:
                    cash_positions[user.username], timestamps[user.username] = \
                        util.position_calculated(cash_position_db, session, checkpoint=cash_positions[user.username],
                                                 start=timestamps[user.username])
                else:
                    cash_positions[user.username], timestamps[user.username] = \
                        util.position_calculated(cash_position_db, session)


            if cash_positions[user.username] < low_margin:
                if user.username not in bad_margin_users:
                    bad_margin_users[user.username] = datetime.datetime.utcnow()
                    email_user(user, cash_positions[user.username], low_margin, high_margin, severe=True)
                result = "WARNING"
            elif cash_positions[user.username] < high_margin:
                if user.username not in low_margin_users:
                    low_margin_users[user.username] = datetime.datetime.utcnow()
                    email_user(user, cash_positions[user.username], low_margin, high_margin, severe=False)
                result = "CALL"
            else:
                if user.username in low_margin_users:
                    del low_margin_users[user.username] # resolved
                if user.username in bad_margin_users:
                    del bad_margin_users[user.username] # resolved
                result = "OK"

            log.msg("%s: %s / %d %d %d" % (result, user.username, low_margin, high_margin,
                                                 cash_positions[user.username]))


    safe_price_subscriber.gotMessage = on_safe_price
    reactor.run()
