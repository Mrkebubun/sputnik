__author__ = 'sameer'

from datetime import datetime
from twisted.internet import ssl
from OpenSSL import SSL
import models
import math
import time
import uuid
from sqlalchemy.orm.exc import NoResultFound
from twisted.python import log

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

def price_to_wire(contract, price):
    if contract.contract_type == "prediction":
        price = price * contract.denominator
    else:
        price = price * contract.denominated_contract.denominator * contract.denominator

    p = price - price % contract.tick_size
    if p != int(p):
        raise Exception("price_to_wire returns non-integer value")
    else:
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

    if q != int(q):
        raise Exception("quantity_to_wire returns non-integer value")
    else:
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


def get_fees(username, contract, transaction_size, trial_period=False):
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
    # TODO: Give some users different fee schedules
    # TODO: Give some contracts different fee schedules
    # TODO: make the fee user accounts configurable in config file
    # TODO: Put fee schedule and user levels into DB
    # TODO: Create fees for futures and predictions
    if contract.contract_type == "cash_pair":
        denominated_contract = contract.denominated_contract
        fees = int(round(transaction_size * 0.004))
        return { denominated_contract.ticker: fees
            }
    elif contract.contract_type == "prediction":
        # Predictions charge fees on settlement, not trading
        return {}
    else:
        # Only cash_pair & prediction is implemented now
        raise NotImplementedError

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

def position_calculated(position, session):
    start = position.position_cp_timestamp or 0
    checkpoint = position.position_checkpoint or 0
    postings = session.query(models.Posting).filter_by(username=position.username).filter_by(contract_id=position.contract_id).filter_by(timestamp>start)
    # TODO: we can actually sum this in SQL itself
    calculated = sum([posting.quantity for posting in postings])
    return checkpoint + calculated

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

