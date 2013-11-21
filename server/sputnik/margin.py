__author__ = 'arthurb'

import models
import logging

logging.basicConfig(level=logging.DEBUG)

def calculate_margin(username, session, safe_prices, order_id=None):
    """
    calculates the low and high margin for a given user
    :param order_id: order we're considering throwing in
    :param username: the username
    :return: low and high margin
    """
    low_margin = high_margin = 0

    # let's start with positions
    positions = {position.contract_id: position for position in
                 session.query(models.Position).filter_by(username=username)}

    open_orders = session.query(models.Order).filter_by(username=username).filter(
        models.Order.quantity_left > 0).filter_by(is_cancelled=False, accepted=True).all()

    if order_id:
        open_orders += session.query(models.Order).filter_by(id=order_id).all()

    for position in positions.values():

        max_position = position.position + sum(
            order.quantity_left for order in open_orders if order.contract == position.contract and order.side == 'BUY')
        min_position = position.position - sum(
            order.quantity_left for order in open_orders if order.contract == position.contract and order.side == 'SELL')

        # if potential_order and position.contract_id == potential_order['contract_id']:
        #     if potential_order['side'] == 0:
        #         max_position += potential_order['quantity']
        #     if potential_order['side'] == 1:
        #         min_position -= potential_order['quantity']

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
            logging.info( low_max)
            logging.info( low_min)

            high_margin += max(high_max, high_min)
            low_margin += max(low_max, low_min)

        if contract.contract_type == 'prediction':
            payoff = contract.denominator

            # case where all our buy orders are hit
            max_spent = sum(order.quantity_left * order.price for order in open_orders if
                            order.contract == contract and order.side == 'BUY')

            # case where all out sell orders are hit
            max_received = sum(order.quantity_left * order.price for order in open_orders if
                               order.contract == contract and order.side == 'SELL')

            # if potential_order and position.contract_id == potential_order['contract_id']:
            #     if potential_order['side'] == 0:
            #         max_spent += potential_order['quantity'] * potential_order['price']
            #     if potential_order['side'] == 1:
            #         max_received += potential_order['quantity'] * potential_order['price']

            worst_short_cover = -min_position * payoff if min_position < 0 else 0
            best_short_cover = -max_position * payoff if max_position < 0 else 0

            additional_margin = max(max_spent + best_short_cover, -max_received + worst_short_cover)
            low_margin += additional_margin
            high_margin += additional_margin

    return low_margin, high_margin