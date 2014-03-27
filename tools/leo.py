#!/usr/bin/python

import os
import sys
import getpass

import string
import shlex
import textwrap
import autobahn.wamp1.protocol
import Crypto.Random.random

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
    "../server"))

from sputnik import config
from sputnik import database, models

class AdminManager:
    def __init__(self, session):
        self.session = session

    def add(self, username, password_hash="", level=5):
        user = self.session.query(models.AdminUser).filter_by(username=username).first()
        if user is not None:
            raise Exception("Admin user %s already exists" % username)
        else:
            user = models.AdminUser(username, password_hash, level)
            self.session.add(user)
            self.session.commit()

class AccountManager:
    def __init__(self, session):
        self.session = session

    def query(self, username):
        user = self.session.query(models.User).filter_by(
                username=username).first()
        if user == None:
            raise Exception("User '%s' not found." % username)
        print "Account: %s" % user.username
        print "\tPersonal Information:"
        print "\t\tnickname:\t%s" % user.nickname
        print "\t\temail:\t\t%s" % user.email
        print "\tCredentials:"
        print "\t\tpassword:\t%s" % user.password
        print "\t\ttotp:\t\t%s" % user.totp
        print "\t\tactive:\t\t%s" % user.active
        print "\t\tdefault_position_type:\t\t%s" % user.default_position_type
        print "\tPositions:"
        for position in user.positions:
            prefix = "%s(%s)-%s/%s:" % (position.contract.ticker,
                                        position.contract.id,
                                        position.position_type,
                                        position.description)
            print "\t\t%s\t%s" % (prefix.ljust(10), position.position)

    def add(self, username):
        user = models.User(username, "")
        self.session.add(user)

    def position(self, username, ticker_or_id):
        """Initialize a position to 0"""
        user = self.session.query(models.User).filter_by(
                username=username).first()
        if user == None:
            raise Exception("User '%s' not found." % username)
        contract = ContractManager.resolve(self.session, ticker_or_id)
        if contract == None:
            raise Exception("Contract '%s' not found." % ticker_or_id)
        position = self.session.query(models.Position).filter_by(
                user=user, contract=contract, description='User').first()
        if position == None:
            self.session.add(models.Position(user, contract, 0))
        else:
            raise Exception("Position %s/%s/%s already exists" % (user, contract, 'User'))


    def delete(self, username):
        user = self.session.query(models.User).filter_by(
                username=username).one()
        self.session.delete(user)

    def list(self):
        users = self.session.query(models.User).all()
        for user in users:
            print user

    def modify(self, username, field, value):
        user = self.session.query(models.User).filter_by(
                username=username).first()
        if user == None:
            raise Exception("User '%s' not found." % username)
        setattr(user, field, value)
        self.session.merge(user)

    def password(self, username, secret):
        alphabet = string.digits + string.lowercase
        num = Crypto.Random.random.getrandbits(64)
        salt = ""
        while num != 0:
            num, i = divmod(num, len(alphabet))
            salt = alphabet[i] + salt
        extra = {"salt":salt, "keylen":32, "iterations":1000}
        password = autobahn.wamp1.protocol.WampCraProtocol.deriveKey(secret, extra)
        self.modify(username, "password", "%s:%s" % (salt, password))

class ContractManager:
    def __init__(self, session):
        self.session = session

    @staticmethod
    def resolve(session, ticker_or_id):
        try:
            id = int(ticker_or_id)
            use_id = True
        except:
            ticker = ticker_or_id
            use_id = False
        if use_id:
            contract = session.query(models.Contract).filter_by(
                    id=id).first()
        else:
            contract = session.query(models.Contract).filter_by(
                ticker=ticker).order_by(models.Contract.id.desc()).first()
        return contract

    def query(self, ticker_or_id):
        contract = self.resolve(self.session, ticker_or_id)
        if contract == None:
            raise Exception("Contract '%s' not found." % ticker_or_id)
        print "Contract: %s(%s)" % (contract.ticker, contract.id)
        print "\tContract details:"
        print "\t\tcontract_type:\t%s" % contract.contract_type
        print "\t\tdescription:\t%s" % contract.description
        print "\t\tfull_description:"
        tw = textwrap.TextWrapper()
        tw.initial_indent = " " * 20
        tw.subsequent_indent = " " * 20
        for line in tw.wrap(contract.full_description):
            print line
        print "\t\tactive:\t\t%s" % contract.active
        print "\t\ttick_size:\t%s" % contract.tick_size
        print "\t\tlot_size:\t%s" % contract.lot_size
        print "\t\tdenominator:\t%s" % contract.denominator
        if contract.contract_type == "futures":
            print "\tFutures details:"
            print "\t\tmargin_high:\t%s" % contract.margin_high
            print "\t\tmargin_low:\t%s" % contract.margin_low
            print "\t\texpiration:\t%s" % contract.expiration
        elif contract.contract_type == "prediction":
            print "\tPrediction details:"
            print "\t\texpiration:\t%s" % contract.expiration

    def add(self, ticker):
        contract = models.Contract(ticker)
        self.session.add(contract)

    def list(self):
        contracts = self.session.query(models.Contract).all()
        for contract in contracts:
            print contract

    def modify(self, ticker_or_id, field, value):
        contract = self.resolve(self.session, ticker_or_id)
        if contract == None:
            raise Exception("Contract '%s' not found." % ticker_or_id)
        setattr(contract, field, value)
        self.session.merge(contract)

class AddressManager:
    def __init__(self, session):
        self.session = session

    def add(self, currency, address):
        address = models.Addresses(None, currency, address)
        self.session.add(address)

    def list(self, currency):
        addresses = self.session.query(models.Addresses).filter_by(
                currency=currency).all()
        for address in addresses:
            print address.address
       
    def query(self, currency, address):
        address = self.session.query(models.Addresses).filter_by(
                currency=currency, address=address).one()
        print "Address: %s" % address.address
        print "\tActive: %s" % address.active
        print "\tCurrency: %s" % address.currency
        if address.user != None:
            print "\tBelongs to: %s" % address.user.username
        print "\tAccounted for: %s" % address.accounted_for

class DatabaseManager:
    def __init__(self, session):
        self.session = session

    def init(self):
        database.Base.metadata.create_all(self.session.bind)

class LowEarthOrbit:
    def __init__(self, session):
        self.session = session
        self.modules = {
            "accounts": AccountManager(session),
            "contracts": ContractManager(session),
            "addresses": AddressManager(session),
            "database": DatabaseManager(session),
            "admin": AdminManager(session)
        }

    def parse(self, line):
        tokens = line.split()
        if len(tokens) == 0:
            return
        if len(tokens) < 2:
            raise Exception("Insufficient arguments.")
        (module, command), args = tokens[:2], tokens[2:]
        try:
            method = getattr(self.modules[module], command)
        except:
            raise Exception("Method %s.%s() not found." % (module, command))
        method(*args)

def main():
    session = database.make_session()
    try:
        leo = LowEarthOrbit(session)
        if len(sys.argv) == 1:
            try:
                while True:
                    leo.parse(raw_input("leo> "))
            except EOFError:
                pass
        else:
            leo.parse(" ".join(sys.argv[1:]))
        session.commit()
    except Exception, e:
        print e
        session.rollback()

if __name__ == "__main__":
    main()

