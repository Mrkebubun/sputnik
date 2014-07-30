#!/usr/bin/env python

import config

from optparse import OptionParser
parser = OptionParser()
parser.add_option("-c", "--config", dest="filename",
        help="config file", default=None)
(options, args) = parser.parse_args()
if options.filename:
    config.reconfigure(options.filename)

import logging
import time
import heapq

import database
import models
import accountant

import util

from twisted.internet import reactor
from zmq_util import export, router_share_async, push_proxy_async

class OrderSide:
    BUY = -1
    SELL = 1

    @staticmethod
    def name(n):
        if n == -1:
            return "BUY"
        return "SELL"


class Order:
    def __init__(self, id=None, contract=None, quantity=None,
            quantity_left=None, price=None, side=None, username=None):
        self.id = id
        self.contract = contract
        self.quantity = quantity
        self.quantity_left = quantity
        self.price = price
        self.side = side
        self.username = username
        self.timestamp = int(time.time() * 1e6)

    def matchable(self, other):
        if self.side == other.side:
            return False
        return (self.price - other.price) * self.side <= 0

    def __str__(self):
        return "%sOrder(price=%s, quantity=%s/%s, id=%d)" % ("Bid" if self.side < 0 else "Ask", self.price, self.quantity_left, self.quantity, self.id)

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

        # Price-Time Priority
        return (self.side * self.price, self.timestamp) < (other.side * other.price, other.timestamp)


class EngineListener:
    def on_init(self):
        pass

    def on_shutdown(self):
        pass

    def on_queue_success(self, order):
        pass

    def on_queue_fail(self, order, reason):
        pass

    def on_trade_success(self, order, passive_order, price, quantity):
        pass

    def on_trade_fail(self, order, passive_order, reason):
        pass

    def on_cancel_success(self, order):
        pass

    def on_cancel_fail(self, order_id, reason):
        pass


class Engine:
    def __init__(self):
        self.orderbook = {OrderSide.BUY: [], OrderSide.SELL: []}
        self.ordermap = {}
        self.listeners = []

    def place_order(self, order):

        # Loop until the order or the opposite side is exhausted.
        while order.quantity_left > 0:

            # If the other side has run out of orders, break.
            if not self.orderbook[-order.side]:
                break

            # Find the best counter-offer.
            passive_order = self.orderbook[-order.side][0]

            # We may assume this order is the best offer on its side. If not,
            #   the following will automatically fail since it failed for
            #   better offers already.

            # If the other side's best order is too pricey, break.
            if not order.matchable(passive_order):
                break

            # Trade.
            self.match(order, passive_order)

            # If the passive order is used up, remove it.
            if passive_order.quantity_left <= 0:
                heapq.heappop(self.orderbook[passive_order.side])
                del self.ordermap[passive_order.id]


        # If order is not completely filled, push remainder onto heap and make
        #   an entry in the map.
        if order.quantity_left > 0:
            heapq.heappush(self.orderbook[order.side], order)
            self.ordermap[order.id] = order

            # Notify listeners
            self.notify_queue_success(order)

        # Order has been successfully processed.
        return True

    def match(self, order, passive_order):

        # Calculate trading quantity and price.
        quantity = min(order.quantity_left, passive_order.quantity_left)
        price = passive_order.price

        # Adjust orders on the books
        order.quantity_left -= quantity
        passive_order.quantity_left -= quantity

        # Notify listeners.
        self.notify_trade_success(order, passive_order, price, quantity)

    def cancel_order(self, id):
        # Check to make sure order has not already been filled.
        if id not in self.ordermap:
            # Too late to cancel.
            logging.info("The order id=%s cannot be cancelled, it's already outside the book." % id)
            self.notify_cancel_fail(id, "the order is no longer on the book")
            return False

        # Find the order object.
        order = self.ordermap[id]

        # Remove the order from the book.
        del self.ordermap[id]
        self.orderbook[order.side].remove(order)
        heapq.heapify(self.orderbook[order.side]) #yuck

        # Notify user of cancellation.
        self.notify_cancel_success(order)

        return True

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

    def notify_trade_success(self, order, passive_order, price, quantity):
        for listener in self.listeners:
            try:
                listener.on_trade_success(order, passive_order, price, quantity)
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
    def __init__(self, engine, contract):
        self.engine = engine
        self.contract = contract

    def on_init(self):
        self.ticker = self.contract.ticker
        logging.info("Engine for contract %s (%d) started." % (self.ticker, self.contract.id))
        logging.info("Listening for connections on port %d." % (config.getint("engine", "base_port") + self.contract.id))

    def on_shutdown(self):
        logging.info("Engine for contract %s stopped." % self.ticker)

    def on_queue_success(self, order):
        logging.info("%s queued." % order)
        self.print_order_book()

    def on_queue_fail(self, order, reason):
        logging.warn("%s cannot be queued because %s." % (order, reason))

    def on_trade_success(self, order, passive_order, price, quantity):
        logging.info("Successful trade between order id=%s and id=%s for %s lots at %s each." % (order.id, passive_order.id, order.side * quantity, price))
        self.print_order_book()

    def on_trade_fail(self, order, passive_order, reason):
        logging.warn("Cannot complete trade between %s and %s." % (order, passive_order))

    def on_cancel_success(self, order):
        logging.info("%s cancelled." % order)
        self.print_order_book()

    def on_cancel_fail(self, order, reason):
        logging.info("Cannot cancel %s because %s." % (order, reason))

    def print_order_book(self):
        logging.debug("Orderbook for %s:" % self.contract.ticker)
        logging.debug("Bids                   Asks")
        logging.debug("Vol.  Price     Price  Vol.")
        length = max(len(self.engine.orderbook[OrderSide.BUY]), len(self.engine.orderbook[OrderSide.SELL]))
        for i in range(length):
            try:
                ask = self.engine.orderbook[OrderSide.SELL][i]
                ask_str = "{:<5} {:<5}".format(ask.price, ask.quantity_left)
            except:
                ask_str = "           "
            try:
                bid = self.engine.orderbook[OrderSide.BUY][i]
                bid_str = "{:>5} {:>5}".format(bid.quantity_left, bid.price)
            except:
                bid_str = "           "
            logging.debug("{}     {}".format(bid_str, ask_str))


class AccountantNotifier(EngineListener):
    def __init__(self, engine, accountant, contract):
        self.engine = engine
        self.accountant = accountant
        self.contract = contract

    def on_init(self):
        self.ticker = self.contract.ticker

    def on_trade_success(self, order, passive_order, price, quantity):
        uid = util.get_uid()
        self.accountant.post_transaction(order.username,
                {
                    'username': order.username,
                    'aggressive': True,
                    'contract': self.ticker,
                    'order': order.id,
                    'other_order': passive_order.id,
                    'side': OrderSide.name(order.side),
                    'quantity': quantity,
                    'price': price,
                    'timestamp': order.timestamp,
                    'uid': uid
                }
            )

        self.accountant.post_transaction(passive_order.username,
                {
                    'username': passive_order.username,
                    'aggressive': False,
                    'contract': self.ticker,
                    'order': passive_order.id,
                    'other_order': order.id,
                    'side': OrderSide.name(passive_order.side),
                    'quantity': quantity,
                    'price': price,
                    'timestamp': order.timestamp,
                    'uid': uid
                }
            )

class WebserverNotifier(EngineListener):
    def __init__(self, engine, webserver, contract):
        self.engine = engine
        self.webserver = webserver
        self.contract = contract

    def on_queue_success(self, order):
        self.update_book()

    def on_cancel_success(self, order):
        self.update_book()

    def update_book(self):
        book = {"contract": self.contract.ticker, "bids": [], "asks": []}
        for entry in self.engine.orderbook[OrderSide.BUY]:
            quantity = book["bids"].setdefault(entry.price, 0)
            quantity += entry.quantity
            book["bids"][entry.price] = quantity
        self.webserver.book(self.contract.ticker, book)

class SafePriceNotifier(EngineListener):
    def __init__(self, engine, forwarder, accountant, webserver):
        self.engine = engine
        self.forwarder = forwarder
        self.accountant = accountant
        self.webserver = webserver

        self.ema_price_volume = 0
        self.ema_volume = 0
        self.decay = 0.9

    def on_init(self):
        self.ticker = self.contract.ticker

        # TODO: seriously, fix this hack
        try:
            self.safe_price = self.engine.session.query(models.Trade).join(models.Contract).filter_by(ticker=self.ticker).all()[-1].price
        except IndexError:
            self.safe_price = 42

        self.forwarder.send_json({'safe_price': {engine.ticker: self.safe_price}})
        self.accountant.send_json({'safe_price': {engine.ticker: self.safe_price}})
        self.webserver.send_json({'safe_price': {engine.ticker: self.safe_price}})

    def on_trade_success(self, order, passive_order, price, quantity):
        self.ema_volume = self.decay * self.ema_volume + (1 - self.decay) * order.quantity
        self.ema_price_volume = self.decay * self.ema_price_volume + (1 - self.decay) * quantity * price
        self.safe_price = int(self.ema_price_volume / self.ema_volume)

        self.forwarder.send_json({'safe_price': {engine.ticker: self.safe_price}})
        self.accountant.send_json({'safe_price': {engine.ticker: self.safe_price}})
        self.webserver.send_json({'safe_price': {engine.ticker: self.safe_price}})


class AccountantExport:
    def __init__(self, engine):
        self.engine = engine

    @export
    def place_order(self, order):
        return self.engine.place_order(Order(**order))

    @export
    def cancel_order(self, id):
        return self.engine.cancel_order(id)

    @export
    def ping(self):
        return "pong"

if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s', level=logging.DEBUG)

    session = database.make_session()
    ticker = args[0]

    try:
        contract = session.query(models.Contract).filter_by(ticker=ticker).one()
    except Exception, e:
        logging.critical("Cannot determine ticker id. %s" % e)
        raise e

    # We are no longer cancelling orders here.
    # We should find a better place for this.
    # Didn't we decide not to cancel orders when the engine restarts? We will have
    # to load orders from the db and add them to the engine in this case
    # Well... it is not possible if the engine does not touch the orders table.
    """
    try:
        for order in session.query(models.Order).filter_by(
                is_cancelled=False).filter_by(contract_id=self.contract_id):
            order.is_cancelled = True
            self.session.merge(order)
        self.session.commit()
    except Exception, e:
        logging.critical("Cannot clear existing orders. %s" % e)
        raise e
    """

    engine = Engine()
    accountant_export = AccountantExport(engine)
    port = config.getint("engine", "base_port") + contract.id
    router_share_async(accountant_export, "tcp://127.0.0.1:%d" % port)

    logger = LoggingListener(engine, contract)
    accountant = accountant.AccountantProxy("push",
            config.get("accountant", "engine_export"),
            config.getint("accountant", "engine_export_base_port"))
    accountant_notifier = AccountantNotifier(engine, accountant, contract)
    webserver = push_proxy_async(config.get("webserver", "engine_export"))
    webserver_notifier = WebserverNotifier(engine, webserver, contract)
    #safe_price_notifier = SafePriceNotifier(engine)
    engine.add_listener(logger)
    engine.add_listener(accountant_notifier)
    engine.add_listener(webserver_notifier)
    #engine.add_listener(safe_price_notifier)

    engine.notify_init()

    reactor.run()

