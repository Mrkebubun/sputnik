from __future__ import absolute_import
 
from autobahn.twisted.wamp import FutureMixin
from sputnik.webserver.router.wamp import protocol, router, broker, dealer
 
class Broker(FutureMixin, broker.Broker):
    """
    Basic WAMP broker for Twisted-based applications.
    """


class Dealer(FutureMixin, dealer.Dealer):
    """
    Basic WAMP dealer for Twisted-based applications.
    """


class Router(FutureMixin, router.Router):
    """
    Basic WAMP router for Twisted-based applications.
    """
    
    broker = Broker
    """
    The broker class this router will use. Defaults to :class:`autobahn.twisted.wamp.Broker`
    """

    dealer = Dealer
    """
    The dealer class this router will use. Defaults to :class:`autobahn.twisted.wamp.Dealer`
    """


class RouterFactory(FutureMixin, router.RouterFactory):
    """
    Basic WAMP router factory for Twisted-based applications.
    """

    router = Router
    """
    The router class this router factory will use. Defaults to :class:`autobahn.twisted.wamp.Router`
    """

class RouterSession(FutureMixin, protocol.RouterSession):
    """
    WAMP router session for Twisted-based applications.
    """


class RouterSessionFactory(FutureMixin, protocol.RouterSessionFactory):
    """
    WAMP router session factory for Twisted-based applications.
    """

    session = RouterSession
    """
    The router session class this router session factory will use. Defaults to :class:`autobahn.asyncio.wamp.RouterSession`.
    """

