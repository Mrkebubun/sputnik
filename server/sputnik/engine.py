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
import util

import zmq
from zmq_util import export, router_share_sync, push_proxy_sync
import database as db
import models
from datetime import datetime

class EngineException(Exception):
    pass

class SafePricePublisher(object):
    # update exponential moving average volume weighted vwap
    # and push the price on a dedicated socket

    def __init__(self):

        self.ema_price_volume = 0
        self.ema_volume = 0
        self.decay = 0.9

        #make safe price equal to last recorded trade...
        try:
            self.safe_price = db_session.query(models.Trade).join(models.Contract).filter_by(ticker=contract_name).all()[-1].price
        except IndexError:
            self.safe_price = 42
        accountant.safe_prices(contract_name, self.safe_price)
        webserver.safe_prices(contract_name, self.safe_price)
        safe_price_forwarder.send_json({'safe_price': {contract_name: self.safe_price}})

    def onTrade(self, last_trade):
        '''
        calculate the ema by volume
        :param last_trade:
        '''

        self.ema_volume = self.decay * self.ema_volume + (1 - self.decay) * last_trade['quantity']
        self.ema_price_volume = self.decay * self.ema_price_volume + (1 - self.decay) * last_trade['quantity'] * last_trade['price']


        #round float for safe price. sub satoshi granularity is unneccessary and
        #leads to js rounding errors:

        self.safe_price = int(self.ema_price_volume / self.ema_volume)
        logging.info('Woo, new safe price %d' % self.safe_price)
        accountant.safe_price(contract_name, self.safe_price)
        webserver.safe_price(contract_name, self.safe_price)
        safe_price_forwarder.send_json({'safe_price': {contract_name: self.safe_price}})

class Order(object):
    """
    represents the order object used by the matching engine
    not to be confused with the sqlAlchemy order object
    """

    def __repr__(self):
        return self.__dict__.__repr__()

    def __init__(self, username=None, contract=None, quantity=None, price=None, side=None, id=None):
        self.id = id
        self.username = username
        self.contract = contract
        self.quantity = quantity
        self.quantity_left = quantity
        self.price = price
        self.side = side
        self.timestamp = datetime.utcnow()

    def matchable(self, other_order):

        if self.side == other_order.side:
            return False
        if (self.price - other_order.price) * self.side > 0:
            return False
        return True



    def match(self, other_order, matching_price):
        """
        Matches an order with another order, this is the trickiest part of the matching engine
        as it deals with the database
        :param other_order:
        :param matching_price:
        """

        assert self.matchable(other_order)
        assert other_order.price == matching_price

        quantity = min(self.quantity_left, other_order.quantity_left)
        print "Order", self, "matched to", other_order

        self.quantity_left -= quantity
        other_order.quantity_left -= quantity

        assert self.quantity_left >= 0
        assert other_order.quantity_left >= 0

        #begin db code
        try:
            db_orders = [db_session.query(models.Order).filter_by(id=oid).one()
                         for oid in [self.id, other_order.id]]

            # Make sure our timestamps are what is in the DB
            self.timestamp = db_orders[0].timestamp
            other_order.timestamp = db_orders[1].timestamp

            for i in [0, 1]:
                db_orders[i].quantity_left -= quantity
                db_orders[i] = db_session.merge(db_orders[i])

            assert db_orders[0].quantity_left == self.quantity_left
            assert db_orders[1].quantity_left == other_order.quantity_left


            # case of futures
            # test if it's a future by looking if there are any futures contract that map to this contract
            # potentially inefficient, but premature optimization is never a good idea


            trade = models.Trade(db_orders[0], db_orders[1], matching_price, quantity)
            db_session.add(trade)

            #commit db
            db_session.commit()
            print "db committed."
            #end db code
        except Exception as e:
            db_session.rollback()
            logging.error("Exception when matching orders: %s" % e)

            # Revert the quantity changes
            self.quantity_left -= quantity
            other_order.quantity_left -= quantity

            raise e
        else:
            safe_price_publisher.onTrade({'price': matching_price, 'quantity': quantity})
            webserver.trade(
                contract_name,
                {'contract': contract_name,
                 'quantity': quantity,
                 'price': matching_price,
                 'timestamp': util.dt_to_timestamp(trade.timestamp)
                })

            # The accountant needs to post both sides of the transaction at once
            transaction = {
                    'aggressive_username': self.username,
                    'passive_username': other_order.username,
                    'contract': contract_name,
                    'quantity': quantity,
                    'price': matching_price,
                    'contract_type': db_orders[0].contract.contract_type,
                    'aggressive_order_id': self.id,
                    'passive_order_id': other_order.id,
                    'timestamp': util.dt_to_timestamp(trade.timestamp),
                    'side': OrderSide.name(self.side)
                }
            accountant.post_transaction(transaction)
            print 'to acct: ',str({'post_transaction': transaction})

            for o in [self, other_order]:
                # Send an order update
                order = {'contract': contract_name,
                         'id': o.id,
                         'quantity': o.quantity,
                         'quantity_left': o.quantity_left,
                         'price': o.price,
                         'side': OrderSide.name(o.side),
                         # TODO: is hardcoding 'False' in here correct?
                         'is_cancelled': False,
                         'timestamp': util.dt_to_timestamp(o.timestamp)
                }
                webserver.order(o.username, order)
                print 'to ws: ', str({'orders': [o.username, order]})


    def cancel(self):
        """
        cancels the order...
        """
        try:
            logging.info("order %d is now cancelled" % self.id)
            db_order = db_session.query(models.Order).filter_by(id=self.id).one()
            db_order.is_cancelled = True
            db_session.merge(db_order)
            db_session.commit()
        except Exception as e:
            db_session.rollback()
            logging.error("Exception when matching orders: %s" % e)
            raise e

    def better(self, price):
        return (self.price - price) * self.side <= 0


class OrderSide():
    BUY = -1
    SELL = 1

    @staticmethod
    def name(n):
        if n == -1:
            return "BUY"
        return "SELL"

class OrderStatus():
    ACCEPTED = 1
    REJECTED = 0


def update_best(side):
    """
    update the current best bid and ask
    :param side: 'ask' or 'bid'
    """
    if side == 'ask':
        if book[side]:
            best[side] = min(book[side].keys())
        else:
            best[side] = None
    else:
        if book[side]:
            best[side] = max(book[side].keys())
        else:
            best[side] = None


def publish_order_book():
    """
    publishes the order book to be consumed by the server
    and dispatched to connected clients
    """
    published_book = { 'contract': contract_name,
             'bids': [],
             'asks': []
    }
    for price in sorted(book['bid'].iterkeys()):
        published_book['bids'].append({'price': price,
                                        'quantity': sum([x.quantity_left for x in book['bid'][price]])
        })

    for price in sorted(book['ask'].iterkeys(), reverse=True):
        published_book['asks'].append({'price': price,
                                        'quantity': sum([x.quantity_left for x in book['ask'][price]])
        })

    webserver.book(contract_name, published_book)


def pretty_print_book():
    """
    returns a string that can be printed on the console
    to represent the state of the order book
    """
    return '***\n%s\n***' % '\n-----\n'.join(
        '\n'.join(
            str(level) + ":" + '+'.join(str(order.quantity_left) for order in book[side][level])
            for level in sorted(book[side], reverse=True))
        for side in ['ask', 'bid'])


class ReplaceMeWithARealEngine:
    @export
    def cancel_order(self, order_id):
        logging.info("this order is actually a cancellation!")

        if order_id in all_orders:
            o = all_orders[order_id]
            side = 'bid' if o.side == OrderSide.BUY else 'ask'
            book[side][o.price].remove(o)
            # if list is now empty, get rid of it!
            if not book[side][o.price]:
                del book[side][o.price]

            update_best(side)

            o.cancel()
            del all_orders[order_id]
            #publisher.send_json({'cancel': [o.user, {'order': o.id}]}) #
            #user.usernamechange o to order in the following:
            print 'o.id:  ', o.id
            print 'order.id:  ', order_id
            print [oxox.__dict__ for oxox in all_orders.values()]
            print 'o.id:  ', o.id
            print 'order.id:  ', order_id
            print 'test 2:  ',str({'cancel': [o.username, {'id': o.id, 'is_cancelled': True, 'contract': contract_name}]})
            webserver.order(o.username, {'id': o.id, 'is_cancelled': True, 'contract': contract_name})
        else:
            logging.info("the order cannot be cancelled, it's already outside the book")
            raise EngineException(0, "the order %d cannot be cancelled, it's already outside the book" % order_id)

        logging.info(pretty_print_book())
        publish_order_book()

        return None

    @export
    def place_order(self, obj):
        logging.info("received order, id=%d, order=%s" % (obj["id"], obj))

        order = Order(None, None, None, None, None, None)
        order.__dict__.update(obj)
        side = 'ask' if order.side == OrderSide.BUY else 'bid'
        other_side = 'bid' if order.side == OrderSide.BUY else 'ask'

        # while we can dig in the other side, do so and be executed
        while order.quantity_left > 0 and best[side] and order.better(best[side]):
            try:
                book_order_list = book[side][best[side]]
                for book_order in book_order_list:
                    order.match(book_order, book_order.price)
                    if book_order.quantity_left == 0:
                        book_order_list.remove(book_order)
                        del all_orders[book_order.id]
                        if not book_order_list:
                            del book[side][best[side]]
                    if order.quantity_left == 0:
                        break
                update_best(side)
            except KeyError as e:
                print e

        # if some quantity remains place it in the book
        if order.quantity_left != 0:
            if order.price not in book[other_side]:
                book[other_side][order.price] = []
            book[other_side][order.price].append(order)
            all_orders[order.id] = order
            update_best(other_side)
            # publish the user's open order to their personal channel
            order_msg = {'id': order.id,
                         'quantity': order.quantity,
                         'quantity_left': order.quantity_left,
                         'price': order.price,
                         'side': OrderSide.name(order.side),
                         'contract': contract_name,
                         # TODO: is hardcoding 'False' in here correct?
                         'is_cancelled': False,
                         'timestamp': util.dt_to_timestamp(order.timestamp)
            }
            webserver.order(
                order.username,
                order_msg
                )
            print 'place_order:  ', str({'order': [order.username, order_msg]})

        # done placing the order, publish the order book
        logging.info(pretty_print_book())
        publish_order_book()
        return order.id


if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s', level=logging.DEBUG)
    db_session = db.make_session()

    context = zmq.Context()

    # yuck
    contract_name = args[0]

    print 'contract name:   ',contract_name

    contract_id = db_session.query(models.Contract).filter_by(ticker=contract_name).one().id

    # set the port based on the contract id
    CONNECTOR_PORT = config.getint("engine", "base_port") + contract_id

    # will automatically pull order from requests
    #connector = context.socket(zmq.PULL)
    #connector.bind('tcp://127.0.0.1:%d' % CONNECTOR_PORT)

    # publishes book updates
    webserver = push_proxy_sync(config.get("webserver", "engine_export"))

    # push to the accountant
    accountant = push_proxy_sync(config.get("accountant", "engine_export"))

    # push to the safe price forwarder
    safe_price_forwarder = context.socket(zmq.PUB)
    safe_price_forwarder.connect(config.get("safe_price_forwarder", "zmq_frontend_address"))

    all_orders = {}
    book = {'bid': {}, 'ask': {}}
    best = {'bid': None, 'ask': None}

    # first cancel all old pending orders
    for order in db_session.query(models.Order).filter_by(contract_id=contract_id).filter_by(
            is_cancelled=False).filter(models.Order.quantity_left > 0):
        order.is_cancelled = True
        db_session.merge(order)
        # Tell the users that their order has been cancelled
        webserver.order(order.username, {'id': order.id, 'is_cancelled': True, 'contract': contract_name})

    db_session.commit()


    safe_price_publisher = SafePricePublisher()

    engine = ReplaceMeWithARealEngine()
    router_share_sync(engine, "tcp://127.0.0.1:%d" % CONNECTOR_PORT)

