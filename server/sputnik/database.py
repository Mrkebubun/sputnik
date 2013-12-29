"""
Provides a common access to the database and a session object
"""

import config

import sqlalchemy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


def get_uri(**kwargs):
    return config.get("database", "uri", vars=kwargs)

Base = declarative_base()

engine = sqlalchemy.create_engine(get_uri(), echo=False)

def make_session(**kwargs):
    engine = sqlalchemy.create_engine(get_uri(**kwargs), echo=False)
    Session = sqlalchemy.orm.sessionmaker(bind=engine)
    return Session()

