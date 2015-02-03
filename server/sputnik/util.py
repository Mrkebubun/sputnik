__author__ = 'sameer'

from datetime import datetime
from twisted.internet import ssl
from OpenSSL import SSL
import models
import sys
import math
import time
import uuid
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import func
from twisted.python import log
from zmq_util import ComponentExport
from sqlalchemy.orm.session import Session
import hashlib

#
# This doesn't work properly
#
def except_trace_alert(func):
    def wrapped(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            log.err("Unhandled exception in %s" % func.__name__)
            log.err(e)
            if hasattr(self, 'alerts_proxy') and self.alerts_proxy is not None:
                self.alerts_proxy.send_alert(str(e), "Unhandled exception in %s" % func.__name__)
            raise e

    return wrapped

def session_aware(func):
    def wrapped(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        finally:
            if isinstance(self, ComponentExport):
                session = self.component.session
            else:
                session = self.session

            if isinstance(session, Session):
                session.rollback()
    return wrapped

def get_locale_template(locale, jinja_env, template):
    locales = [locale, "root"]
    templates = [template.format(locale=locale) for locale in locales]
    t = jinja_env.select_template(templates)
    return t

def timed(f):
    def wrapped(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        stop = time.time()
        log.msg("%s completed in %dms." % (f.__name__, (stop - start) * 1000))
        return result
    return wrapped

def get_uid():
    return uuid.uuid4().get_hex()

def malicious_looking(w):
    """

    :param w:
    :returns: bool
    """
    return any(x in w for x in '<>&')

def encode_username(username):
    return hashlib.sha256(username).hexdigest()

def price_to_wire(contract, price):
    if contract.contract_type == "prediction":
        price = price * contract.denominator
    else:
        price = price * contract.denominated_contract.denominator * contract.denominator

    p = price - price % contract.tick_size
    return int(p)

def price_from_wire(contract, price):
    if contract.contract_type == "prediction":
        return float(price) / contract.denominator
    else:
        return float(price) / (contract.denominated_contract.denominator * contract.denominator)

def quantity_from_wire(contract, quantity):
    if contract.contract_type == "prediction":
        return quantity
    elif contract.contract_type == "cash":
        return float(quantity) / contract.denominator
    else:
        return float(quantity) / contract.payout_contract.denominator

def quantity_to_wire(contract, quantity):
    if contract.contract_type == "prediction":
        q = quantity
    elif contract.contract_type == "cash":
        q = quantity * contract.denominator
    else:
        quantity = quantity * contract.payout_contract.denominator
        q = quantity - quantity % contract.lot_size
    return int(q)

def get_precision(numerator, denominator):
    if numerator <= denominator:
        return 0
    else:
        return math.log10(numerator / denominator)

def get_price_precision(contract):
    if contract.contract_type == "prediction":
        return get_precision(contract.denominator, contract.tick_size)
    else:
        return get_precision(contract.denominated_contract.denominator * contract.denominator, contract.tick_size)

def get_quantity_precision(contract):
    if contract.contract_type == "prediction":
        return 0
    elif contract.contract_type == "cash":
        return get_precision(contract.denominator, contract.lot_size)
    else:
        return get_precision(contract.payout_contract.denominator, contract.lot_size)

def price_fmt(contract, price):
        return ("{price:.%df}" % get_price_precision(contract)).format(price=price_from_wire(contract, price))

def quantity_fmt(contract, quantity):
        return ("{quantity:.%df}" % get_quantity_precision(contract)).format(quantity=quantity_from_wire(contract,
                                                                                                         quantity))

def dt_to_timestamp(dt):
    """Turns a datetime into a Sputnik timestamp (microseconds since epoch)

    :param dt:
    :type dt: datetime.datetime
    :returns: int
    """
    epoch = datetime.utcfromtimestamp(0)
    delta = dt - epoch
    timestamp = int(delta.total_seconds() * 1e6)
    return timestamp

def timestamp_to_dt(timestamp):
    """Turns a sputnik timestamp into a python datetime

    :param timestamp:
    :type timestamp: int
    :returns: datetime.datetime
    """
    return datetime.utcfromtimestamp(timestamp/1e6)


def get_fees(user, contract, transaction_size, trial_period=False, ap=None):
    """
    Given a transaction, figure out how much fees need to be paid in what currencies
    :param username:
    :type username: str
    :param contract:
    :type contract: Contract
    :param transaction_size:
    :type transaction_size: int
    :returns: dict
    """

    # No fees during trial period
    if trial_period:
        return {}

    # Right now fees are very simple, just 40bps of the total from_currency amount
    # but only charged to the liquidity taker
    # TODO: Make fees based on transaction size

    base_fee = transaction_size * contract.fees
    # If we don't know the aggressive/passive -- probably because we're
    # checking what the fees might be before placing an order
    # so we assume the fees are the max possible
    if ap is None:
        user_factor = max(user.fees.aggressive_factor, user.fees.passive_factor)
    elif ap == "aggressive":
        user_factor = user.fees.aggressive_factor
    else:
        user_factor = user.fees.passive_factor

    # 100 because factors are in % and 10000 because fees are in bps
    final_fee = int(round(base_fee * user_factor / 100 / 10000))
    return {contract.denominated_contract.ticker: final_fee}

def get_deposit_fees(user, contract, deposit_amount, trial_period=False):
    if trial_period:
        return {}

    base_fee = contract.deposit_base_fee + float(deposit_amount * contract.deposit_bps_fee) / 10000
    user_factor = float(user.fees.deposit_factor) / 100
    final_fee = int(round(base_fee * user_factor))

    return {contract.ticker: final_fee}

def get_withdraw_fees(user, contract, withdraw_amount, trial_period=False):
    if trial_period:
        return {}

    base_fee = contract.withdraw_base_fee + float(withdraw_amount * contract.withdraw_bps_fee) / 10000
    user_factor = float(user.fees.withdraw_factor) / 100
    final_fee = int(round(base_fee * user_factor))

    return {contract.ticker: final_fee}


def get_contract(session, ticker):
    """
    Return the Contract object corresponding to the ticker.
    :param session: the sqlalchemy session to use
    :param ticker: the ticker to look up or a Contract id
    :type ticker: str, models.Contract
    :returns: models.Contract -- the Contract object matching the ticker
    :raises: AccountantException
    """

    # TODO: memoize this!

    if isinstance(ticker, models.Contract):
        return ticker

    try:
        ticker = int(ticker)
        return session.query(models.Contract).filter_by(
            id=ticker).one()
    except NoResultFound:
        raise Exception("Could not resolve contract '%s'." % ticker)
    except ValueError:
        # drop through
        pass

    try:
        return session.query(models.Contract).filter_by(
            ticker=ticker).order_by(models.Contract.id.desc()).first()
    except NoResultFound:
        raise Exception("Could not resolve contract '%s'." % ticker)

def position_calculated(position, session, checkpoint=None, start=None, end=None):
    if start is None:
        start = position.position_cp_timestamp or timestamp_to_dt(0)
    if checkpoint is None:
        checkpoint = position.position_checkpoint or 0

    rows = session.query(func.sum(models.Posting.quantity).label('quantity_sum'),
                         func.max(models.Journal.timestamp).label('last_timestamp')).filter_by(
        username=position.username).filter_by(
        contract_id=position.contract_id).filter(
        models.Journal.id==models.Posting.journal_id).filter(
        models.Journal.timestamp > start)
    if end is not None:
        rows = rows.filter(models.Journal.timestamp <= end)

    try:
        grouped = rows.group_by(models.Posting.username).one()
        calculated = grouped.quantity_sum
        last_posting_timestamp = grouped.last_timestamp
    except NoResultFound:
        calculated = 0
        last_posting_timestamp = None


    return checkpoint + calculated, last_posting_timestamp

class ChainedOpenSSLContextFactory(ssl.DefaultOpenSSLContextFactory):
    def __init__(self, privateKeyFileName, certificateChainFileName,
                 sslmethod=SSL.SSLv23_METHOD):
        """

        :param privateKeyFileName:
        :param certificateChainFileName:
        :param sslmethod:
        """
        self.privateKeyFileName = privateKeyFileName
        self.certificateChainFileName = certificateChainFileName
        self.sslmethod = sslmethod
        self.cacheContext()

    def cacheContext(self):
        """


        """
        ctx = SSL.Context(self.sslmethod)
        ctx.use_certificate_chain_file(self.certificateChainFileName)
        ctx.use_privatekey_file(self.privateKeyFileName)
        self._context = ctx

class SputnikObserver(log.FileLogObserver):
    levels = {10: "DEBUG", 20:"INFO", 30:"WARN", 40:"ERROR", 50:"CRITICAL"}

    def __init__(self, level=20):
        self.level = level
        log.FileLogObserver.__init__(self, sys.stdout)

    def emit(self, eventDict):
        text = log.textFromEventDict(eventDict)
        if text is None:
            return
        
        level = eventDict.get("level", 20)
        if level < self.level:
            return

        timeStr = self.formatTime(eventDict['time'])
        fmtDict = {'system': eventDict['system'],
                   'text': text.replace("\n", "\n\t"),
                   'level': self.levels[level]}
        msgStr = log._safeFormat("%(level)s [%(system)s] %(text)s\n", fmtDict)

        twisted.python.util.untilConcludes(self.write, timeStr + " " + msgStr)
        twisted.python.util.untilConcludes(self.flush)

class Logger:
    def __init__(self, prefix):
        self.prefix = prefix

    def debug(self, message=None):
        log.msg(message, system=self.prefix, level=10)

    def info(self, message=None):
        log.msg(message, system=self.prefix, level=20)

    def warn(self, message=None):
        log.msg(message, system=self.prefix, level=30)

    def error(self, message=None):
        log.err(message, system=self.prefix, level=40)

    def critical(self, message=None):
        log.err(message, system=self.prefix, level=50)

