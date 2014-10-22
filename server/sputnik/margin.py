__author__ = 'arthurb'

import collections

from twisted.python import log

import models
import util

class MarginException(Exception):
    pass


def calculate_margin(username, session, safe_prices={}, order_id=None, withdrawals=None, trial_period=False):
    """
    calculates the low and high margin for a given user
    :param order_id: order we're considering throwing in
    :type order_id: int
    :param username: the username
    :type username: str
    :returns: tuple - low and high margin
    """

    low_margin = high_margin = 0

    cash_position = collections.defaultdict(int)

    # let's start with positions
    positions = {position.contract_id: position.dict for position in
                 session.query(models.Position).filter_by(username=username)}

    open_orders = session.query(models.Order).filter_by(username=username).filter(
        models.Order.quantity_left > 0).filter_by(is_cancelled=False, accepted=True).all()

    if order_id:
        open_orders += session.query(models.Order).filter_by(id=order_id).all()

    # Make a blank position for all contracts which have an open order but no position
    for order in open_orders:
        if order.contract.id not in positions:
            positions[order.contract.id] = {
                'position': 0,
                'reference_price': None,
                'contract': order.contract
            }

    for position in positions.values():

        max_position = position['position'] + sum(
            order.quantity_left for order in open_orders if
            order.contract == position['contract'] and order.side == 'BUY')
        min_position = position['position'] - sum(
            order.quantity_left for order in open_orders if
            order.contract == position['contract'] and order.side == 'SELL')

        contract = position['contract']

        if contract.contract_type == 'futures':
            SAFE_PRICE = safe_prices[position['contract'].ticker]

            log.msg(low_margin)
            print 'max position:', max_position
            print 'contract.margin_low :', contract.margin_low
            print 'SAFE_PRICE :', SAFE_PRICE
            print 'position.reference_price :', position['reference_price']
            print position
            if position['reference_price'] is None:
                if position['position'] != 0:
                    raise MarginException("No reference price with non-zero position")

                reference_price = SAFE_PRICE
            else:
                reference_price = position['reference_price']

            # We divide by 100 because contract.margin_low and contract.margin_high are percentages from 0-100
            low_max = abs(max_position) * contract.margin_low * SAFE_PRICE * contract.lot_size / contract.denominator / 100 + max_position * (
                reference_price - SAFE_PRICE) * contract.lot_size / contract.denominator
            low_min = abs(min_position) * contract.margin_low * SAFE_PRICE * contract.lot_size / contract.denominator / 100 + min_position * (
                reference_price - SAFE_PRICE) * contract.lot_size / contract.denominator
            high_max = abs(max_position) * contract.margin_high * SAFE_PRICE * contract.lot_size / contract.denominator / 100 + max_position * (
                reference_price - SAFE_PRICE) * contract.lot_size / contract.denominator
            high_min = abs(min_position) * contract.margin_high * SAFE_PRICE * contract.lot_size / contract.denominator / 100 + min_position * (
                reference_price - SAFE_PRICE) * contract.lot_size / contract.denominator
            log.msg(low_max)
            log.msg(low_min)

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
            cash_position[contract.ticker] = position['position']

    max_cash_spent = collections.defaultdict(int)

    # Deal with cash_pair orders separately because there are no cash_pair positions
    for order in open_orders:
        fees = util.get_fees(username, order.contract, order.price, order.quantity, trial_period=trial_period)
        
        if order.contract.contract_type == 'cash_pair':
            transaction_size = util.get_cash_spent(order.contract, order.price, order.quantity)
            if order.side == 'BUY':
                max_cash_spent[order.contract.denominated_contract.ticker] += transaction_size
                if order.contract.payout_contract.ticker in fees:
                    fees[order.contract.payout_contract.ticker] = max(0, fees[order.contract.payout_contract.ticker] - order.quantity_left)
            if order.side == 'SELL':
                max_cash_spent[order.contract.payout_contract.ticker] += order.quantity_left
                if order.contract.denominated_contract.ticker in fees:
                    fees[order.contract.denominated_contract.ticker] = max(0, fees[order.contract.denominated_contract.ticker] - transaction_size)

        for ticker, fee in fees.iteritems():
            max_cash_spent[ticker] += fee



    # Make sure max_cash_spent has something in it for every cash contract
    for ticker in cash_position.iterkeys():
        if ticker not in max_cash_spent:
            max_cash_spent[ticker] = 0

    # Deal with withdrawals
    if withdrawals:
        for ticker, amount in withdrawals.iteritems():
            max_cash_spent[ticker] += amount

    for cash_ticker, max_spent in max_cash_spent.iteritems():
        if cash_ticker == 'BTC':
            additional_margin = max_spent
        else:
            if max_spent <= cash_position[cash_ticker]:
                additional_margin = 0
            else:
                # TODO: We should fix this hack and just check max_cash_spent in check_margin
                log.msg("max_spent (%d) > cash_position[%s] (%d)" % (max_spent, cash_ticker, cash_position[cash_ticker]))
                additional_margin = 2**48

        low_margin += additional_margin
        high_margin += additional_margin

    return low_margin, high_margin, max_cash_spent


