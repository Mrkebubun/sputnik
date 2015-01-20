__author__ = 'sameer'
from datetime import datetime

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

def trade_history_to_ohlcv(trade_history, period="day"):
    ohlcv_history = {}
    period_map = {'minute': 60,
                  'hour': 3600,
                  'day': 3600 * 24}
    period_seconds = int(period_map[period])
    period_micros = int(period_seconds * 1e6)
    for trade in trade_history:
        contract = trade['contract']
        start_period = int(trade['timestamp'] / period_micros) * period_micros
        if start_period not in ohlcv_history:
            ohlcv_history[start_period] = {'period': period,
                                       'contract': contract,
                                       'open': trade['price'],
                                       'low': trade['price'],
                                       'high': trade['price'],
                                       'close': trade['price'],
                                       'volume': trade['quantity'],
                                       'vwap': trade['price'],
                                       'open_timestamp': start_period,
                                       'close_timestamp': start_period + period_micros - 1}
        else:
            ohlcv_history[start_period]['low'] = min(trade['price'], ohlcv_history[start_period]['low'])
            ohlcv_history[start_period]['high'] = max(trade['price'], ohlcv_history[start_period]['high'])
            ohlcv_history[start_period]['close'] = trade['price']
            ohlcv_history[start_period]['vwap'] = ( ohlcv_history[start_period]['vwap'] * \
                                            ohlcv_history[start_period]['volume'] + trade['quantity'] * trade['price'] ) / \
                                          ( ohlcv_history[start_period]['volume'] + trade['quantity'] )
            ohlcv_history[start_period]['volume'] += trade['quantity']
    return ohlcv_history

