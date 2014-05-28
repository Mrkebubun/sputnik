__author__ = 'arthurb'

import models
import logging
import util
import collections

def calculate_margin(username, session, safe_prices={}, order_id=None, withdrawal=None, trial_period=False):
    """
    calculates the low and high margin for a given user
    :param order_id: order we're considering throwing in
    :type order_id: int
    :param username: the username
    :type username: str
    :returns: tuple - low and high margin
    """

    low_margin = high_margin = 0

    cash_position = {}

    # let's start with positions
    positions = {position.contract_id: position for position in
                 session.query(models.Position).filter_by(username=username)}

    open_orders = session.query(models.Order).filter_by(username=username).filter(
        models.Order.quantity_left > 0).filter_by(is_cancelled=False, accepted=True).all()

    if order_id:
        open_orders += session.query(models.Order).filter_by(id=order_id).all()

    for position in positions.values():

        max_position = position.position + sum(
            order.quantity_left for order in open_orders if
            order.contract == position.contract and order.side == 'BUY')
        min_position = position.position - sum(
            order.quantity_left for order in open_orders if
            order.contract == position.contract and order.side == 'SELL')

        contract = position.contract

        if contract.contract_type == 'futures':
            SAFE_PRICE = safe_prices[position.contract.ticker]

            logging.info(low_margin)
            print 'max position:', max_position
            print 'contract.margin_low :', contract.margin_low
            print 'SAFE_PRICE :', SAFE_PRICE
            print 'position.reference_price :', position.reference_price
            print position
            low_max = abs(max_position) * contract.margin_low * SAFE_PRICE / 100 + max_position * (
                position.reference_price - SAFE_PRICE)
            low_min = abs(min_position) * contract.margin_low * SAFE_PRICE / 100 + min_position * (
                position.reference_price - SAFE_PRICE)
            high_max = abs(max_position) * contract.margin_high * SAFE_PRICE / 100 + max_position * (
                position.reference_price - SAFE_PRICE)
            high_min = abs(min_position) * contract.margin_high * SAFE_PRICE / 100 + min_position * (
                position.reference_price - SAFE_PRICE)
            logging.info(low_max)
            logging.info(low_min)

            high_margin += max(high_max, high_min)
            low_margin += max(low_max, low_min)

        if contract.contract_type == 'prediction':
            payoff = contract.lot_size

            # case where all our buy orders are hit
            max_spent = sum(order.quantity_left * order.price * order.contract.lot_size / order.contract.denominator
                            for order in open_orders if
                            order.contract == contract and order.side == 'BUY')

            # case where all our sell orders are hit
            max_received = sum(order.quantity_left * order.price * order.contract.lot_size / order.contract.denominator
                               for order in open_orders if
                               order.contract == contract and order.side == 'SELL')

            worst_short_cover = -min_position * payoff if min_position < 0 else 0
            best_short_cover = -max_position * payoff if max_position < 0 else 0

            additional_margin = max(max_spent + best_short_cover, -max_received + worst_short_cover)
            low_margin += additional_margin
            high_margin += additional_margin

        if contract.contract_type == 'cash':
            cash_position[contract.ticker] = position.position

    max_cash_spent = collections.defaultdict(int)

    # Deal with cash_pair orders separately because there are no cash_pair positions
    for order in open_orders:
        if order.contract.contract_type == 'cash_pair':
            denominated_contract = order.contract.denominated_contract
            payout_contract = order.contract.payout_contract

            transaction_size_float = order.quantity_left * order.price / (order.contract.denominator *
                                                                          payout_contract.denominator)
            transaction_size_int = int(transaction_size_float)
            if transaction_size_float != transaction_size_int:
                logging.error("Position change is not an integer.")

            if order.side == 'BUY':
                max_cash_spent[denominated_contract.ticker] += transaction_size_int
            if order.side == 'SELL':
                max_cash_spent[payout_contract.ticker] += order.quantity_left

            fees = util.get_fees(username, order.contract, transaction_size_int, trial_period=trial_period)
            for ticker, fee in fees.iteritems():
                max_cash_spent[ticker] += fee

    # Make sure max_cash_spent has something in it for every cash contract
    for ticker in cash_position.iterkeys():
        if ticker not in max_cash_spent:
            max_cash_spent[ticker] = 0

    for cash_ticker, max_spent in max_cash_spent.iteritems():
        if cash_ticker == 'BTC':
            additional_margin = max_spent
        else:
            if cash_ticker in cash_position and max_spent <= cash_position[cash_ticker]:
                additional_margin = 0
            else:
                additional_margin = 2**48

        low_margin += additional_margin
        high_margin += additional_margin

    return low_margin, high_margin


