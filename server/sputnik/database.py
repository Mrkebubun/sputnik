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

def get_session_maker(**kwargs):
    # If we are not root, override SQL username to be myself
    my_user = getpass.getuser()
    if my_user != 'root':
        kwargs['username'] = my_user

    uri = config.get("database", "uri", vars=kwargs)
    if uri.split(":")[0] == "sqlite":
        sqlalchemy.event.listen(Engine, "connect", set_sqlite_pragma)
    engine = sqlalchemy.create_engine(uri, echo=False)
    Session = sqlalchemy.orm.sessionmaker(bind=engine)
    return Session
    
def make_session(**kwargs):
    Session = get_session_maker(**kwargs)
    return Session()

