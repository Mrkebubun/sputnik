__author__ = 'satosushi'

"""
Provides a common access to the database and a session object
"""
__author__ = 'satosushi'

import sqlalchemy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

engine = sqlalchemy.create_engine('postgresql://www-data@/www-data', echo=False)
Session = sqlalchemy.orm.sessionmaker(bind=engine)
#session = Session()
