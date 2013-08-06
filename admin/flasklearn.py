from sqlalchemy import create_engine, MetaData

engine = create_engine('postgresql://penny:arcade@localhost/test', convert_unicode=True)
metadata = MetaData(bind=engine)

from sqlalchemy import Table, Column, Integer, String
from sqlalchemy.orm import mapper
from yourapplication.database import metadata, db_session

class User(object):
    query = db_session.query_property()

    def __init__(self, name=None, email=None):
        self.name = name
        self.email = email

    def __repr__(self):
        return '<User %r>' % (self.name)

users = Table('users', metadata, autoload=True)
mapper(User, users)

User.query.all()
