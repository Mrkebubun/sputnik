import sys
import logging

import zmq
from sqlalchemy.orm.exc import NoResultFound
import database as db
import models

PUBLISHER_PORT = 6666

db_session = db.Session()

context = zmq.Context()

best = {'bid': None, 'ask': None}
book = {'bid': {}, 'ask': {}}

logging.basicConfig(level=logging.DEBUG)


class SafePricePublisher(object):
    # update exponential moving average volume weighted vwap
    # and push the price on a dedicated socket

    def __init__(self):

        self.ema_price_volume = 0
        self.ema_volume = 0
        self.decay = 0.9

    def onTrade(self, last_trade):
        '''
        calculate the ema by volume
        :param last_trade:
        '''

        self.ema_volume = self.decay * self.ema_volume + (1 - self.decay) * last_trade['quantity']
        self.ema_price_volume = self.decay * self.ema_price_volume + (1 - self.decay) * last_trade['quantity'] * last_trade['price']


        safe_price = self.ema_price_volume / self.ema_volume
        logging.info('Woo, new safe price %f' % safe_price)
        accountant.send_json({'safe_price': {contract_name: safe_price}})
        publisher.send_json({'safe_price': {contract_name: safe_price}})

class Order(object):
    """
    represents the order object used by the matching engine
    not to be confused with the sqlAlchemy order object
    """

    def __repr__(self):
        return self.__dict__.__repr__()

    def __init__(self, user, contract, quantity, price, order_side, order_id, is_a_cancellation=False):
        self.order_id = order_id
        self.user = user
        self.contract = contract
        self.quantity = quantity
        self.price = price
        self.order_side = order_side
        self.is_a_cancellation = is_a_cancellation

    def cancel(self):
        """
        cancels the order...
        """
        logging.info("order %d is now cancelled" % self.order_id)
        db_order = db_session.query(models.Order).filter_by(id=self.order_id).one()
        db_order.is_cancelled = True
        db_session.merge(db_order)
        db_session.commit()


    def matchable(self, other_order):

        if self.order_side == other_order.order_side:
            return False
        if (self.price - other_order.price) * (2 * self.order_side - 1) > 0:
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
        db_orders = [db_session.query(models.Order).filter_by(id=order_id).one()
                     for order_id in [self.order_id, other_order.order_id]]

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
        publisher.send_json({'trade': {'contract': self.contract, 'quantity': qty, 'price': matching_price}})

        for o in [self, other_order]:
            signed_qty = (1 - 2 * o.order_side) * qty
            accountant.send_json({
                'trade': {
                    'user': o.user,
                    'contract': o.contract,
                    'signed_qty': signed_qty,
                    'price': matching_price,
                    'contract_type': db_orders[0].contract.contract_type
                }
            })
            publisher.send_json({'fill': [o.user, {'order': o.order_id, 'quantity': qty, 'price': matching_price}]})

    def better(self, price):
        return (self.price - price) * (2 * self.order_side - 1) <= 0


class OrderSide():
    BUY = 0
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
contract_name = sys.argv[1]
contract_id = int(sys.argv[2])

# set the port based on the contract id
CONNECTOR_PORT = 4200 + contract_id
ACCOUNTANT_PORT = 3342



# first cancel all old pending orders
for order in db_session.query(models.Order).filter(models.Order.quantity_left > 0).filter_by(contract_id=contract_id):
    order.is_cancelled = True
    db_session.merge(order)
db_session.commit()



# will automatically pull order from requests
connector = context.socket(zmq.PULL)
connector.bind('tcp://127.0.0.1:%d' % CONNECTOR_PORT)

# publishes book updates
publisher = context.socket(zmq.PUSH)
publisher.connect('tcp://localhost:%d' % PUBLISHER_PORT)

# push to the accountant
accountant = context.socket(zmq.PUSH)
accountant.connect('tcp://localhost:%d' % ACCOUNTANT_PORT)

all_orders = {}


def publish_order_book():
    """
    publishes the order book to be consumed by the server
    and dispatched to connected clients
    """
    publisher.send_json({'book_update': {contract_name: [{"quantity": o.quantity, "price": o.price, "order_side": o.order_side} for o in all_orders.values()]}})


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

while True:
    order = Order(None, None, None, None, None, None)
    order.__dict__.update(connector.recv_json())
    logging.info("received order, id=%d, order=%s" % (order.order_id, order))

    side = 'ask' if order.order_side == OrderSide.BUY else 'bid'
    other_side = 'bid' if order.order_side == OrderSide.BUY else 'ask'

    #is it a cancel order?
    if order.is_a_cancellation:
        logging.info("this order is actually a cancellation!")

        if order.order_id in all_orders:
            o = all_orders[order.order_id]
            book['bid' if o.order_side == OrderSide.BUY else 'ask'][o.price].remove(o)
            # if list is now empty, get rid of it!
            if not book['bid' if o.order_side == OrderSide.BUY else 'ask'][o.price]:
                del book['bid' if o.order_side == OrderSide.BUY else 'ask'][o.price]

            update_best(other_side)
            
            o.cancel()
            del all_orders[order.order_id]

            #now publish new book and cancelled order (isn't 262 redundant with 269?)
            publisher.send_json({contract_name: [o.__dict__ for o in all_orders.values()]})
            #publisher.send_json({'cancel': [o.user, {'order': o.order_id}]}) #
            #change o to order in the following:
            publisher.send_json({'cancel': [order.user, {'order': order.order_id}]}) #
        else:
            logging.info("the order cannot be cancelled, it's already outside the book")
            logging.warning("we currently don't have a way of telling the cancel failed")

        logging.info(pretty_print_book())
        publish_order_book()
        continue

    # it's a regular order, carry on

    # while we can dig in the other side, do so and be executed
    while order.quantity > 0 and best[side] and order.better(best[side]):
        try:
            book_order_list = book[side][best[side]]
            for book_order in book_order_list:
                order.match(book_order, book_order.price)
                if book_order.quantity == 0:
                    book_order_list.remove(book_order)
                    del all_orders[book_order.order_id]
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
        all_orders[order.order_id] = order
        update_best(other_side)
        # publish the user's open order to their personal channel
        publisher.send_json({'open_orders': [order.user,{'order': order.order_id,
                                                         'quantity':order.quantity,
                                                         'price':order.price,
                                                         'side': order.order_side,
                                                         'ticker':contract_name,
                                                         'contract_id':contract_id}]}) 

    # done placing the order, publish the order book 
    logging.info(pretty_print_book())
    publish_order_book()









