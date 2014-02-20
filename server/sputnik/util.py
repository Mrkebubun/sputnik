__author__ = 'sameer'

from datetime import datetime

def dt_to_timestamp(dt):
    epoch = datetime.utcfromtimestamp(0)
    delta = dt - epoch
    timestamp = int(delta.total_seconds() * 1e6)
    return timestamp
