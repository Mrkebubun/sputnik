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
import collections
from psycopg2 import OperationalError
from twisted.internet.defer import inlineCallbacks, returnValue

class PostgresException(util.SputnikException):
    pass

class MyConnectionPool():
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.pool = adbapi.ConnectionPool(*args, **kwargs)

    @inlineCallbacks
    def runQuery(self, *args, **kwargs):
        count = 0
        while count < 10:
            try:
                result = yield self.pool.runQuery(*args, **kwargs)
                returnValue(result)
            except OperationalError as e:
                log.err("Operational Error! Trying again - %s" % str(e))
                self.pool = adbapi.ConnectionPool(*self.args, **self.kwargs)
                count += 1
            except Exception as e:
                raise e

        log.err("Tried to reconnect 10 times, no joy")
        raise PostgresException("exceptions/webserver/database-error")

class PostgresDatabase(DatabasePlugin):
    def __init__(self):
        DatabasePlugin.__init__(self)

        # noinspection PyUnresolvedReferences
        dbpassword = config.get("database", "password")
        if dbpassword:
            dbpool = MyConnectionPool(config.get("database", "adapter"),
                                       user=config.get("database", "username"),
                                       password=dbpassword,
                                       host=config.get("database", "host"),
                                       port=config.get("database", "port"),
                                       database=config.get("database", "dbname"))
        else:
            dbpool = MyConnectionPool(config.get("database", "adapter"),
                                       user=config.get("database", "username"),
                                       database=config.get("database", "dbname"))
        self.dbpool = dbpool

    @inlineCallbacks
    def lookup(self, username):
        query = "SELECT password, totp FROM users WHERE username=%s LIMIT 1"
        try:
            debug("Looking up username %s..." % username)

            # A hit and a miss both take approximately the same amount of time.
            # We can probably not worry about timing attacks here.
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
                                             "denominated_contract_ticker, payout_contract_ticker, expiration FROM contracts")
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

    @inlineCallbacks
    def get_permissions(self, username):
        result = yield self.dbpool.runQuery(
            "SELECT permission_groups.name, permission_groups.login, permission_groups.deposit, permission_groups.withdraw, "
            "permission_groups.trade, permission_groups.full_ui "
            "FROM permission_groups, users WHERE "
            "users.permission_group_id=permission_groups.id AND users.username=%s",
            (username,))

        permissions = {'name': result[0][0],
                       'login': result[0][1],
                       'deposit': result[0][2],
                       'withdraw': result[0][3],
                       'trade': result[0][4],
                       'full_ui': result[0][5]}
        returnValue(permissions)

    @inlineCallbacks
    def get_transaction_history(self, from_timestamp, to_timestamp, username):
        result = yield self.dbpool.runQuery(
            "SELECT contracts.ticker, SUM(posting.quantity) FROM posting, journal, contracts "
            "WHERE posting.journal_id=journal.id AND posting.username=%s AND journal.timestamp<%s "
            "AND posting.contract_id=contracts.id GROUP BY contracts.ticker",
            (username, util.timestamp_to_dt(from_timestamp)))

        balances = collections.defaultdict(int)
        for row in result:
            balances[row[0]] = int(row[1])

        result = yield self.dbpool.runQuery(
            "SELECT contracts.ticker, journal.timestamp, posting.quantity, journal.type, posting.note "
            "FROM posting, journal, contracts WHERE posting.journal_id=journal.id AND "
            "posting.username=%s AND journal.timestamp>=%s AND journal.timestamp<=%s "
            "AND posting.contract_id=contracts.id ORDER BY journal.timestamp",
            (username, util.timestamp_to_dt(from_timestamp), util.timestamp_to_dt(to_timestamp)))

        transactions = []
        for row in result:
            balances[row[0]] += row[2]
            quantity = abs(row[2])

            # Here we assume that the user is a Liability user
            if row[2] < 0:
                direction = 'debit'
            else:
                direction = 'credit'

            transactions.append({'contract': row[0],
                                 'timestamp': util.dt_to_timestamp(row[1]),
                                 'quantity': quantity,
                                 'type': row[3],
                                 'direction': direction,
                                 'balance': balances[row[0]],
                                 'note': row[4]})

        returnValue(transactions)

    @inlineCallbacks
    def get_positions(self, username):

        result = yield self.dbpool.runQuery(
            "SELECT contracts.id, contracts.ticker, positions.position, positions.reference_price "
            "FROM positions, contracts WHERE positions.contract_id = contracts.id AND positions.username=%s",
            (username,))

        returnValue({x[1]: {"contract": x[1],
                            "position": x[2],
                            "reference_price": x[3]
                            }
                            for x in result})

    @inlineCallbacks
    def get_open_orders(self, username):
        def _cb(result):
            """

            :param result:
            :returns: list - [True, dict of orders, indexed by id]
            """


        results = yield self.dbpool.runQuery('SELECT contracts.ticker, orders.price, orders.quantity, orders.quantity_left, '
                               'orders.timestamp, orders.side, orders.id FROM orders, contracts '
                               'WHERE orders.contract_id=contracts.id AND orders.username=%s '
                               'AND orders.quantity_left > 0 '
                               'AND orders.accepted=TRUE AND orders.is_cancelled=FALSE', (username,))
        returnValue({r[6]: {'contract': r[0], 'price': r[1], 'quantity': r[2], 'quantity_left': r[3],
                       'timestamp': util.dt_to_timestamp(r[4]), 'side': r[5], 'id': r[6], 'is_cancelled': False} for r in results})