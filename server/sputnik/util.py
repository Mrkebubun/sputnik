__author__ = 'sameer'

from datetime import datetime
from twisted.internet import ssl
from OpenSSL import SSL
import models
import math
from sqlalchemy.orm.exc import NoResultFound
import logging

def price_to_wire(contract, price):
    if contract.contract_type == "prediction":
        price = price * contract.denominator
    else:
        price = price * contract.denominated_contract.denominator * contract.denominator

    return price - price % contract.tick_size

def price_from_wire(contract, price):
    if contract.contract_type == "prediction":
        return price / contract.denominator
    else:
        return price / (contract.denominated_contract.denominator * contract.denominator)

def quantity_from_wire(contract, quantity):
    if contract.contract_type == "prediction":
        return quantity
    elif contract.contract_type == "cash":
        return quantity / contract.denominator
    else:
        return quantity / contract.payout_contract.denominator

def quantity_to_wire(contract, quantity):
    if contract.contract_type == "prediction":
        return quantity
    elif contract.contract_type == "cash":
        return quantity * contract.denominator
    else:
        quantity = quantity * contract.payout_contract.denominator
        return quantity - quantity % contract.lot_size

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
    # Special case BTC
    if contract.ticker == "BTC":
        return 2

    if contract.contract_type == "prediction":
        return 0
    elif contract.contract_type == "cash":
        return get_precision(contract.denominator, 1)
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
    return datetime.fromtimestamp(timestamp/1e6)


def get_fees(username, contract, transaction_size):
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

    # Right now fees are very simple, just 20bps of the total from_currency amount
    # user account.
    # TODO: Make fees based on transaction size
    # TODO: Give some users different fee schedules
    # TODO: Give some contracts different fee schedules
    # TODO: make the fee user accounts configurable in config file
    # TODO: Put fee schedule and user levels into DB
    # TODO: Create fees for futures and predictions
    if contract.contract_type == "cash_pair":
        denominated_contract = contract.denominated_contract
        payout_contract = contract.payout_contract
        fees = int(round(transaction_size * 0.002))
        return { denominated_contract.ticker: fees,
                 payout_contract.ticker: 0
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
    logging.debug("Looking up contract %s." % ticker)


    if isinstance(ticker, models.Contract):
        return ticker

    try:
        ticker = int(ticker)
        return session.query(models.Contract).filter_by(
            contract_id=ticker).one()
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

