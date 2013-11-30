#!/usr/bin/env python

import sys
import logging

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
            return "BUY"
        elif side == OrderSide.SELL:
            return "SELL"


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
        if self.order_side == other.order_side:
            return False
        if (self.price - other.price) * self.side > 0:
            return False
        return True

    def __str__(self):
        return "Order(side=%s, price=%s, quantity=%s, id=%d)" % (OrderSide.name(self.side), self.price, self.quantity, self.id)

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
    
    def on_trade_success(self, order, passive_order):
        pass

    def on_trade_fail(self, order, passive_order, reason):
        pass

    def on_cancel_success(self, order):
        pass

    def on_cancel_fail(self, order_id, reason):
        pass


class Engine:
    def __init__(self, socket, session, ticker):
        self.orderbook = [[], []]
        self.ordermap = {}

        self.session = session
        self.ticker = ticker

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
            for order in db_session.query(models.Order).filter(models.Order.quantity_left > 0).filter_by(contract_id=contract_id):
                order.is_cancelled = True
                self.session.merge(order)
            self.session.commit()
        except Exception, e:
            logging.critical("Cannot clear existing orders. %s" % e)
            raise e

        self.socket = socket

        self.notify_init()
    
    def process(self, order):

        # Loop until the order or the opposite side is exhausted.
        while order.quantity > 0:

            # If the other side has run out of orders, break.
            if len(self.orderbook[OrderSide.other(order.side)]) == 0:
                break

            # Find the best counter-offer.
            passive_order = self.orderbook[OrderSide.other(order.side)][0]

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
                notify_trade_failed(order, passive_order, "database error")
                return False

            # At this point, the trade has been successful.

            # If the passive order is used up, remove it.
            if passive_order.quantity <= 0:
                heapq.heappop(self.orderbook[passive_order.side])
                del self.ordermap[passive_order.id]


        # If order is not completely filled, push remainer onto heap and make
        #   an entry in the map.
        if order.quantity > 0:
            heapq.heappush(self.orderbook[order.side], order)
            self.ordermap[order.id] = order

            # Notify listeners
            notify_queue_success(order)

        # Order has been successfully processed.
        return True

    def match(self, order, passive_order):

        # Calculate trading quantity.
        quantity = min(order.quantity, passive_order.quantity)
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
        trade = models.Trade(db_order, db_passive_order, db_passive_order.price, quantity)

        # If this fails, rollback.
        try:
            db_order.quantity_left -= qty
            db_passive_order.quantity_left -= qty
            self.session.merge(db_order)
            self.session.merge(db_passive_order)
            self.session.add(trade)
            self.session.commit()
        except Exception, e:
            logging.error("Unable to match orders id=%s with id=%s. %s" % (order.id, passive_order.id, e))
            self.session.rollback()
            raise e

        # At this point the trade has been successful. Notify listeners.

        notify_trade_success(order, passive_order)
        
        return True

    def cancel(self, id):
        # Check to make sure order has not already been filled.
        if details.order_id not in self.ordermap:
            # Too late to cancel.
            logging.info("The order id=%s cannot be cancelled, it's already outside the book." % id)
            notify_cancel_failed(id, "the order is no longer on the book")
            return False

        # Find the order object.
        order = self.ordermap[id]

        # Remove the order from the book.
        del self.ordermap[id]
        self.orderbook[order.side].remove(order)
        heapq.heapify(self.orderbook[order.side])

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
            notify_cancel_failed(id, "database error")
            return False

        # Notify user of cancellation.
        notify_cancel_success(order)

        return True

    def run(self):
        while True:
            try:
                request = self.socket.recv_json()
                for request_type, details in request.iteritems():
                    if request_type == "order":
                        order = Order(**details)
                        self.process(order)

                    elif request_type == "cancel":
                        self.cancel(details.order_id)
                            
                    elif request_type == "clear":
                        pass
            except ValueError:
                logging.warn("Received message cannot be decoded.")
            except Exception, e:
                logging.critical("Critical error: " + e)
                sys.exit(1)

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
    
    def notify_trade_success(self, order, passive_order):
        for listener in self.listeners:
            try:
                listener.on_trade_success(order, passive_order)
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


class LoggingEngineListener:
    def __init__(self, engine):
        self.engine = engine

    def on_init(self):
        self.ticker = self.engine.ticker
        self.contract_id = self.engine.contract_id

    def on_init(self):
        logging.info("Engine for contract %s (%d) started." % (self.ticker, self.contract_id))
        logging.info("Listening for connections on port %d." % (4200 + self.contract_id))

    def on_shutdown(self):
        logging.info("Engine for contract %s stopped." % self.ticker)

    def on_queue_success(self, order):
        logging.info("%s queued." % order)
    
    def on_queue_fail(self, order, reason):
        logging.warn("%s cannot be queued because %s." % (order, reason))

    def on_trade_success(self, order, passive_order):
        logging.info("Successful trade between %s and %s." % (order, passive_order))

    def on_trade_fail(self, order, passive_order, reason):
        logging.warn("Cannot complete trade between %s and %s." % (order, passive_order))

    def on_cancel_success(self, order):
        logging.info("%s cancelled." % order)

    def on_cancel_fail(self, order, reason):
        logging.info("Cannot cancel %s because %s." % (order, reason))



class AccountantNotifier(EngineListener):
    def __init__(self, accountant, engine):
        self.accountant = accountant
        self.engine = engine

    def on_init(self):
        self.ticker = engine.ticker

    def on_trade_success(self, order, passive_order):
        self.accountant.send_json({
                'trade': {
                    'username':order.username,
                    'contract': order.contract,
                    'signed_qty': order.quantity * order.side,
                    'price': passive_order.price,
                    'contract_type': self.contract_type
                }
            })

        self.accountant.send_json({
                'trade': {
                    'username':passive_order.username,
                    'contract': passive_order.contract,
                    'signed_qty': passive_order.quantity * passive_order.side,
                    'price': passive_order.price,
                    'contract_type': self.contract_type
                }
            })

class WebserverNotifier(EngineListener):
    def __init__(self, webserver, engine):
        self.webserver = webserver
        self.engine = engine

    def on_trade_success(self, order, passive_order):
        self.webserver.send_json({'trade': {'ticker': contract_name, 'quantity': quantity, 'price': passive_order.price}})
        self.webserver.send_json({'fill': [order.username, {'order': order.order_id, 'quantity': quantity, 'price': passive_order.price}]})
        self.webserver.send_json({'fill': [passive_order.username, {'order': passive_order.order_id, 'quantity': quantity, 'price': passive_order.price}]})
        self.update_book()

    def on_queue_success(self, order):
        self.update_book()

    def on_cancek_success(self, order):
        self.webserver.send_json({'cancel': [order.username, {'order': order.id}]})

    def update_book(self):
        self.publisher.send_json(
            {'book_update':
                {self.engine.ticker:
                    [{"quantity": o.quantity, "price": o.price, "order_side": o.side} for o in engine.ordermap.values()]}})


class SafePriceNotifier(EngineListener):
    def __init__(self, forwarder, engine):
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

    def on_trade_success(self, order, passive_order):
        self.ema_volume = self.decay * self.ema_volume + (1 - self.decay) * order.quantity
        self.ema_price_volume = self.decay * self.ema_price_volume + (1 - self.decay) * order.quantity * passive_order.price
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
engine_socket.bind('tcp://127.0.0.1:%d' % 4200 + contract_id)

webserver_socket = context.socket(zmq.PUSH)
webserver_socket.connect(config.get("webserver", "zmq_address"))

accountant_socket = context.socket(zmq.PUSH)
accountant_socket.connect(config.get("accountant", "zmq_address"))

forwarder_socket = context.socket(zmq.PUB)
forwarder_socket.connect(config.get("safe_price_forwarder", "zmq_frontend_address"))

engine = Engine(session, engine_socket, args[0])

logger = LoggingNotifier(engine)
webserver_notifier = WebserverNotifier(engine, webserver_socket)
accountant_notifier = AccountantNotifier(engine, accountant_socket)
safeprice_notifier = SafePriceNotifier(engine, forwarder_socket)

engine.add_listener(logger)
engine.add_listener(webserver_notifier)
engine.add_listener(accountant_notifier)
engine.add_listener(safeprice_notifier)

engine.run()

