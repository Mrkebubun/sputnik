"""
Provides a common access to the database and a session object
"""

import config

import sqlalchemy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.engine import Engine
import getpass

# hack to make sure sqlite honors foriegn keys
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

Base = declarative_base()

def get_uri(**kwargs):
    # If we are not root, override SQL username to be myself
    my_user = getpass.getuser()
    if my_user != 'root':
        kwargs['username'] = my_user

    uri = config.get("database", "uri", vars=kwargs)
    if uri.split(":")[0] == "sqlite":
        sqlalchemy.event.listen(Engine, "connect", set_sqlite_pragma)
    return uri

def get_session_maker(**kwargs):
    """

    :param kwargs:
    :returns: sessionmaker
    """
    engine = make_engine(**kwargs)
    Session = sqlalchemy.orm.sessionmaker(bind=engine)
    return Session

def make_engine(**kwargs):
    uri = get_uri(**kwargs)
    engine = sqlalchemy.create_engine(uri, echo=False)
    return engine


def make_session(**kwargs):
    """

    :param kwargs:
    :returns: Session
    """
    Session = get_session_maker(**kwargs)
    return Session()

