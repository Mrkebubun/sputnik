
__author__ = 'satosushi'

from sqlalchemy.orm import relationship
from sqlalchemy.schema import ForeignKey
from sqlalchemy.types import Enum, DateTime
import database as db
from datetime import datetime, date, timedelta
from sqlalchemy import Column, Integer, String, BigInteger, schema, Boolean, sql
import util
import hashlib
import base64
import collections
from Crypto.Random.random import getrandbits

class QuantityUI(object):
    @property
    def quantity_ui(self):
        return util.quantity_from_wire(self.contract, self.quantity)

    @property
    def quantity_fmt(self):
        return util.quantity_fmt(self.contract, self.quantity)

    @property
    def quantity_left_ui(self):
        return util.quantity_from_wire(self.contract, self.quantity_left)

    @property
    def quantity_left_fmt(self):
        return util.quantity_fmt(self.contract, self.quantity_left)

class PriceUI(object):
    @property
    def price_ui(self):
        return util.price_from_wire(self.contract, self.price)

    @property
    def price_fmt(self):
        return util.price_fmt(self.contract, self.price)

class ResetToken(db.Base):
    __table_args__ = {'extend_existing': True, 'sqlite_autoincrement': True}
    __tablename__ = 'reset_tokens'

    id = Column(Integer, primary_key=True)
    username = Column(String, ForeignKey('users.username'))
    user = relationship('User')
    token = Column(String)
    expiration = Column(DateTime)
    used = Column(Boolean)

    def __init__(self, username, hours_to_expiry=2):
        """

        :param username:
        :type username: str
        :param hours_to_expiry:
        :type hours_to_expiry: int
        """
        self.username = username
        self.expiration = datetime.utcnow() + timedelta(hours=hours_to_expiry)
        self.token = base64.urlsafe_b64encode(("%032X" % getrandbits(128)).decode("hex"))
        self.used = False

    def __repr__(self):
        return "<ResetToken('%s', '%s', '%s', used=%d)>" % \
               (self.username, self.token, self.expiration, self.used)

class FeeGroup(db.Base):
    __table_args__ = {'extend_existing': True, 'sqlite_autoincrement': True}
    __tablename__ = 'fee_groups'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    aggressive_factor = Column(Integer, server_default="100", nullable=False)
    passive_factor = Column(Integer, server_default="100", nullable=False)

    def __init__(self, name, aggressive_factor, passive_factor):
        self.name = name
        self.aggressive_factor = aggressive_factor
        self.passive_factor = passive_factor

    def __repr__(self):
        return "<FeeGroup('%s', %d, %d)>" % (self.name, self.aggressive_factor, self.passive_factor)

class Contract(db.Base):
    __table_args__ = (schema.UniqueConstraint('ticker'), {'extend_existing': True, 'sqlite_autoincrement': True})
    __tablename__ = 'contracts'

    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False, unique=True)
    description = Column(String)
    full_description = Column(String)
    active = Column(Boolean, nullable=False, server_default=sql.true())
    contract_type = Column(Enum('futures', 'prediction', 'cash', 'cash_pair', name='contract_types'), nullable=False)
    tick_size = Column(BigInteger, nullable=False, server_default="1")
    lot_size = Column(BigInteger, nullable=False, server_default="1")
    denominator = Column(BigInteger, server_default="1", nullable=False)
    expiration = Column(DateTime)
    #expired = Column(Boolean, server_default=sql.false())
    # Fees in bps
    fees = Column(BigInteger, server_default="100", nullable=False)

    denominated_contract_ticker = Column(String, ForeignKey('contracts.ticker'))
    denominated_contract = relationship('Contract', remote_side='Contract.ticker',
                                        primaryjoin='contracts.c.denominated_contract_ticker==contracts.c.ticker')

    # If the contract pays out something other than the denominated contract
    # Only used for cash_pair contracts
    payout_contract_ticker = Column(String, ForeignKey('contracts.ticker'))
    payout_contract = relationship('Contract', remote_side='Contract.ticker',
                               primaryjoin='contracts.c.payout_contract_ticker==contracts.c.ticker')

    margin_high = Column(BigInteger)
    margin_low = Column(BigInteger)

    hot_wallet_limit = Column(BigInteger)
    cold_wallet_address = Column(String)

    deposit_instructions = Column(String, server_default="Please send your crypto-currency to this address")

    @property
    def expired(self):
        if self.expiration is None:
            return False
        elif self.expiration < datetime.utcnow():
            return True

    def __repr__(self):
        return "<Contract('%s')>" % self.ticker

    def __init__(self, ticker, description="", full_description="", tick_size=1, lot_size=1, denominator=1, contract_type="cash", active=True):
        """

        :param ticker:
        :type ticker: str
        :param description:
        :type description: str
        :param full_description:
        :type full_description: str
        :param tick_size:
        :type tick_size: int
        :param lot_size:
        :type lot_size: int
        :param denominator:
        :type denominator: int
        :param contract_type:
        :type contract_type: str
        :param active:
        :type active: bool
        """
        self.ticker, self.description, self.full_description = ticker, description, full_description
        self.tick_size, self.lot_size, self.denominator = tick_size, lot_size, denominator
        self.contract_type, self.active = contract_type, active

class Order(db.Base, QuantityUI, PriceUI):
    __table_args__ = {'extend_existing': True, 'sqlite_autoincrement': True}
    __tablename__ = 'orders'

    ORDER_ACCEPTED = 0
    ORDER_REJECTED = -1

    id = Column(Integer, primary_key=True)
    username = Column(String, ForeignKey('users.username'), index=True)
    user = relationship('User')
    contract_id = Column(Integer, ForeignKey('contracts.id'), index=True)
    contract = relationship('Contract')
    quantity = Column(BigInteger)
    quantity_left = Column(BigInteger)
    price = Column(BigInteger, nullable=False)
    side = Column(Enum('BUY', 'SELL', name='side_types'))
    is_cancelled = Column(Boolean, nullable=False)
    accepted = Column(Boolean, nullable=False, server_default=sql.false())
    dispatched = Column(Boolean, nullable=False, server_default=sql.false())
    timestamp = Column(DateTime, index=True)

    aggressive_trades = relationship('Trade', primaryjoin="Order.id==Trade.aggressive_order_id")
    passive_trades = relationship('Trade', primaryjoin="Order.id==Trade.passive_order_id")


    def to_webserver(self):
        return {"id": self.id,
                "contract": self.contract.ticker,
                "quantity": self.quantity,
                "quantity_left": self.quantity_left,
                "price": self.price,
                "side": self.side,
                "is_cancelled": self.is_cancelled,
                "timestamp": util.dt_to_timestamp(self.timestamp)
        }

    def to_matching_engine_order(self):
        """


        :returns: dict
        """
        return {'id': self.id, 'username': self.username, 'contract': self.contract_id, 'quantity': self.quantity,
                'timestamp': util.dt_to_timestamp(self.timestamp),
                'price': self.price, 'side': (-1 if self.side == "BUY" else 1)}


    def __init__(self, user, contract, quantity, price, side, timestamp=None):
        """

        :param user:
        :type user: User
        :param contract:
        :type contract: Contract
        :param quantity:
        :type quantity: int
        :param price:
        :type price: int
        :param side:
        :type side: str
        """
        self.user = user
        self.contract = contract
        self.quantity = quantity
        self.quantity_left = quantity
        self.price = price
        self.side = side
        if timestamp is not None:
            self.timestamp = timestamp
        else:
            self.timestamp = datetime.utcnow()

        self.is_cancelled = False

    def __repr__(self):
        return "<Order('%s', '%s', %d, %d, '%s')>" % \
               (self.user, self.contract, self.quantity, self.price, self.side)

class SupportTicket(db.Base):
    __tablename__ = 'support_tickets'
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True)
    nonce = Column(String, unique=True)
    foreign_key = Column(String, unique=True)
    username = Column(String, ForeignKey('users.username'))
    user = relationship('User', back_populates='support_tickets')
    type = Column(Enum('Compliance', name='ticket_types'))

    @property
    def closed(self):
        # TODO: Check support system and see if it is closed or not
        return False

    def __init__(self, username, type):
        """

        :param username:
        :type username: str
        :param type:
        :type type: str
        """
        self.nonce = base64.b64encode(("%032X" % getrandbits(128)).decode("hex"))
        self.username = username
        self.type = type

    def __repr__(self):
        return "<SupportTicket('%s', '%s', '%s', '%s')>" % \
               (self.username, self.foreign_key, self.type, self.nonce)

class PermissionGroup(db.Base):
    __tablename__ = 'permission_groups'
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    trade = Column(Boolean, server_default=sql.false())
    deposit = Column(Boolean, server_default=sql.false())
    withdraw = Column(Boolean, server_default=sql.false())
    login = Column(Boolean, server_default=sql.true())

    def __init__(self, name, permissions):
        """

        :param name:
        :type name: str
        """
        self.name = name
        self.trade = 'trade' in permissions
        self.withdraw = 'withdraw' in permissions
        self.deposit = 'deposit' in permissions
        self.login = 'login' in permissions

    @property
    def dict(self):
        return {'name': self.name,
                'trade': self.trade,
                'deposit': self.deposit,
                'withdraw': self.withdraw,
                'login': self.login
        }

    def __repr__(self):
        return "<PermissionGroup('%s')>" % self.dict

class AdminUser(db.Base):
    __tablename__ = 'admin_users'
    __table_args__ = {'extend_existing': True}

    username = Column(String, primary_key=True)
    password_hash = Column(String, nullable=False)
    totp = Column(String)
    level = Column(Integer, server_default="0")

    def __init__(self, username, password_hash, level):
        """

        :param username:
        :type username: str
        :param password_hash:
        :type password_hash: str
        :param level:
        :type level: int
        """
        self.username = username
        self.password_hash = password_hash
        self.level = level

    def __repr__(self):
        return "<AdminUser('%s', %d)>" % (self.username, self.level)

class User(db.Base):
    __tablename__ = 'users'
    __table_args__ = {'extend_existing': True}

    username = Column(String, primary_key=True)
    password = Column(String, nullable=False)
    totp = Column(String)
    nickname = Column(String)
    email = Column(String)
    active = Column(Boolean, server_default=sql.true())
    permission_group_id = Column(Integer, ForeignKey('permission_groups.id'), server_default="1")
    fee_group_id = Column(Integer, ForeignKey('fee_groups.id'), server_default="1")
    type = Column(Enum('Liability', 'Asset', name='position_types'), nullable=False,
                                   default='Liability', server_default="Liability")
    audit_secret = Column(String)

    positions = relationship("Position", back_populates="user")
    orders = relationship("Order", back_populates="user")
    addresses = relationship("Addresses", back_populates="user")
    withdrawals = relationship("Withdrawal", back_populates="user")
    support_tickets = relationship("SupportTicket", back_populates="user")
    permissions = relationship("PermissionGroup")
    fees = relationship("FeeGroup")
    postings = relationship("Posting", back_populates="user")

    def user_hash(self, timestamp):
        """


        :returns: str
        """
        combined_string = "%s:%s:%s:%s:%d" % (self.audit_secret, self.username, self.nickname, self.email,
                                              timestamp)

        user_hash = base64.b64encode(hashlib.md5(combined_string).digest())
        return user_hash

    def __init__(self, username, password, email="", nickname="anonymous"):
        """

        :param username:
        :type username: str
        :param password:
        :type password: str
        :param email:
        :type email: str
        :param nickname:
        :type nickname: str
        """
        self.username = username
        self.password = password
        self.email = email
        self.nickname = nickname
        self.audit_secret = base64.b64encode(("%064X" % getrandbits(256)).decode("hex"))

    def __repr__(self):
        return "<User('%s', '%s', '%s')>" \
                % (self.username, self.email, self.nickname)

    def to_obj(self):
        """


        :returns: dict
        """
        return {"username": self.username, "password": self.password,
                "email": self.email, "nickname":self.nickname}

class Journal(db.Base):
    __tablename__ = 'journal'
    __table_args__ = {'extend_existing': True, 'sqlite_autoincrement': True}

    id = Column(Integer, primary_key=True)
    type = Column(Enum('Deposit', 'Withdrawal', 'Transfer', 'Adjustment',
                        'Trade', 'Fee', 'Clearing',
                        name='journal_types'), nullable=False)
    timestamp = Column(DateTime, index=True)
    postings = relationship('Posting', back_populates="journal")

    def __init__(self, type, postings, timestamp=None):
        """

        :param type:
        :type type: str
        :param postings:
        :type postings: list - list of Posting
        :param timestamp:
        :type timestamp: int
        :param notes:
        :type notes: str
        :raises: Exception
        """
        self.type = type
        self.postings = [p for p in postings]
        if timestamp is None:
            self.timestamp = datetime.utcnow()
        else:
            self.timestamp = timestamp

    def __repr__(self):
        header = "<Journal('%s', '%s', '%s')>\n" % (self.type, self.timestamp, self.notes)
        postings = ""
        for posting in self.postings:
            postings += "\t%s\n" % posting
        footer = "</Journal>"
        return header + postings + footer

    @property
    def notes(self):
        """Get all the notes for all the postings
        :returns: string
        """
        dedup_notes = set([posting.note for posting in self.postings if posting.note is not None])
        return '\n'.join(dedup_notes)

    @property
    def audit(self):
        """Make sure that every position's postings sum to 0
        :returns: bool
        """
        sums = collections.defaultdict(int)
        for posting in self.postings:
            ticker = posting.contract.ticker
            if posting.user.type == 'Asset':
                sign = 1
            else:
                sign = -1
            sums[ticker] += sign * posting.quantity

        for audited in sums.itervalues():
            if audited != 0:
                return False

        return True

class Posting(db.Base, QuantityUI):
    __tablename__ = 'posting'
    __table_args__ = {'extend_existing': True, 'sqlite_autoincrement': True}

    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey('contracts.id'), index=True)
    contract = relationship('Contract')
    journal_id = Column(Integer, ForeignKey('journal.id'), index=True)
    journal = relationship('Journal')
    username = Column(String, ForeignKey('users.username'), index=True)
    user = relationship('User', back_populates="postings")
    quantity = Column(BigInteger)
    note = Column(String)
    timestamp = Column(DateTime, index=True)

    def __repr__(self):
        return "<Posting('%s', '%s', %d, '%s')>" % (self.contract, self.user, self.quantity, self.note)

    def __init__(self, user, contract, quantity, direction, note=None, timestamp=None):
        """

        :param user:
        :type user: User
        :param contract:
        :type contract: Contract
        :param quantity:
        :type quantity: int
        :param side:
        :type side: str
        """
        self.user = user
        self.contract = contract
        if direction == 'debit':
            if self.user.type == 'Asset':
                sign = 1
            else:
                sign = -1
        else:
            if self.user.type == 'Asset':
                sign = -1
            else:
                sign = 1

        self.quantity = sign * quantity
        if timestamp is None:
            self.timestamp = datetime.utcnow()
        else:
            self.timestamp = timestamp
        self.note = note

class Addresses(db.Base, QuantityUI):
    """
    Currency addresses for users, and how much has been accounted for
    """
    __tablename__ = 'addresses'

    __table_args__ = (schema.UniqueConstraint('address'),
            {'extend_existing': True, 'sqlite_autoincrement': True})

    id = Column(Integer, primary_key=True)
    username = Column(String, ForeignKey('users.username'))
    user = relationship('User')

    contract_id = Column(Integer, ForeignKey('contracts.id'))
    contract = relationship('Contract')

    address = Column(String, nullable=False, index=True)
    active = Column(Boolean, nullable=False, server_default=sql.false())
    accounted_for = Column(BigInteger, server_default='0', nullable=False)

    @property
    def quantity(self):
        """Alias for the purpose of the UI functions


        :returns: int
        """
        return self.accounted_for

    @property
    def dict(self):
        return { 'id': self.id,
                 'username': self.username,
                 'contract': self.contract.ticker,
                 'address': self.address,
                 'active': self.active,
                 'accounted_for': self.quantity_fmt
                 }

    def __init__(self, user, contract, address):
        """

        :param user:
        :type user: User
        :param contract:
        :type contract:models.Contract
        :param address:
        :type address: str
        """
        self.user, self.contract, self.address = user, contract, address

    def __repr__(self):
        return "<Address('%s','%s', %s)>" \
               % (self.user, self.contract.ticker, self.address)

class Position(db.Base, QuantityUI):
    __tablename__ = 'positions'

    __table_args__ = (schema.UniqueConstraint('username', 'contract_id'),
            {'extend_existing': True, 'sqlite_autoincrement': True})

    id = Column(Integer, primary_key=True)
    username = Column(String, ForeignKey('users.username'))
    user = relationship('User', back_populates="positions")
    contract_id = Column(Integer, ForeignKey('contracts.id'))
    contract = relationship('Contract')
    position = Column(BigInteger)
    position_checkpoint = Column(BigInteger, server_default="0")
    position_cp_timestamp = Column(DateTime)
    reference_price = Column(BigInteger, nullable=False, server_default="0")
    pending_postings = Column(BigInteger, server_default="0", nullable="False")

    @property
    def quantity(self):
        """Alias for the purpose of the UI functions


        :returns: int
        """
        return self.position

    def __init__(self, user, contract, position=0):
        """

        :param user:
        :type user: User
        :param contract:
        :type contract: Contract
        :param position:
        :type position: int
        """
        self.user, self.contract = user, contract
        self.position = position
        self.pending_postings = 0

    def __repr__(self):
        return "<Position('%s', '%s', %d/%d)>" \
               % (self.contract, self.user,
                  self.position, self.position_checkpoint)


class Withdrawal(db.Base, QuantityUI):
    __tablename__ = 'withdrawals'
    __table_args__ = {'extend_existing': True, 'sqlite_autoincrement': True}

    id = Column(Integer, primary_key=True)
    username = Column(String, ForeignKey('users.username'))
    user = relationship('User')
    address = Column(String, nullable=False)
    contract_id = Column(Integer, ForeignKey('contracts.id'))
    contract = relationship('Contract')
    amount = Column(BigInteger)
    pending = Column(Boolean, nullable=False, server_default=sql.true())
    entered = Column(DateTime, nullable=False)
    completed = Column(DateTime)

    @property
    def dict(self):
        return {'id': self.id,
                'username': self.username,
                'address': self.address,
                'contract': self.contract.ticker,
                'amount': self.quantity_fmt,
                'entered': util.dt_to_timestamp(self.entered)}

    @property
    def quantity(self):
        """Alias for the purpose of the UI functions


        :returns: int
        """
        return self.amount

    def __init__(self, user, contract, address, amount):
        """

        :param user:
        :type user: User
        :param contract:
        :type contract: models.Contract
        :param address:
        :type address: str
        :param amount:
        :type amount: int
        """
        self.user, self.contract, self.address, self.amount = user, contract, address, amount
        self.entered = datetime.utcnow()

    def __repr__(self):
        return "<Withdrawal('%s','%s','%s',%d)>" \
               % (self.contract, self.user, self.address, self.amount)

class Trade(db.Base, QuantityUI, PriceUI):
    __table_args__ = {'extend_existing': True, 'sqlite_autoincrement': True}
    __tablename__ = 'trades'

    id = Column(Integer, primary_key=True)

    quantity = Column(BigInteger)
    price = Column(BigInteger, nullable=False)
    timestamp = Column(DateTime, index=True)

    contract_id = Column(Integer, ForeignKey('contracts.id'), index=True)
    contract = relationship('Contract')

    aggressive_order_id = Column(Integer, ForeignKey('orders.id'), index=True)
    passive_order_id = Column(Integer, ForeignKey('orders.id'), index=True)
    aggressive_order = relationship('Order', primaryjoin="Order.id==Trade.aggressive_order_id")
    passive_order = relationship('Order', primaryjoin="Order.id==Trade.passive_order_id")

    posted = Column(Boolean, server_default=sql.false())

    def __init__(self, aggressive_order, passive_order, price, quantity):
        """

        :param aggressive_order:
        :type aggressive_order: Order
        :param passive_order:
        :type passive_order: Order
        :param price:
        :type price: int
        :param quantity:
        :type quantity: int
        """
        self.contract_id = aggressive_order.contract_id
        self.aggressive_order = aggressive_order
        self.passive_order = passive_order
        self.timestamp = max(aggressive_order.timestamp, passive_order.timestamp)
        self.price = price
        self.quantity = quantity
        self.posted = False

    def __repr__(self):
        return '<Trade(%s:%d@%d)>' % (self.contract.ticker, self.price, self.quantity)

    def to_webserver(self):
        return {"contract": self.contract.ticker,
                "price": self.price,
                "quantity": self.quantity,
                "id": self.id,
                "timestamp": util.dt_to_timestamp(self.timestamp)
        }

