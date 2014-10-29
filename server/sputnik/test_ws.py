__author__ = 'sameer'

from autobahn.twisted.wamp import ApplicationSession, ApplicationSessionFactory, ApplicationRunner
from autobahn.wamp import register
from twisted.internet.defer import inlineCallbacks

class Interface(ApplicationSession):
    @register(u'get_markets')
    def get_markets(self):
        return [True, {'Market': 'YAY'}]

    @inlineCallbacks
    def onJoin(self, details):
        yield self.register(self)

class Factory(ApplicationSessionFactory):
    def __init__(self):
        pass

    def make(self, config):
        session = self.session(config)
        session.factory = self
        return session


if __name__ == "__main__":
    factory = Factory()
    factory.session = Interface

    runner = ApplicationRunner(url='ws://localhost:8000', realm='sputnik', debug=True)
    runner.run(factory.make)