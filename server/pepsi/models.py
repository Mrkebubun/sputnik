from sqlalchemy.orm import relationship
from sqlalchemy.schema import ForeignKey
from sqlalchemy.types import Enum, DateTime
import database as db
from datetime import datetime

__author__ = 'satosushi'
from sqlalchemy import Column, Integer, String, BigInteger, schema, Boolean


class Contract(db.Base):
    __table_args__ = (schema.UniqueConstraint('ticker'), {'extend_existing': True})
    __tablename__ = 'contracts'

    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False)
    description = Column(String)
    full_description = Column(String)
    active = Column(Boolean, nullable=False, server_default="true")
    contract_type = Column(Enum('futures', 'prediction', 'cash', name='contract_types'), nullable=False)
    tick_size = Column(Integer, nullable=False, server_default="1")
    image_url = Column(String)
    denominator = Column(BigInteger, server_default="1", nullable=False)

    def __repr__(self):
        return "<Contract('%s')>" % self.ticker

    def __init__(self, ticker, description, full_description, contract_type, active=True):
        self.ticker, self.description, self.full_description = ticker, description, full_description
        self.contract_type, self.active = contract_type, active

class FuturesContract(db.Base):
    __table_args__ = {'extend_existing': True}
    __tablename__ = 'futures'

    id = Column(Integer, ForeignKey('contracts.id'), primary_key=True)
    contract = relationship('Contract')

    multiplier = Column(BigInteger, server_default="1")
    open_interest = Column(Integer, server_default="0")
    margin_high = Column(Integer)
    margin_low = Column(Integer)
    last_settlement = Column(Integer)
    expiration = Column(DateTime)

    def __init__(self, contract, margin_high, margin_low):
        self.contract = contract
        self.margin_high = margin_high
        self.margin_low = margin_low
        self.multiplier = contract.denominator

class PredictionContract(db.Base):
    __table_args__ = {'extend_existing': True}
    __tablename__ = 'predictions'

    id = Column(Integer, ForeignKey('contracts.id'), primary_key=True)
    final_payoff = Column(Integer)
    contract = relationship('Contract')

    def __init__(self, contract):
        self.contract = contract
        self.final_payoff = contract.denominator

    def __repr__(self):
        print "<PredictionContract(%s,%d)>" % (self.contract, self.final_payoff)

class Order(db.Base):
    __table_args__ = {'extend_existing': True}
    __tablename__ = 'orders'

    ORDER_ACCEPTED = 0
    ORDER_REJECTED = -1

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship('User')
    contract_id = Column(Integer, ForeignKey('contracts.id'))
    contract = relationship('Contract')
    quantity = Column(Integer)
    quantity_left = Column(Integer)
    price = Column(BigInteger, nullable=False)
    side = Column(Enum('BUY', 'SELL', name='side_types'))
    is_cancelled = Column(Boolean, nullable=False)
    accepted = Column(Boolean, nullable=False, server_default='false')
    timestamp = Column(DateTime)

    def to_matching_engine_order(self):
        return {'order_id': self.id, 'user': self.user_id, 'contract': self.contract_id, 'quantity': self.quantity,
                'price': self.price, 'order_side': (0 if self.side == "BUY" else 1), 'is_a_cancellation': False}


    def __init__(self, user, contract, quantity, price, side):
        self.user = user
        self.contract = contract
        self.quantity = quantity
        self.quantity_left = quantity
        self.price = price
        self.side = side
        self.timestamp = datetime.utcnow()
        self.is_cancelled = False

#class CancelOrder(db.Base):
#    __tablename__ = 'cancel_order'
#
#    id = Column(Integer, primary_key=True, ForeignKey('orders.id'))
#    order = relationship('Order')
#
#    def __init_ _(self, order):
#        self.order = order

class User(db.Base):
    __tablename__ = 'users'
    __table_args__ = ({'extend_existing': True},)

    id = Column(Integer, primary_key=True)
    password_hash = Column(String, nullable=False)
    salt = Column(String)
    nickname = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True)
    bitmessage = Column(String, unique=True)
    jabber = Column(String, unique=True)
    margin = Column(BigInteger, default=0)
    #login_allowed = Column(Boolean, server_default="false", nullable=False)


    def __init__(self, password_hash, salt, nickname, email, bitmessage):
        self.password_hash = password_hash
        self.salt = salt
        self.nickname = nickname
        self.email = email
        self.bitmessage = bitmessage
        self.margin = 0

    def __repr__(self):
        return "<User('%s','%s','%s')>" \
               % (self.nickname, self.email, self.bitmessage)


class Addresses(db.Base):
    """
    Currency addresses for users, and how much has been accounted for
    """
    __tablename__ = 'addresses'

    __table_args__ = (schema.UniqueConstraint('address'),
                      {'extend_existing': True})

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship('User')
    currency = Column(Enum('btc', 'ltc', 'xrp', 'usd', name='currency_types'), nullable=False)
    address = Column(String, nullable=False)
    active = Column(Boolean, nullable=False, server_default='false')
    accounted_for = Column(BigInteger, server_default='0', nullable=False)

    def __init__(self, user, currency, address):
        self.user, self.currency, self.address = user, currency, address

    def __repr__(self):
        return "<Wallet('%s','%s', %s>" \
               % (self.user.__repr__(), self.currency.__repr__(), self.address)

class Position(db.Base):
    __tablename__ = 'positions'

    __table_args__ = (schema.UniqueConstraint('user_id', 'contract_id'),
                      {'extend_existing': True})

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship('User')
    contract_id = Column(Integer, ForeignKey('contracts.id'))
    contract = relationship('Contract')
    position = Column(BigInteger)
    reference_price = Column(BigInteger, nullable=False, server_default="0")

    def __init__(self, user, contract, position=0):
        self.user, self.contract = user, contract
        self.position = position

    def __repr__(self):
        return "<Position('%s','%s',%d>" \
               % (self.contract.__repr__(), self.user.__repr__(), self.position)


class Withdrawal(db.Base):
    __tablename__ = 'withdrawals'
    __table_args__ = ({'extend_existing': True},)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship('User')
    address = Column(String, nullable=False)
    currency_id = Column(Integer, ForeignKey('contracts.id'))
    currency = relationship('Contract')
    amount = Column(BigInteger)
    pending = Column(Boolean, nullable=False, server_default='true')
    entered = Column(DateTime, nullable=False)
    completed = Column(DateTime)

    def __init__(self, user, currency, address, amount):
        self.user, self.currency, self.address, self.amount = user, currency, address, amount
        self.entered = datetime.utcnow()

    def __repr__(self):
        return "<Withdrawal('%s','%s','%s',%d>" \
               % (self.currency.__repr__(), self.user.__repr__(), self.address, self.amount)

class Trade(db.Base):
    __table_args__ = {'extend_existing': True}
    __tablename__ = 'trades'

    id = Column(Integer, primary_key=True)

    quantity = Column(Integer)
    price = Column(BigInteger, nullable=False)
    timestamp = Column(DateTime)

    contract_id = Column(Integer, ForeignKey('contracts.id'))
    contract = relationship('Contract')

    aggressive_order_id = Column(Integer, ForeignKey('orders.id'))
    passive_order_id = Column(Integer, ForeignKey('orders.id'))
    aggressive_order = relationship('Order', primaryjoin="Order.id==Trade.aggressive_order_id")
    passive_order = relationship('Order', primaryjoin="Order.id==Trade.passive_order_id")

    def __init__(self, aggressive_order, passive_order, price, quantity):
        self.contract_id = aggressive_order.contract_id
        self.aggressive_order = aggressive_order
        self.passive_order = passive_order
        self.timestamp = max(aggressive_order.timestamp, passive_order.timestamp)
        self.price = price
        self.quantity = quantity

    def __repr__(self):
        return '<Trade(%s:%d@%d>' % (self.contract.ticker, self.price, self.quantity)

if __name__ == '__main__':
    db.Base.metadata.create_all(db.engine)
