__author__ = 'sameer'

from datetime import datetime
from twisted.internet import ssl
from OpenSSL import SSL
import models

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

def split_pair(pair):
    """
    Return the underlying pair of contracts in a cash_pair contract.
    :param pair: the ticker name of the pair to split
    :type pair: str
    :returns: tuple - a pair of Contract tickers
    """

    if isinstance(pair, models.Contract):
        return split_pair(pair.ticker)

    tokens = pair.split("/", 1)
    if len(tokens) == 1:
        raise Exception("'%s' is not a currency pair." % pair)
    try:
        target = tokens[0]
        source = tokens[1]
    except Exception as e:
        raise Exception("'%s' is not a currency pair: %s" % (pair, e.message))
    return source, target


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
    # Not implemented for anything but cash_pair
    # TODO: Make fees based on transaction size
    # TODO: Give some users different fee schedules
    # TODO: Give some contracts different fee schedules
    # TODO: make the fee user accounts configurable in config file
    # TODO: Put fee schedule and user levels into DB
    # TODO: Create fees for futures and predictions
    if contract.contract_type == "cash_pair":
        from_currency_ticker, to_currency_ticker = split_pair(contract.ticker)
        fees = round(transaction_size * 0.002)
        return { from_currency_ticker: fees,
                 to_currency_ticker: 0
        }
    else:
        # Only cash_pair is implemented for now
        raise NotImplementedError


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

