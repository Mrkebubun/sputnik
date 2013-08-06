from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
 
engine = create_engine('postgresql://penny:arcade@localhost/test', echo=True)
Base = declarative_base(engine)
########################################################################
class Bookmarks(Base):
    """"""
    __tablename__ = 'users'
    __table_args__ = {'autoload':True}
 
#----------------------------------------------------------------------
def loadSession():
    """"""
    metadata = Base.metadata
    Session = sessionmaker(bind=engine)
    session = Session()
    return session
 
if __name__ == "__main__":
    session = loadSession()
    res = session.query(Bookmarks).all()
    for item in  res:
      print item
      print item.nickname
