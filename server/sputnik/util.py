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
