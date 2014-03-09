__author__ = 'sameer'

from datetime import datetime
import models

def dt_to_timestamp(dt):
    epoch = datetime.utcfromtimestamp(0)
    delta = dt - epoch
    timestamp = int(delta.total_seconds() * 1e6)
    return timestamp

def timestamp_to_dt(timestamp):
    return datetime.fromtimestamp(timestamp/1e6)

def split_pair(pair):
    """
    Return the underlying pair of contracts in a cash_pair contract.
    :param pair: the ticker name of the pair to split
    :return: a tuple of Contract objects
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
    :param transaction: the transaction object
    :return: dict
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