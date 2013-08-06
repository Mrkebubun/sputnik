from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy

from wtforms import validators

from flask.ext import admin
from flask.ext.admin.contrib import sqla
from flask.ext.admin.contrib.sqla import filters

from models import *

# Create application
app = Flask(__name__)

# Create dummy secrey key so we can use sessions
app.config['SECRET_KEY'] = '123456790'

# Create in-memory database
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://penny:arcade@localhost/test'
app.config['SQLALCHEMY_ECHO'] = True
db = SQLAlchemy(app)


# Create models
'''
class TradeInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    key = db.Column(db.String(64), nullable=False)
    value = db.Column(db.String(64))

    contract_id = db.Column(db.Integer(), db.ForeignKey(Trade.id))
    contract = db.relationship(Trade, backref='info')

    def __str__(self):
        return '%s - %s' % (self.key, self.value)

class OrderInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    key = db.Column(db.String(64), nullable=False)
    value = db.Column(db.String(64))

    contract_id = db.Column(db.Integer(), db.ForeignKey(Order.id))
    contract = db.relationship(Order, backref='info')

    user_id = db.Column(db.Integer(), db.ForeignKey(UserInfo.id))
    user = db.relationship(UserInfo, backref='info')

    def __str__(self):
        return '%s - %s' % (self.key, self.value)

class PositionInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    key = db.Column(db.String(64), nullable=False)
    value = db.Column(db.String(64))

    position_id = db.Column(db.Integer(), db.ForeignKey(Position.id))
    position = db.relationship(Position, backref='info')

    def __str__(self):
        return '%s - %s' % (self.key, self.value)
'''


class UserInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    key = db.Column(db.String(64), nullable=False)
    value = db.Column(db.String(64))

    user_id = db.Column(db.Integer(), db.ForeignKey(User.id))
    user = db.relationship(User, backref='info')

    def __str__(self):
        return '%s - %s' % (self.key, self.value)

class PredictionContractInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    key = db.Column(db.String(64), nullable=False)
    value = db.Column(db.String(64))

    contract_id = db.Column(db.Integer(), db.ForeignKey(PredictionContract.id))
    contract = db.relationship(PredictionContract, backref='info')

    def __str__(self):
        return '%s - %s' % (self.key, self.value)

class FuturesContractInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    key = db.Column(db.String(64), nullable=False)
    value = db.Column(db.String(64))

    contract_id = db.Column(db.Integer(), db.ForeignKey(FuturesContract.id))
    contract = db.relationship(FuturesContract, backref='info')

    def __str__(self):
        return '%s - %s' % (self.key, self.value)

class ContractInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    key = db.Column(db.String(64), nullable=False)
    value = db.Column(db.String(64))

    contract_id = db.Column(db.Integer(), db.ForeignKey(Contract.id))
    contract = db.relationship(Contract, backref='info')

    def __str__(self):
        return '%s - %s' % (self.key, self.value)


class AddressesInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    key = db.Column(db.String(64), nullable=False)
    value = db.Column(db.String(64))

    address_id = db.Column(db.Integer(), db.ForeignKey(Addresses.id))
    address = db.relationship(Addresses, backref='info')

    def __str__(self):
        return '%s - %s' % (self.key, self.value)

# Flask views
@app.route('/')
def index():
    return '<a href="/admin/">Click me to get to Admin!</a>'


# Customized User model admin
class UserAdmin(sqla.ModelView):
    inline_models = (UserInfo,)

class ContractAdmin(sqla.ModelView):
    inline_models = (ContractInfo,)

class FuturesContractAdmin(sqla.ModelView):
    inline_models = (FuturesContractInfo,)

class PredictionContractAdmin(sqla.ModelView):
    inline_models = (PredictionContractInfo,)

class AddressesAdmin(sqla.ModelView):
    inline_models = (AddressesInfo,)

'''
class PositionAdmin(sqla.ModelView):
    inline_models = (PositionInfo,)
'''

if __name__ == '__main__':
    # Create admin
    admin = admin.Admin(app, 'Arcade')

    # Add views
    admin.add_view(UserAdmin(User, db.session))
    admin.add_view(AddressesAdmin(Addresses, db.session))
    admin.add_view(ContractAdmin(Contract, db.session))
    admin.add_view(FuturesContractAdmin(FuturesContract, db.session))
    admin.add_view(PredictionContractAdmin(PredictionContract, db.session))
    #admin.add_view(PositionAdmin(Position, db.session))

    # Create DB
    db.create_all()

    # Start app
    app.run(host='0.0.0.0')
