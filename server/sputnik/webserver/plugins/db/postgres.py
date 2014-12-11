from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("db_postgres")

from sputnik.webserver.plugin import DatabasePlugin
from autobahn.wamp import types
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.enterprise import adbapi
from sputnik import util
import markdown
import datetime

class PostgresDatabase(DatabasePlugin):
    def __init__(self):
        DatabasePlugin.__init__(self)
        dbpassword = config.get("database", "password")
        if dbpassword:
            dbpool = adbapi.ConnectionPool(config.get("database", "adapter"),
                    user=config.get("database", "username"),
                    password=dbpassword,
                    host=config.get("database", "host"),
                    port=config.get("database", "port"),
                    database=config.get("database", "dbname"))
        else:
            dbpool = adbapi.ConnectionPool(config.get("database", "adapter"),
                    user=config.get("database", "username"),
                    database=config.get("database", "dbname"))
        self.dbpool = dbpool

    @inlineCallbacks
    def lookup(self, username):
        query = "SELECT password, totp FROM users WHERE username=%s LIMIT 1"
        try:
            debug("Looking up username %s..." % username)

            # A hit and a miss both take approximately the same amount of time.
            #   We can probably not worry about timing attacks here.
            result = yield self.dbpool.runQuery(query, (username,))
            if result:
                debug("User %s found." % username)
                returnValue(result[0])

            debug("User %s not found." % username)
        except Exception, e:
            error("Exception caught looking up user %s." % username)
            error()

    @inlineCallbacks
    def get_markets(self):
        results = yield self.dbpool.runQuery("SELECT ticker, description, denominator, contract_type, full_description,"
                               "tick_size, lot_size, margin_high, margin_low,"
                               "denominated_contract_ticker, payout_contract_ticker, expiration FROM contracts").addCallback(_cb)
        markets = {}
        for r in results:
            markets[r[0]] = {"ticker": r[0],
                            "description": r[1],
                            "denominator": r[2],
                            "contract_type": r[3],
                            "full_description": markdown.markdown(r[4], extensions=["markdown.extensions.extra",
                                                                                    "markdown.extensions.sane_lists",
                                                                                    "markdown.extensions.nl2br"
                            ]),
                            "tick_size": r[5],
                            "lot_size": r[6],
                            "denominated_contract_ticker": r[9],
                            "payout_contract_ticker": r[10]}

            if markets[r[0]]['contract_type'] == 'futures':
                markets[r[0]]['margin_high'] = r[7]
                markets[r[0]]['margin_low'] = r[8]

            if markets[r[0]]['contract_type'] in ['futures', 'prediction']:
                markets[r[0]]['expiration'] = util.dt_to_timestamp(r[11])

        returnValue(markets)

    @inlineCallbacks
    def get_trade_history(self, ticker):
        to_dt = datetime.datetime.utcnow()
        from_dt = to_dt - datetime.timedelta(days=60)
        start_dt_for_period = {
            'minute': to_dt - datetime.timedelta(minutes=60),
            'hour': to_dt - datetime.timedelta(hours=60),
            'day': to_dt - datetime.timedelta(days=60)
        }
        results = yield self.dbpool.runQuery(
                "SELECT contracts.ticker, trades.timestamp, trades.price, trades.quantity FROM trades, contracts WHERE "
                "trades.contract_id=contracts.id AND contracts.ticker=%s AND trades.timestamp >= %s AND trades.posted IS TRUE",
                (ticker, from_dt))


        trades = [{'contract': r[0], 'price': r[2], 'quantity': r[3],
                                               'timestamp': util.dt_to_timestamp(r[1])} for r in results]
        returnValue(trades)



