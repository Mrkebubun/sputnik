#!/usr/bin/env python
import config

from optparse import OptionParser
parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
        help="config file")
(options, args) = parser.parse_args()
if options.filename:
    config.reconfigure(options.filename)

import collections

import json
import re

__author__ = 'satosushi'

from sqlalchemy.orm.exc import NoResultFound
import zmq
import models
import database
import logging


context = zmq.Context()
connector = context.socket(zmq.constants.PULL)
connector.bind(config.get("accountant", "zmq_address"))

session = database.make_session()

logging.basicConfig(level=logging.DEBUG)


# type of messages:

# deposit/withdraw: adds or remove coins from the account
# increase/decrease required_margin: adds or remove to the required margin


class AccountantException(Exception):
    pass

class Accountant:
    def __init__(self, session):
        self.session = session
        self.btc = self.resolve("BTC")
       
    def get_user(self, username):
        """
        Return the User object corresponding to the username.
        :param username: the username to look up
        :return: the User matching the username
        """
        logging.debug("Looking up username %s." % username)

        try:
            return self.session.query(models.Users).filter_by(
                username=username).one()
        except NoResultFound:
            raise AccountantException("No such user: '%s'." % username)

    def get_contract(self, ticker):
        """
        Return the Contract object corresponding to the ticker.
        :param ticker: the ticker to look up or a Contract id
        :return: the last (id-wise) Contract object matching the ticker
        """
        logging.debug("Looking up contract %s." % ticker)

        try:
            ticker = int(ticker)
            return self.session.query(models.Contract).filter_by(
                contract_id=ticker).one()
        except NoResultFound:
            raise AccountantError("Could not resolve contract '%s'." % ticker)
        except ValueError:
            # drop through
            pass

        try:
            return self.session.query(models.Contract).filter_by(
                ticker=ticker).order_by(models.Contract.id.desc()).first()
        except NoResultFound:
            raise AccountantError("Could not resolve contract '%s'." % ticker)

    def get_position(self, username, contract, reference_price=0):
        """
        Return a user's position for a contact. If it does not exist,
            initialize it. 
        :param username: the username
        :param contract: the contract ticker or id
        :param reference_price: the (optional) reference price for the position
        :return: the position object
        """
        logging.debug("Looking up position for %s on %s." %
            (username, contract))

        user = self.get_user(username)
        contract = self.get_contract(contract)

        try:
            return self.session.query(models.Position).filter_by(
                user=user, contract=contract).one()
        except NoResultFound:
            logging.debug("Creating new position for %s on %s." %
                (username, contract))
            position = models.Position(user, contract)
            position.reference_price = reference_price
            self.session.add(pos)
            return position

    def split_pair(self, pair):
        """
        Return the underlying pair of contracts in a cash_pair contract.
        :param pair: the ticker name of the pair to split
        :return: a tuple of Contract objects
        """

        tokens = pair.split("/", 1)
        if len(tokens) == 1:
            raise AccountantException("'%s' is not a currency pair." % pair)
        try:
            source = self.get_contract(tokens[0])
            target = self.get_contract(tokens[1])
        except AccountantError:
            raise AccountantException("'%s' is not a currency pair." % pair)
         return source, target  

    def accept_order(self, order):
        """
        Accept the order if the user has sufficient margin. Otherwise, delete
            the order.
        :param order: Order object we wish to accept
        :return success: True if there was sufficient margin, otherwise False
        """
        logging.info("Trying to accept order %s." % order)

        low_margin, high_margin = margin.get_margin(
            self.session, order.user, order)

        cash_position = self.get_position(order.username, "BTC")

        logging.info("high_margin = %d, low_margin = %d, cash_position = %d" %
            (high_margin, low_margin, cash_position.position))

        if high_margin > cash_position.position:
            # TODO replace deleting rejected orders with marking them as
            #   rejected, using an enum

            logging.info("Order rejected due to margin.")
            session.delete(order)
            session.commit()
            return False
        else:
            logging.info("Order accepted.")
            order.accepted = True
            session.merge(order)
            session.commit()
            return True

    def process_transaction(self, transaction):
        """
        Update the database to reflect that the given trade happened
        :param trransaction: the transaction object
        :return: None
        """
        logging.info("Processing transaction %s." % transaction)

        username = transaction["username"]
        ticker = transaction["ticker"]) 
        price = transaction["price"]
        signed_quantity = transaction["signed_quantity"]
        
        contract = self.get_contract(ticker)

        if contract.contract_type == "futures":
            logging.debug("This is a futures trade.")
            cash_position = self.get_position(username, "BTC")
            future_position = self.get_position(username, ticker, price)

            # mark to current price as if everything had been entered at that
            #   price and profit had been realized
            cash_position.position +=
                (price - future_position.reference_price) * \
                future_position.position
            future_position.reference_price = price

            # note that even though we're transferring money to the account,
            #   this money may not be withdrawable because the margin will
            #   raise depending on the distance of the price to the safe price

            # then change the quantity
            future_position.position += signed_quantity

            session.merge(cash_position)
            session.merge(future_position)

        elif contract.contract_type == "prediction":
            cash_position = self.get_position(username, "BTC")
            prediction_position = self.get_position(username, ticker)

            cash_position.position -= signed_quantity * price
            prediction_position.position += signed_quantity

            session.merge(cash_position)
            session.merge(prediction_position)

        elif contract.contract_type == "cash_pair":
            from_currency, to_currency = self.split_pair(ticker)
            from_position = self.get_position(username, from_currency)
            to_position = self.get_position(username, to_currency)
            
            from_delta_float = float(signed_quantity * price) / \
                (contract.denominator * to_currency.denominator)
            from_delta_int = int(from_delta_float)
            if from_delta_float != from_delta_int:
                logging.error("Position change is not an integer.")

            from_position.position -= from_delta_int
            to_position.position += signed_quantity

            session.merge(from_position)
            session.merge(to_position)

        else:
            logging.error("Unknown contract type '%s'." %
                contract.contract_type)

     session.commit()


    def cancel_order(self, id):
        """
        Cancel an order by id.
        :param id: The order id to cancel
        :return: None
        """
        logging.info("Received request to cancel order id %d." % id)
        
        try:
            order = session.query(models.Order).filter_by(id=order_id).one()
            m_e_order = order.to_matching_engine_order()
            engine_sockets[order.contract_id].send(json.dumps({"cancel": m_e_order}))
            return True
        except NoResultFound:
            return False


    def place_order(order):
        """
        Place an order
        :param order: dictionary representing the order to be placed
        :return: id of the order placed or -1 if failure
        """
        user = self.get_user(order["username"])
        contact = self.get_contract(order["ticker"])

        if not contract.active:
            return False

        # do not allow orders for internally used contracts
        if contract.contract_type == 'cash':
            return False

        # TODO: check that the price is an integer and within a valid range

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
            from_currency, to_currency = self.split_pair(order.contract.ticker)
            if order.side == 'BUY':
                max_cash_spent[from_currency.ticker] += (order.quantity_left / order.contract.lot_size) * order.price
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

