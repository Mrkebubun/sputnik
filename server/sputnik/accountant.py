#!/usr/bin/env python
import collections

import json
import re

__author__ = 'satosushi'

from sqlalchemy.orm.exc import NoResultFound
import zmq
import models
import database
import logging

from optparse import OptionParser
parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
        help="config file", default="../config/sputnik.ini")
(options, args) = parser.parse_args()

from ConfigParser import SafeConfigParser
config = SafeConfigParser()
config.read(options.filename)

context = zmq.Context()
connector = context.socket(zmq.constants.PULL)
connector.bind(config.get("accountant", "zmq_address"))

session = database.Session()

logging.basicConfig(level=logging.DEBUG)


# type of messages:

# deposit/withdraw: adds or remove coins from the account
# increase/decrease required_margin: adds or remove to the required margin


btc = session.query(models.Contract).filter_by(ticker='BTC').one()


def create_or_get_position(username, contract, ref_price):
    """
    returns the position in the database for a contract or creates it should it not exist
    :param user: the user
    :param contract: the contract
    :param ref_price: which price is the position entered at?
    :return: the position object
    """
    try:
        return session.query(models.Position).filter_by(username=username, contract_id=contract).one()
    except NoResultFound:
        user = session.query(models.User).filter_by(username=username).one()
        contract = session.query(models.Contract).filter_by(id=contract).one()
        pos = models.Position(user, contract)
        pos.reference_price = ref_price
        session.add(pos)
        return pos


def calculate_margin(username, order_id=None):
    """
    calculates the low and high margin for a given user
    :param order_id: order we're considering throwing in
    :param username: the username
    :return: low and high margin
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
            order.quantity_left for order in open_orders if order.contract == position.contract and order.side == 'BUY')
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
            payoff = contract.denominator

            # case where all our buy orders are hit
            max_spent = sum(order.quantity_left * order.price for order in open_orders if
                            order.contract == contract and order.side == 'BUY')

            # case where all out sell orders are hit
            max_received = sum(order.quantity_left * order.price for order in open_orders if
                               order.contract == contract and order.side == 'SELL')

            worst_short_cover = -min_position * payoff if min_position < 0 else 0
            best_short_cover = -max_position * payoff if max_position < 0 else 0

            additional_margin = max(max_spent + best_short_cover, -max_received + worst_short_cover)
            low_margin += additional_margin
            high_margin += additional_margin

        if contract.contract_type == 'cash':
            cash_position[contract.ticker] = position.position

    max_cash_spent = collections.defaultdict(int)

    for order in open_orders:
        if order.contract.contract_type == 'cash_pair':
            from_currency, to_currency = get_currencies_in_pair(contract.ticker)
            if order.side == 'BUY':
                max_cash_spent[from_currency.ticker] += order.quantity_left * order.price
            if order.side == 'SELL':
                max_cash_spent[to_currency.ticker] += order.quantity_left

    for cash_ticker in cash_position:
        if cash_ticker == 'BTC':
            additional_margin = max_cash_spent['BTC']
        else:
            # this is a bit hackish, I make the margin requirement REALLY big if we can't meet a cash order
            additional_margin = 0 if max_cash_spent[cash_ticker] < cash_position[cash_ticker] else 2**48

        low_margin += additional_margin
        high_margin += additional_margin

    return low_margin, high_margin


#todo replace deleting rejected orders with marking them as rejected, using an enum
def accept_order_if_possible(username, order_id):
    """
    Checks the impact of an order on margin, and if said impact is acceptable, mark the order as accepted
    otherwise delete the order
    :param username: the username
    :param order_id: order we're considering accepting
    :return:
    """
    low_margin, high_margin = calculate_margin(username, order_id)
    cash_position = session.query(models.Position).filter_by(username=username, contract=btc).one()

    order = session.query(models.Order).get(order_id)
    logging.info(
        "high_margin = %d, low_margin = %d, cash_position = %d" % (high_margin, low_margin, cash_position.position))

    if high_margin > cash_position.position:
        session.delete(order)
        session.commit()
        return False
    else:
        order.accepted = True
        session.merge(order)
        session.commit()
        return True

        #todo: make actual margin calls here


def get_currencies_in_pair(ticker):


        """
            (}
           /Y\`;,
           /^\  ;:,
         """
        m = re.match(r'([a-z]+)/([a-z]+)', ticker, re.IGNORECASE)
        from_currency = session.query(models.Contract).filter_by(ticker=m.groups()[0])
        to_currency = session.query(models.Contract).filter_by(ticker=m.groups()[1])
        return from_currency, to_currency



def process_trade(trade):
     """
     takes in a trade and updates the database to reflect that the trade happened
     :param trade: the trade
     """
     print trade
     if trade['contract_type'] == 'futures':
         cash_position = session.query(models.Position).filter_by(contract=btc, username=trade['username']).one()
         future_position = create_or_get_position(trade['username'], trade['contract'], trade['price'])

         #mark to current price as if everything had been entered at that price and profit had been realized
         cash_position.position += (trade['price'] - future_position.reference_price) * future_position.position
         future_position.reference_price = trade['price']

         #note that even though we're transferring money to the account, this money may not be withdrawable
         #because the margin will raise depending on the distance of the price to the safe price

         # then change the quantity
         future_position.position += trade['signed_qty']

         session.merge(future_position)
         session.merge(cash_position)

     elif trade['contract_type'] == 'prediction':
        cash_position = session.query(models.Position).filter_by(contract=btc, username=trade['username']).one()
        prediction_position = create_or_get_position(trade['username'], trade['contract'], 0)

        cash_position.position -= trade['signed_qty'] * trade['price']
        prediction_position.position += trade['signed_qty']

        session.merge(prediction_position)
        session.merge(cash_position)

     elif trade['contract_type'] == 'cash_pair':
        # forgive me lord, for I'm about to sin

        try:
            from_currency, to_currency = get_currencies_in_pair(trade['ticker'])


            from_position = session.query(models.Position).filter_by(contract=from_currency,
                                                                     username=trade['username']).one()
            to_position = session.query(models.Position).filter_by(contract=to_currency,
                                                                   username=trade['username']).one()
            from_position.position -= trade['signed_qty'] * trade['price']
            to_position.position += trade['signed_qty']

            session.merge(from_position)
            session.merge(to_position)

        except:
            logging.error("trying to trade a cash pair where the ticker has the wrong format")

     else:
        logging.error("unknown contract type")

     session.commit()


def cancel_order(details):
    """
    Cancels an order by id
    :param username:
    :param order_id:
    :return:
    """

    print 'accountant received', details
    order_id = details['id']
    username = details['username']
    try:
        # sanitize inputs:
        order_id = int(order_id)
        # try db query
        order = session.query(models.Order).filter_by(id=order_id).one()
        if order.username != username:
            return False

        m_e_order = order.to_matching_engine_order()
        engine_sockets[order.contract_id].send(json.dumps({"cancel": m_e_order}))
        return True

    except NoResultFound:
        return False


def place_order(order):
    """
    Places an order
    :param order: dictionary representing the order to be placed
    :return: id of the order placed or -1 if failure
    """
    try:
        user = session.query(models.User).get(order['username'])
        if "contract_id" in order:
            contract = session.query(models.Contract).filter_by(id=order['contract_id']).first()
        else:
            contract = session.query(models.Contract).filter_by(
                ticker=order["ticker"]).order_by(
                        models.Contract.id.desc()).first()

        # check that the contract is active
        if contract == None:
            return False
        if not contract.active:
            return False

        # check that the price is an integer and within a valid range

        # case of predictions
        if contract.contract_type == 'prediction':
            # contract.denominator happens to be the same as the finally payoff
            if not 0 <= order["price"] <= contract.denominator:
                return False

        o = models.Order(user, contract, order["quantity"], order["price"], "BUY" if order["side"] == 0 else "SELL")

        session.add(o)
        session.commit()

        if accept_order_if_possible(user.username, o.id):
            m_e_order = o.to_matching_engine_order()
            engine_sockets[o.contract_id].send(json.dumps({"order":m_e_order}))
        else:
            logging.info("lol you can't place the order, you don't have enough margin")
    except Exception as e:
        session.rollback()
        raise e

def deposit_cash(details):
    """
    Deposits cash
    :param address:
    :param total_received:
    :return:
    """
    try:
        print 'received', details
        currency = btc
        address = details['address']
        total_received = details['total_received']

        # sanitize inputs:
        address = str(address)
        total_received = int(total_received)

        #query for db objects we want to update
        total_deposited_at_address = session.query(models.Addresses).filter_by(address=address).one()
        user_cash_position = session.query(models.Position).filter_by(username=total_deposited_at_address.username,contract=currency).one()

        #prepare cash deposit
        deposit = total_received - total_deposited_at_address.accounted_for
        print 'updating ', user_cash_position, ' to '
        user_cash_position.position += deposit
        print user_cash_position
        print 'with a deposit of: ',deposit

        #prepare record of deposit
        total_deposited_at_address.accounted_for = total_received

        session.add(total_deposited_at_address)
        session.add(user_cash_position)

        session.commit()
        return True

    except NoResultFound:
        session.rollback()
        return False

def clear_contract(details):
    try:
        contract = session.query(models.Contract).filter_by(
                id=details["id"]).first()
        # disable new orders on contract
        contract.active = False
        # cancel all pending orders
        orders = session.query(models.Order).filter_by(
                contract=contract, is_cancelled=False).all()
        for order in orders:
            cancel_order({"username":order.username, "id":order.id})
        # place orders on behalf of users
        positions = session.query(models.Position).filter_by(
                contract=contract).all()
        for position in positions:
            order = {}
            order["username"] = position.username
            order["contract_id"] = position.contract_id
            if position.position > 0:
                order["quantity"] = position.position
                order["side"] = 0 # sell
            elif position.position < 0:
                order["quantity"] = -position.position
                order["side"] = 1 # buy
            order["price"] = details["price"]
            place_order(order)
        session.commit()
    except:
        session.rollback()

engine_sockets = {i.id: context.socket(zmq.constants.PUSH)
                  for i in session.query(models.Contract).filter_by(active=True)}

for contract_id, socket in engine_sockets.iteritems():
    socket.connect('tcp://%s:%d' % ("localhost", 4200 + contract_id))

safe_prices = {}
for c in session.query(models.Contract):
    # this should be refined at some point for a better
    # initial safe value
    try:
        last_trade = session.query(models.Trade).filter_by(contract=c).order_by(
            models.Trade.timestamp.desc()).first()
        #round to an int for safe prices
        safe_prices[c.ticker] = int(last_trade.price)
    except:
        logging.warning("warning, missing last trade for contract: %s. Using 42 as a stupid default" % c.ticker)
        safe_prices[c.ticker] = 42

#TODO: make one zmq socket for each connecting service (webserver, engine, leo)
while True:
    request = connector.recv_json()
    for request_type, request_details in request.iteritems():
        if request_type == 'safe_price':
            safe_prices.update(request_details)
        elif request_type == 'trade':
            process_trade(request_details)
        elif request_type == 'place_order':
            place_order(request_details)
        elif request_type == 'cancel_order':
            cancel_order(request_details)
        elif request_type == 'deposit_cash':
            deposit_cash(request_details)
        elif request_type == 'clear':
            clear_contract(request_details)
        else:
            logging.warning("unknown request type: %s", request_type)

