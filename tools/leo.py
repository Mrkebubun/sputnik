#!/usr/bin/python

import os
import sys

import string
import textwrap
import autobahn.wamp1.protocol
import Crypto.Random.random

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
    "../server"))

from sputnik import config
from sputnik import database, models
from sqlalchemy.orm.exc import NoResultFound
from dateutil import parser
import shlex

class PermissionsManager:
    def __init__(self, session):
        self.session = session

    def add(self, name, *permissions):
        try:
            group = self.session.query(models.PermissionGroup).filter_by(name=name).one()
        except NoResultFound:
            permissions_dict = {}
            for permission in permissions:
                permissions_dict[permission] = True

            group = models.PermissionGroup(name, permissions_dict)
            self.session.add(group)
        else:
            print "PermissionGroup %s already exists" % group

    def set(self, name, field, value):
        group = self.session.query(models.PermissionGroup).filter_by(
                name=name).first()
        if group == None:
            raise Exception("Permission group '%s' not found." % name)
        setattr(group, field, value)

class FeesManager:
    def __init__(self, session):
        self.session = session

    def add(self, name, aggressive_factor, passive_factor):
        try:
            group = self.session.query(models.FeeGroup).filter_by(name=name).one()
        except NoResultFound:
            group = models.FeeGroup(name, aggressive_factor, passive_factor)
            self.session.add(group)
        else:
            print "FeeGroup %s already exists" % group

    def set(self, name, field, value):
        group = self.session.query(models.FeeGroup).filter_by(
            name=name).first()
        if group == None:
            raise Exception("Fee Group '%s' not found" % name)
        setattr(group, field, value)


class AdminManager:
    def __init__(self, session):
        self.session = session

    def add(self, username, password_hash="", level=5):
        try:
            user = self.session.query(models.AdminUser).filter_by(username=username).one()
        except NoResultFound:
            user = models.AdminUser(username, password_hash, level)
            self.session.add(user)
        else:
            print "AdminUser %s already exists" % user

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
        print "\t\ttype:\t\t%s" % user.type
        print "\t\tpermissions:\t\t%s" % user.permissions
        print "\t\tfees:\t\t%s" % user.fees
        print "\tPositions:"
        for position in user.positions:
            prefix = "%s-%s:" % (position.contract.ticker,
                                        position.contract.id)
            print "\t\t%s\t%s" % (prefix.ljust(10), position.position)

    def add(self, username):
        try:
            user = self.session.query(models.User).filter_by(username=username).one()
        except NoResultFound:
            user = models.User(username, "")
            self.session.add(user)
        else:
            print "User %s already exists" % user

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
                user=user, contract=contract).first()
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

    def set(self, username, field, value):
        user = self.session.query(models.User).filter_by(
                username=username).first()
        if user == None:
            raise Exception("User '%s' not found." % username)

        if field == "fees":
            try:
                fee_group = self.session.query(models.FeeGroup).filter_by(name=value).one()
            except NoResultFound:
                print "No fee group: %s" % value
                return
            else:
                field = "fee_group_id"
                value = fee_group.id

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
        self.set(username, "password", "%s:%s" % (salt, password))

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
        if contract.contract_type != "cash":
            print "\tFee:\t%s" % contract.fees

    def add(self, ticker):
        try:
            contract = self.session.query(models.Contract).filter_by(ticker=ticker).one()
        except NoResultFound:
            contract = models.Contract(ticker)
            self.session.add(contract)
        else:
            print "Contract %s already exists" % contract

    def list(self):
        contracts = self.session.query(models.Contract).all()
        for contract in contracts:
            print contract

    def modify_denominator(self, ticker_or_id, value):
        contract = self.resolve(self.session, ticker_or_id)
        if contract.contract_type == "cash":
            old_denominator = contract.denominator
            denominator_ratio_float = float(value)/float(old_denominator)
            denominator_ratio = int(denominator_ratio_float)

            if denominator_ratio_float != denominator_ratio:
                raise NotImplementedError

            contract.denominator = value
            if contract.hot_wallet_limit is not None:
                contract.hot_wallet_limit *= denominator_ratio

            self.session.add(contract)

            # Get contracts use this contract
            denominated = self.session.query(models.Contract).filter_by(denominated_contract_ticker=contract.ticker)
            payout = self.session.query(models.Contract).filter_by(payout_contract_ticker=contract.ticker)

            print "Denominated by %s: " % contract.ticker
            for d in denominated:
                if d.margin_high is not None:
                    d.margin_high *= denominator_ratio

                if d.margin_low is not None:
                    d.margin_low *= denominator_ratio

                self.session.add(d)

                # Get trades and orders
                self.session.query(models.Trade).filter_by(contract_id=d.id).update({'price': models.Trade.price * denominator_ratio})
                self.session.query(models.Order).filter_by(contract_id=d.id).update({'price': models.Order.price * denominator_ratio})

            print "Payout with %s: " % contract.ticker
            for p in payout:
                # Get trades and orders
                self.session.query(models.Trade).filter_by(contract_id=p.id).update({'quantity': models.Trade.quantity * denominator_ratio})
                self.session.query(models.Order).filter_by(contract_id=p.id).update({'quantity': models.Order.quantity * denominator_ratio, 'quantity_left': models.Order.quantity_left * denominator_ratio})


            print "Positions:"
            self.session.query(models.Position).filter_by(contract_id=contract.id).update({'position': models.Position.position * denominator_ratio})
            print "Postings:"
            self.session.query(models.Posting).filter_by(contract_id=contract.id).update({'quantity': models.Posting.quantity * denominator_ratio})
        else:
            raise NotImplementedError

    def set(self, ticker_or_id, field, value):
        contract = self.resolve(self.session, ticker_or_id)
        if contract == None:
            raise Exception("Contract '%s' not found." % ticker_or_id)
        if field == 'expiration':
            value = parser.parse(value)

        setattr(contract, field, value)
        self.session.merge(contract)

    def modify(self, ticker_or_id, field, value):
        if field == 'denominator':
            self.modify_denominator(ticker_or_id, value)
        else:
            raise NotImplementedError


class AddressManager:
    def __init__(self, session):
        self.session = session

    def add(self, ticker_or_id, address):
        contract = ContractManager.resolve(self.session, ticker_or_id)
        if contract == None:
            raise Exception("Contract '%s' not found." % ticker_or_id)
        address = models.Addresses(None, contract, address)
        self.session.add(address)

    def list(self, ticker_or_id):
        contract = ContractManager.resolve(self.session, ticker_or_id)
        if contract == None:
            raise Exception("Contract '%s' not found." % ticker_or_id)
        addresses = self.session.query(models.Addresses).filter_by(
                contract=contract).all()
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

    def set(self, address, field, value):
        addr = self.session.query(models.Addresses).filter_by(
                address=address).first()
        if addr == None:
            raise Exception("Address '%s' not found." % address)
        setattr(addr, field, value)
        self.session.merge(addr)

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
            "permissions": PermissionsManager(session),
            "admin": AdminManager(session),
            "fees": FeesManager(session),
        }

    def parse(self, line):
        tokens = [t.decode('unicode_escape') for t in shlex.split(line)]

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
        print "WARNING: DO NOT RUN WHILE SPUTNIK IS RUNNING. SHUT EVERYTHING DOWN FIRST"
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
	raise e

if __name__ == "__main__":
    main()

