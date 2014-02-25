from sqlalchemy.orm import relationship
from sqlalchemy.schema import ForeignKey
from sqlalchemy.types import Enum, DateTime
import database as db
from datetime import datetime

__author__ = 'satosushi'
from sqlalchemy import Column, Integer, String, BigInteger, schema, Boolean, sql


class Contract(db.Base):
    __table_args__ = (schema.UniqueConstraint('ticker'), {'extend_existing': True, 'sqlite_autoincrement': True})
    __tablename__ = 'contracts'

    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False)
    description = Column(String)
    full_description = Column(String)
    active = Column(Boolean, nullable=False, server_default=sql.true())
    contract_type = Column(Enum('futures', 'prediction', 'cash', 'cash_pair', name='contract_types'), nullable=False)
    tick_size = Column(Integer, nullable=False, server_default="1")
    lot_size = Column(Integer, nullable=False, server_default="1")
    denominator = Column(BigInteger, server_default="1", nullable=False)
    expiration = Column(DateTime)
    inverse_quotes = Column(Boolean, server_default=sql.false(), nullable=False)

    margin_high = Column(Integer)
    margin_low = Column(Integer)

    def __repr__(self):
        return "<Contract('%s')>" % self.ticker

    def __init__(self, ticker, description="", full_description="", tick_size=1, lot_size=1, denominator=1, contract_type="cash", active=True):
        self.ticker, self.description, self.full_description = ticker, description, full_description
        self.tick_size, self.lot_size, self.denominator = tick_size, lot_size, denominator
        self.contract_type, self.active = contract_type, active

class Order(db.Base):
    __table_args__ = {'extend_existing': True, 'sqlite_autoincrement': True}
    __tablename__ = 'orders'

    ORDER_ACCEPTED = 0
    ORDER_REJECTED = -1

    id = Column(Integer, primary_key=True)
    username = Column(String, ForeignKey('users.username'))
    user = relationship('User')
    contract_id = Column(Integer, ForeignKey('contracts.id'))
    contract = relationship('Contract')
    quantity = Column(BigInteger)
    quantity_left = Column(BigInteger)
    price = Column(BigInteger, nullable=False)
    side = Column(Enum('BUY', 'SELL', name='side_types'))
    is_cancelled = Column(Boolean, nullable=False)
    accepted = Column(Boolean, nullable=False, server_default=sql.false())
    timestamp = Column(DateTime)

    def to_matching_engine_order(self):
        return {'id': self.id, 'username': self.username, 'contract': self.contract_id, 'quantity': self.quantity,
                'quantity_left': self.quantity_left,
                'price': self.price, 'side': (-1 if self.side == "BUY" else 1)}


    def __init__(self, user, contract, quantity, price, side):
        self.user = user
        self.contract = contract
        self.quantity = quantity
        self.quantity_left = quantity
        self.price = price
        self.side = side
        self.timestamp = datetime.utcnow()
        self.is_cancelled = False

class User(db.Base):
    __tablename__ = 'users'
    __table_args__ = {'extend_existing': True}

    username = Column(String, primary_key=True)
    password = Column(String, nullable=False)
    totp = Column(String)
    nickname = Column(String)
    email = Column(String)
    active = Column(Boolean, server_default=sql.true())

    positions = relationship("Position", back_populates="user")

    def __init__(self, username, password, email="", nickname="anonymous"):
        self.username = username
        self.password = password
        self.email = email
        self.nickname = nickname

    def __repr__(self):
        return "User('%s', '%s', '%s', '%s')" \
                % (self.username, self.password, self.email, self.nickname)

    def __str__(self):
        return "User('%s','%s')" % (self.username, self.email)

    def to_obj(self):
        return {"username": self.username, "password": self.password,
                "email": self.email, "nickname":self.nickname}


class Addresses(db.Base):
    """
    Currency addresses for users, and how much has been accounted for
    """
    __tablename__ = 'addresses'

    __table_args__ = (schema.UniqueConstraint('address'),
            {'extend_existing': True, 'sqlite_autoincrement': True})

    id = Column(Integer, primary_key=True)
    username = Column(String, ForeignKey('users.username'))
    user = relationship('User')
    currency = Column(Enum('btc', 'ltc', 'xrp', 'usd', name='currency_types'), nullable=False)
    address = Column(String, nullable=False)
    active = Column(Boolean, nullable=False, server_default=sql.false())
    accounted_for = Column(BigInteger, server_default='0', nullable=False)

    def __init__(self, user, currency, address):
        self.user, self.currency, self.address = user, currency, address

    def __repr__(self):
        return "<Wallet('%s','%s', %s>" \
               % (self.user.__repr__(), self.currency.__repr__(), self.address)

class Position(db.Base):
    __tablename__ = 'positions'

    __table_args__ = (schema.UniqueConstraint('username', 'contract_id'),
            {'extend_existing': True, 'sqlite_autoincrement': True})

    id = Column(Integer, primary_key=True)
    username = Column(String, ForeignKey('users.username'))
    user = relationship('User', back_populates="positions")
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
    __table_args__ = {'extend_existing': True, 'sqlite_autoincrement': True}

    id = Column(Integer, primary_key=True)
    username = Column(String, ForeignKey('users.username'))
    user = relationship('User')
    address = Column(String, nullable=False)
    currency_id = Column(Integer, ForeignKey('contracts.id'))
    currency = relationship('Contract')
    amount = Column(BigInteger)
    pending = Column(Boolean, nullable=False, server_default=sql.true())
    entered = Column(DateTime, nullable=False)
    completed = Column(DateTime)

    def __init__(self, user, currency, address, amount):
        self.user, self.currency, self.address, self.amount = user, currency, address, amount
        self.entered = datetime.utcnow()

    def __repr__(self):
        return "<Withdrawal('%s','%s','%s',%d>" \
               % (self.currency.__repr__(), self.user.__repr__(), self.address, self.amount)

class Trade(db.Base):
    __table_args__ = {'extend_existing': True, 'sqlite_autoincrement': True}
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

