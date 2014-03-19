from sqlalchemy.orm import relationship
from sqlalchemy.schema import ForeignKey
from sqlalchemy.types import Enum, DateTime
import database as db
from datetime import datetime, date

__author__ = 'satosushi'
from sqlalchemy import Column, Integer, String, BigInteger, schema, Boolean, sql
import util
import hashlib
import base64
import collections

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

    margin_high = Column(BigInteger)
    margin_low = Column(BigInteger)

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

    aggressive_trades = relationship('Trade', primaryjoin="Order.id==Trade.aggressive_order_id")
    passive_trades = relationship('Trade', primaryjoin="Order.id==Trade.passive_order_id")

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
    default_position_type = Column(Enum('Liability', 'Asset', name='position_types'), nullable=False,
                                   default='Liability')

    positions = relationship("Position", back_populates="user")
    orders = relationship("Order", back_populates="user")
    addresses = relationship("Addresses", back_populates="user")
    withdrawals = relationship("Withdrawal", back_populates="user")

    @property
    def user_hash(self):
        combined_string = "%s:%s:%s:%d" % (self.username, self.nickname, self.email,
                                           util.dt_to_timestamp(datetime.combine(date.today(),
                                                                                 datetime.min.time())))

        user_hash = base64.b64encode(hashlib.md5(combined_string).digest())
        return user_hash

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

class Journal(db.Base):
    __tablename__ = 'journal'
    __table_args__ = {'extend_existing': True, 'sqlite_autoincrement': True}

    id = Column(Integer, primary_key=True)
    type = Column(String, Enum('Deposit', 'Withdrawal', 'Transfer', 'Adjustment',
                               'Trade', 'Fee',
                               name='journal_types'), nullable=False)
    timestamp = Column(DateTime)
    notes = Column(String)
    postings = relationship('Posting', back_populates="journal")

    def __init__(self, type, timestamp=datetime.utcnow(), notes=None):
        self.type = type
        self.timestamp = timestamp
        self.notes = None

    def __repr__(self):
        header = "<Journal('%s', '%s', '%s')>\n" % (self.type, self.timestamp, self.notes)
        postings = ""
        for posting in self.postings:
            postings += "\t%s\n" % posting
        footer = "</Journal>"
        return header + postings + footer

    def audit(self):
        """Make sure that every position's postings sum to 0
        """
        sums = collections.defaultdict(int)
        for posting in self.postings:
            ticker = posting.position.contract.ticker
            sums[ticker] += posting.quantity

        for ticker, sum in sums:
            assert(sum == 0)

class Posting(db.Base):
    __tablename__ = 'posting'
    __table_args__ = {'extend_existing': True, 'sqlite_autoincrement': True}

    id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey('journal.id'))
    journal = relationship('Journal')
    position_id = Column(Integer, ForeignKey('positions.id'))
    position = relationship('Position', back_populates="postings")
    quantity = Column(BigInteger)

    def __repr__(self):
        return "<Posting('%s', %d))>" % (self.position, self.quantity)

    def __init__(self, journal, position, quantity, side):
        self.journal = journal
        self.position = position
        if side is 'debit':
            if self.position.position_type == 'Asset':
                sign = 1
            else:
                sign = -1
        else:
            if self.position.position_type == 'Asset':
                sign = -1
            else:
                sign = 1

        self.quantity = sign * quantity
        self.position.position += sign * quantity

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
    # TODO: Make this a foreign key
    currency = Column(Enum('btc', 'ltc', 'xrp', 'usd', 'mxn', name='currency_types'), nullable=False)
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

    __table_args__ = (schema.UniqueConstraint('username', 'contract_id',
                                              'description'),
            {'extend_existing': True, 'sqlite_autoincrement': True})

    id = Column(Integer, primary_key=True)
    username = Column(String, ForeignKey('users.username'))
    user = relationship('User', back_populates="positions")
    contract_id = Column(Integer, ForeignKey('contracts.id'))
    contract = relationship('Contract')
    position = Column(BigInteger)
    reference_price = Column(BigInteger, nullable=False, server_default="0")
    position_type = Column(Enum('Liability', 'Asset', name='position_types'), nullable=False, default='Liability')
    description = Column(String, default='User')
    postings = relationship("Posting", back_populates="position")

    def __init__(self, user, contract, position=0, description='User'):
        self.user, self.contract = user, contract
        self.position = position
        self.description = description
        self.position_type = self.user.default_position_type

    def audit(self):
        """Make sure that the sum of all postings for this position sum to the position
        """
        sum = sum([x.quantity for x in self.postings])
        assert(sum == self.position)

    def __repr__(self):
        return "<Position('%s', '%s', '%s','%s',%d>" \
               % (self.position_type, self.description, self.contract.__repr__(), self.user.__repr__(), self.position)


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

