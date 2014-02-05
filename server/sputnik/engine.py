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

import zmq
from zmq_util import export, router_share_sync, push_proxy_sync
import database as db
import models

db_session = db.make_session()

context = zmq.Context()


logging.basicConfig(level=logging.DEBUG)


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
        accountant.safe_price(contract_name, self.safe_price)
        publisher.send_json({'safe_price': {contract_name: self.safe_price}})
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
        publisher.send_json({'safe_price': {contract_name: self.safe_price}})
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
        self.price = price
        self.side = side



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

        qty = min(self.quantity, other_order.quantity)
        print "Order", self, "matched to", other_order

        self.quantity -= qty
        other_order.quantity -= qty

        assert self.quantity >= 0
        assert other_order.quantity >= 0

        #begin db code
        db_orders = [db_session.query(models.Order).filter_by(id=oid).one()
                     for oid in [self.id, other_order.id]]

        for i in [0, 1]:
            db_orders[i].quantity_left -= qty
            db_orders[i] = db_session.merge(db_orders[i])

        assert db_orders[0].quantity_left == self.quantity
        assert db_orders[1].quantity_left == other_order.quantity


        # case of futures
        # test if it's a future by looking if there are any futures contract that map to this contract
        # potentially inefficient, but premature optimization is never a good idea


        trade = models.Trade(db_orders[0], db_orders[1], matching_price, qty)
        db_session.add(trade)

        #commit db
        db_session.commit()
        print "db committed."
        #end db code

        safe_price_publisher.onTrade({'price': matching_price, 'quantity': qty})
        publisher.send_json({'trade': {'ticker': contract_name, 'quantity': qty, 'price': matching_price}})

        for o in [self, other_order]:
            signed_qty = -o.side * qty
            accountant.post_transaction(
                {
                    'username':o.username,
                    'contract': o.contract,
                    'signed_quantity': signed_qty,
                    'price': matching_price,
                    'contract_type': db_orders[0].contract.contract_type,
                    'ticker': contract_name,
                }
            )
            publisher.send_json({'fill': [o.username, {'order': o.id, 'quantity': qty, 'price': matching_price}]})
            print 'test 1:  ',str({'fill': [o.username, {'order': o.id, 'quantity': qty, 'price': matching_price}]})

    def cancel(self):
        """
        cancels the order...
        """
        logging.info("order %d is now cancelled" % self.id)
        db_order = db_session.query(models.Order).filter_by(id=self.id).one()
        db_order.is_cancelled = True
        db_session.merge(db_order)
        db_session.commit()

    def better(self, price):
        return (self.price - price) * self.side <= 0


class OrderSide():
    BUY = -1
    SELL = 1


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


# yuck
contract_name = args[0]

print 'contract name:   ',contract_name

contract_id = db_session.query(models.Contract).filter_by(ticker=contract_name).one().id

# set the port based on the contract id
CONNECTOR_PORT = config.getint("engine", "base_port") + contract_id


# first cancel all old pending orders
for order in db_session.query(models.Order).filter(models.Order.quantity_left > 0).filter_by(contract_id=contract_id):
    order.is_cancelled = True
    db_session.merge(order)
db_session.commit()



# will automatically pull order from requests
#connector = context.socket(zmq.PULL)
#connector.bind('tcp://127.0.0.1:%d' % CONNECTOR_PORT)

# publishes book updates
publisher = context.socket(zmq.PUSH)
publisher.connect(config.get("webserver", "zmq_address"))

# push to the accountant
accountant = push_proxy_sync(config.get("accountant", "engine_link"))

# push to the safe price forwarder
safe_price_forwarder = context.socket(zmq.PUB)
safe_price_forwarder.connect(config.get("safe_price_forwarder", "zmq_frontend_address"))

all_orders = {}
book = {'bid': {}, 'ask': {}}
best = {'bid': None, 'ask': None}


def publish_order_book():
    """
    publishes the order book to be consumed by the server
    and dispatched to connected clients
    """
    publisher.send_json({'book_update': {contract_name: [{"quantity": o.quantity, "price": o.price, "side": o.side} for o in all_orders.values()]}})


def pretty_print_book():
    """
    returns a string that can be printed on the console
    to represent the state of the order book
    """
    return '***\n%s\n***' % '\n-----\n'.join(
        '\n'.join(
            str(level) + ":" + '+'.join(str(order.quantity) for order in book[side][level])
            for level in sorted(book[side], reverse=True))
        for side in ['ask', 'bid'])


safe_price_publisher = SafePricePublisher()


class ReplaceMeWithARealEngine:
    @export
    def cancel_order(self, order_id):
        logging.info("this order is actually a cancellation!")

        if order_id in all_orders:
            o = all_orders[order_id]
            side = 'ask' if o.side == OrderSide.BUY else 'bid'
            other_side = 'bid' if o.side == OrderSide.BUY else 'ask'
            book['bid' if o.side == OrderSide.BUY else 'ask'][o.price].remove(o)
            # if list is now empty, get rid of it!
            if not book['bid' if o.side == OrderSide.BUY else 'ask'][o.price]:
                del book['bid' if o.side == OrderSide.BUY else 'ask'][o.price]

            update_best(other_side)

            o.cancel()
            del all_orders[order_id]
            #publisher.send_json({'cancel': [o.user, {'order': o.id}]}) #
            #user.usernamechange o to order in the following:
            print 'o.id:  ', o.id
            print 'order.id:  ', order_id
            print [oxox.__dict__ for oxox in all_orders.values()]
            print 'o.id:  ', o.id
            print 'order.id:  ', order_id
            print 'test 2:  ',str({'cancel': [o.username, {'order': o.id}]})
            publisher.send_json({'cancel': [o.username, {'order': o.id}]})
        else:
            logging.info("the order cannot be cancelled, it's already outside the book")
            return False

        logging.info(pretty_print_book())
        publish_order_book()

        return True

    @export
    def place_order(self, obj):
        logging.info("received order, id=%d, order=%s" % (obj["id"], obj))

        order = Order(None, None, None, None, None, None)
        order.__dict__.update(obj)
        side = 'ask' if order.side == OrderSide.BUY else 'bid'
        other_side = 'bid' if order.side == OrderSide.BUY else 'ask'

        # while we can dig in the other side, do so and be executed
        while order.quantity > 0 and best[side] and order.better(best[side]):
            try:
                book_order_list = book[side][best[side]]
                for book_order in book_order_list:
                    order.match(book_order, book_order.price)
                    if book_order.quantity == 0:
                        book_order_list.remove(book_order)
                        del all_orders[book_order.id]
                        if not book_order_list:
                            del book[side][best[side]]
                    if order.quantity == 0:
                        break
                update_best(side)
            except KeyError as e:
                print e

        # if some quantity remains place it in the book
        if order.quantity != 0:
            if order.price not in book[other_side]:
                book[other_side][order.price] = []
            book[other_side][order.price].append(order)
            all_orders[order.id] = order
            update_best(other_side)
            # publish the user's open order to their personal channel
            publisher.send_json({'open_orders': [order.username,{'order': order.id,
                                                             'quantity':order.quantity,
                                                             'price':order.price,
                                                             'side': order.side,
                                                             'ticker':contract_name,
                                                             'contract_id':contract_id}]})
            print 'test 3:  ',str({'open_orders': [order.username,{'order': order.id,
                                                             'quantity':order.quantity,
                                                             'price':order.price,
                                                             'side': order.side,
                                                             'ticker':contract_name,
                                                             'contract_id':contract_id}]})

        # done placing the order, publish the order book
        logging.info(pretty_print_book())
        publish_order_book()
        return True

engine = ReplaceMeWithARealEngine()
router_share_sync(engine, "tcp://127.0.0.1:%d" % CONNECTOR_PORT)

