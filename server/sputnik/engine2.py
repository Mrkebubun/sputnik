#!/usr/bin/env python

import sys
import logging
import time
import heapq

import zmq
import database
import models

from optparse import OptionParser
parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
        help="config file", default="../config/sputnik.ini")
(options, args) = parser.parse_args()

from ConfigParser import SafeConfigParser
config = SafeConfigParser()
config.read(options.filename)

logging.basicConfig(level=logging.DEBUG)

class OrderSide:
    BUY = -1 
    SELL = 1

    @staticmethod
    def other(side):
        return -side

    @staticmethod
    def name(side):
        if side == OrderSide.BUY:
            return "Bid"
        elif side == OrderSide.SELL:
            return "Ask"


class Order:
    def __init__(self, id=None, contract=None, quantity=None, price=None,
            side=None, username=None):
        self.id = id
        self.contract = contract
        self.quantity = quantity
        self.price = price
        self.side = side
        self.username = username
        self.timestamp = time.time()
   
    def matchable(self, other):
        if self.side == other.side:
            return False
        if (self.price - other.price) * self.side > 0:
            return False
        return True

    def __str__(self):
        return "%sOrder(price=%s, quantity=%s, id=%d)" % (OrderSide.name(self.side), self.price, self.quantity, self.id)

    def __repr__(self):
        return self.__dict__.__repr__()

    def __eq__(self, other):
        return self.side == other.side and self.price == other.price \
            and self.timestamp == other.timestamp

    def __lt__(self, other):
        """
        Returns whether an order is higher than another in the order book.
        """

        if self.side is not other.side:
            raise Exception("Orders are not comparable.")

        if self.side == OrderSide.BUY:
            if self.price < other.price:
                return False
            elif self.price > other.price:
                return True
            else:
                return self.timestamp < other.timestamp
        elif self.side == OrderSide.SELL:
            if self.price > other.price:
                return False
            elif self.price < other.price:
                return True
            else:
                return self.timestamp < other.timestamp

class EngineListener:
    def on_init(self):
        pass

    def on_shutdown(self):
        pass

    def on_queue_success(self, order):
        pass
    
    def on_queue_fail(self, order, reason):
        pass
    
    def on_trade_success(self, order, passive_order, price, signed_quantity):
        pass

    def on_trade_fail(self, order, passive_order, reason):
        pass

    def on_cancel_success(self, order):
        pass

    def on_cancel_fail(self, order_id, reason):
        pass


class Engine:
    def __init__(self, socket, session, ticker):
        self.orderbook = {"Ask":[], "Bid":[]}
        self.ordermap = {}

        self.socket = socket
        self.session = session
        self.ticker = ticker

        self.listeners = []

        # Determine contract id
        try:
            self.contract_id = self.session.query(models.Contract).filter_by(ticker=ticker).one().id
        except Exception, e:
            logging.critical("Cannot determine ticker id. %s" % e)
            raise e
      
        # Determine contract type
        try:
            self.contract_type = session.query(models.Contract).filter_by(
                                ticker=ticker).order_by(models.Contract.id.desc()).first().contract_type
        except Exception, e:
            logging.error("Cannot determine contract type. %s" % e)


        try:
            for order in self.session.query(models.Order).filter(models.Order.quantity_left > 0).filter_by(contract_id=contract_id):
                order.is_cancelled = True
                self.session.merge(order)
            self.session.commit()
        except Exception, e:
            logging.critical("Cannot clear existing orders. %s" % e)
            raise e
    
    def process(self, order):

        # Loop until the order or the opposite side is exhausted.
        while order.quantity > 0:

            # If the other side has run out of orders, break.
            if len(self.orderbook[OrderSide.name(OrderSide.other(order.side))]) == 0:
                break

            # Find the best counter-offer.
            passive_order = self.orderbook[OrderSide.name(OrderSide.other(order.side))][0]

            # We may assume this order is the best offer on its side. If not,
            #   the following will automatically fail since it failed for
            #   better offers already.

            # If the other side's best order is too pricey, break.
            if not order.matchable(passive_order):
                break

            # Trade.
            # If this method fails, something horrible has happened.
            #   Do not accept the order.
            try:
                self.match(order, passive_order)
            except Exception, e:
                self.notify_trade_fail(order, passive_order, "database error")
                return False

            # At this point, the trade has been successful.

            # If the passive order is used up, remove it.
            if passive_order.quantity <= 0:
                heapq.heappop(self.orderbook[OrderSide.name(passive_order.side)])
                del self.ordermap[passive_order.id]


        # If order is not completely filled, push remainer onto heap and make
        #   an entry in the map.
        if order.quantity > 0:
            heapq.heappush(self.orderbook[OrderSide.name(order.side)], order)
            self.ordermap[order.id] = order

            # Notify listeners
            self.notify_queue_success(order)

        # Order has been successfully processed.
        return True

    def match(self, order, passive_order):

        # Calculate trading quantity and price.
        quantity = min(order.quantity, passive_order.quantity)
        signed_quantity = quantity * order.side
        price = passive_order.price
        
        # Adjust orders on the books
        order.quantity -= quantity
        passive_order.quantity -= quantity

        # Retrieve the database objects.
        try:
            db_order = self.session.query(models.Order).filter_by(id = order.id).one()
        except Exception, e:
            logging.error("Unable to find order id=%s. Database object lookup error." % order.id)
            raise e
        try:
            db_passive_order = self.session.query(models.Order).filter_by(id = passive_order.id).one()
        except Exception, e:
            logging.error("Unable to find order id=%s. Database object lookup error." % passive_order.id)
            raise e
        
        # Create the trade.
        trade = models.Trade(db_order, db_passive_order, price, quantity)

        # If this fails, rollback.
        try:
            db_order.quantity_left -= quantity
            db_passive_order.quantity_left -= quantity
            self.session.merge(db_order)
            self.session.merge(db_passive_order)
            self.session.add(trade)
            self.session.commit()
        except Exception, e:
            logging.error("Unable to match orders id=%s with id=%s. %s" % (order.id, passive_order.id, e))
            self.session.rollback()
            raise e

        # Notify listeners.
        self.notify_trade_success(order, passive_order, price, signed_quantity)

        return True

    def cancel(self, id):
        # Check to make sure order has not already been filled.
        if id not in self.ordermap:
            # Too late to cancel.
            logging.info("The order id=%s cannot be cancelled, it's already outside the book." % id)
            self.notify_cancel_failed(id, "the order is no longer on the book")
            return False

        # Find the order object.
        order = self.ordermap[id]

        # Remove the order from the book.
        del self.ordermap[id]
        self.orderbook[OrderSide.name(order.side)].remove(order)
        heapq.heapify(self.orderbook[OrderSide.name(order.side)])

        # Fetch the database object and cancel the order. If this fails, rollback.
        try:
            db_order = self.session.query(models.Order).filter_by(
                    id=order.id).one()
            db_order.is_cancelled = True
            self.session.merge(db_order)
            self.session.commit()
        except Exception, e:
            logging.error("Unable to cancel order id=%s. %s" % (order.id, e))
            self.session.rollback()
            self.notify_cancel_failed(id, "database error")
            return False

        # Notify user of cancellation.
        self.notify_cancel_success(order)

        return True

    def run(self):
        self.notify_init()

        while True:
            try:
                request = self.socket.recv_json()
                for request_type, details in request.iteritems():
                    if request_type == "order":
                        order = Order(**details)
                        self.process(order)

                    elif request_type == "cancel":
                        self.cancel(details["id"])
                            
                    elif request_type == "clear":
                        pass
            except ValueError:
                logging.warn("Received message cannot be decoded.")
            except Exception, e:
                logging.critical("Critical error: %s", e)
                sys.exit(1)

        self.notify_shutdown()

    def add_listener(self, listener):
        self.listeners.append(listener)

    def remove_listener(self, listener):
        if listener in self.listeners:
            self.listeners.remove(listener)

    def notify_init(self):
        for listener in self.listeners:
            try:
                listener.on_init()
            except Exception, e:
                logging.warn("Exception in on_init of %s: %s." % (listener, e))

    def notify_shutdown(self):
        for listener in self.listeners:
            try:
                listener.on_shutdown()
            except Exception, e:
                logging.warn("Exception in on_shutdown of %s: %s." % (listener, e))

    def notify_queue_success(self, order):
        for listener in self.listeners:
            try:
                listener.on_queue_success(order)
            except Exception, e:
                logging.warn("Exception in on_queue_success of %s: %s." % (listener, e))
    
    def notify_queue_fail(self, order, reason):
        for listener in self.listeners:
            try:
                listener.on_queue_fail(order, reason)
            except Exception, e:
                logging.warn("Exception in on_queue_fail of %s: %s." % (listener, e))
    
    def notify_trade_success(self, order, passive_order, price, signed_quantity):
        for listener in self.listeners:
            try:
                listener.on_trade_success(order, passive_order, price, signed_quantity)
            except Exception, e:
                logging.warn("Exception in on_trade_success of %s: %s." % (listener, e))

    def notify_trade_fail(self, order, passive_order, reason):
        for listener in self.listeners:
            try:
                listener.on_trade_fail(order, passive_order, reason)
            except Exception, e:
                logging.warn("Exception in on_trade_fail of %s: %s." % (listener, e))

    def notify_cancel_success(self, order):
        for listener in self.listeners:
            try:
                listener.on_cancel_success(order)
            except Exception, e:
                logging.warn("Exception in on_cancel_success of %s: %s." % (listener, e))

    def notify_cancel_fail(self, order, reason):
        for listener in self.listeners:
            try:
                listener.on_cancel_fail(order, reason)
            except Exception, e:
                logging.warn("Exception in on_cancel_fail of %s: %s." % (listener, e))


class LoggingListener:
    def __init__(self, engine):
        self.engine = engine

    def on_init(self):
        self.ticker = self.engine.ticker
        self.contract_id = self.engine.contract_id
        logging.info("Engine for contract %s (%d) started." % (self.ticker, self.contract_id))
        logging.info("Listening for connections on port %d." % (4200 + self.contract_id))

    def on_shutdown(self):
        logging.info("Engine for contract %s stopped." % self.ticker)

    def on_queue_success(self, order):
        logging.info("%s queued." % order)
        self.print_order_book()
    
    def on_queue_fail(self, order, reason):
        logging.warn("%s cannot be queued because %s." % (order, reason))

    def on_trade_success(self, order, passive_order, price, signed_quantity):
        logging.info("Successful trade between order id=%s and id=%s for %s lots at %s each." % (order.id, passive_order.id, signed_quantity, price))
        self.print_order_book()

    def on_trade_fail(self, order, passive_order, reason):
        logging.warn("Cannot complete trade between %s and %s." % (order, passive_order))

    def on_cancel_success(self, order):
        logging.info("%s cancelled." % order)
        self.print_order_book()

    def on_cancel_fail(self, order, reason):
        logging.info("Cannot cancel %s because %s." % (order, reason))

    def print_order_book(self):
        logging.debug("Orderbook for %s:" % self.engine.ticker)
        logging.debug("Bids                 Asks")
        logging.debug("Vol. Price     Price Vol.")
        length = max(len(self.engine.orderbook["Bid"]), len(self.engine.orderbook["Ask"]))
        for i in range(length):
            try:
                ask = self.engine.orderbook["Ask"][i]
                ask_str = "{:<5}{:<5}".format(ask.price, ask.quantity)
            except:
                ask_str = "          "
            try:
                bid = self.engine.orderbook["Bid"][i]
                ask_str = "{:>5}{:>5}".format(bid.price, bid.quantity)
            except:
                bid_str = "          "
            logging.debug("{}     {}".format(bid_str, ask_str))


class AccountantNotifier(EngineListener):
    def __init__(self, engine, accountant):
        self.engine = engine
        self.accountant = accountant

    def on_init(self):
        self.ticker = engine.ticker

    def on_trade_success(self, order, passive_order, price, signed_quantity):
        self.accountant.send_json({
                'trade': {
                    'username':order.username,
                    'contract': order.contract,
                    'signed_qty': signed_quantity,
                    'price': price,
                    'contract_type': self.engine.contract_type
                }
            })

        self.accountant.send_json({
                'trade': {
                    'username':passive_order.username,
                    'contract': passive_order.contract,
                    'signed_qty': passive_order.quantity * passive_order.side,
                    'price': passive_order.price,
                    'contract_type': self.engine.contract_type
                }
            })

class WebserverNotifier(EngineListener):
    def __init__(self, engine, webserver):
        self.engine = engine
        self.webserver = webserver

    def on_trade_success(self, order, passive_order, price, signed_quantity):
        quantity = abs(signed_quantity)
        self.webserver.send_json({'trade': {'ticker': self.engine.ticker, 'quantity': quantity, 'price': price}})
        self.webserver.send_json({'fill': [order.username, {'order': order.id, 'quantity': quantity, 'price': price}]})
        self.webserver.send_json({'fill': [passive_order.username, {'order': passive_order.id, 'quantity': quantity, 'price': price}]})
        self.update_book()

    def on_queue_success(self, order):
        self.webserver.send_json({'open_orders': [order.username, {'order': order.id, 'quantity':order.quantity, 'price':order.price, 'side': order.side,
                                                                   'ticker': self.engine.ticker, 'contract_id': self.engine.contract_id}]})
        self.update_book()

    def on_cancel_success(self, order):
        self.webserver.send_json({'cancel': [order.username, {'order': order.id}]})
        self.update_book()

    def update_book(self):
        self.webserver.send_json(
            {'book_update':
                {self.engine.ticker:
                    [{"quantity": o.quantity, "price": o.price, "side": o.side} for o in engine.ordermap.values()]}})


class SafePriceNotifier(EngineListener):
    def __init__(self, engine, forwarder):
        self.engine = engine
        self.forwarder = forwarder

        self.ema_price_volume = 0
        self.ema_volume = 0
        self.decay = 0.9

    def on_init(self):
        self.ticker = self.engine.ticker

        # TODO: seriously, fix this hack
        try:
            self.safe_price = self.engine.session.query(models.Trade).join(models.Contract).filter_by(ticker=self.ticker).all()[-1].price
        except IndexError:
            self.safe_price = 42

    def on_trade_success(self, order, passive_order, price, signed_quantity):
        self.ema_volume = self.decay * self.ema_volume + (1 - self.decay) * order.quantity
        self.ema_price_volume = self.decay * self.ema_price_volume + (1 - self.decay) * abs(signed_quantity) * price
        self.safe_price = int(self.ema_price_volume / self.ema_volume)

        self.forwarder.send_json({'safe_price': {engine.ticker: self.safe_price}})



session = database.Session()
context = zmq.Context()


try:
    contract_id = session.query(models.Contract).filter_by(ticker=args[0]).one().id
except Exception, e:
    logging.critical("Cannot determine ticker id. %s" % e)
    raise e

engine_socket = context.socket(zmq.PULL)
engine_socket.bind('tcp://127.0.0.1:%d' % (4200 + contract_id))

webserver_socket = context.socket(zmq.PUSH)
webserver_socket.connect(config.get("webserver", "zmq_address"))

accountant_socket = context.socket(zmq.PUSH)
accountant_socket.connect(config.get("accountant", "zmq_address"))

forwarder_socket = context.socket(zmq.PUB)
forwarder_socket.connect(config.get("safe_price_forwarder", "zmq_frontend_address"))

engine = Engine(engine_socket, session, args[0])

logger = LoggingListener(engine)
webserver_notifier = WebserverNotifier(engine, webserver_socket)
accountant_notifier = AccountantNotifier(engine, accountant_socket)
safeprice_notifier = SafePriceNotifier(engine, forwarder_socket)

engine.add_listener(logger)
engine.add_listener(webserver_notifier)
engine.add_listener(accountant_notifier)
engine.add_listener(safeprice_notifier)

engine.run()

