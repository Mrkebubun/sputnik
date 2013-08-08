import sys
from pprint import pprint

from twisted.python import log
from twisted.internet import reactor, ssl

from autobahn.websocket import connectWS
from autobahn.wamp import WampClientFactory, WampCraClientProtocol

base_uri = "http://example.com/"
trade_URI = base_uri + "trades#"
order_book_URI = base_uri + "order_book"

class TradingBot(WampCraClientProtocol):
    """
   Authenticated WAMP client using WAMP-Challenge-Response-Authentication ("WAMP-CRA").

   """

    def __init__(self):
        self.base_URI = "http://example.com/procedures/"
        self.user = 'a'
        self.psswd = 'a'


    def onSessionOpen(self):
        ## "authenticate" as anonymous
        ##
        #d = self.authenticate()

        ## authenticate as "foobar" with password "secret"
        ##
        d = self.authenticate(authKey=self.user,
                              authExtra=None,
                              authSecret=self.psswd)

        d.addCallbacks(self.onAuthSuccess, self.onAuthError)


    def onClose(self, wasClean, code, reason):
        reactor.stop()

    def action(self):
        '''
        overwrite me
        '''
        return True

    def onAuthSuccess(self, permissions):
        print "Authentication Success!", permissions
        self.action()
        #self.publish("http://example.com/topics/mytopic1", "Hello, world!")
        #self.sendClose()

    def onAuthError(self, e):
        uri, desc, details = e.value.args
        print "Authentication Error!", uri, desc, details

    def subToOrderBook(self):
       self.subscribe(order_book_URI, self.onOrderBook) 

    def subToTradeStream(self,ticker):
       self.subscribe(order_book_URI + str(ticker), self.onOrderBook) 

    def onOrderBook(self, topicUri, event):
        """
        overwrite me
        """
        print "Event", topicUri, event

    def onOrderBook(self, topicUri, event):
        """
        overwrite me
        """
        print "Event", topicUri, event

    def getNewAddress(self):
        d = self.call(self.base_URI + "get_new_address")
        d.addBoth(pprint)
        d.addBoth(self.sendClose)

    def getPositions(self):
        d = self.call(self.base_URI + "get_positions")
        d.addBoth(pprint)
        d.addBoth(self.sendClose)

    def listMarkets(self):
        d = self.call(self.base_URI + "list_markets")
        d.addBoth(pprint)
        d.addBoth(self.sendClose)

    def getOrderBook(self, ticker, callback):
        d = self.call(self.base_URI + "get_order_book", ticker)
        d.addBoth(callback)

    def getOpenOrders(self,callback):
        # store cache of open orders update asynchronously
        d = self.call(self.base_URI + "get_open_orders")
        d.addBoth(callback)

    def getTradeHistory(self, ticker, callback):
        d = self.call(self.base_URI + "get_trade_history", ticker, 1000000)
        d.addBoth(callback)

    def placeOrder(self, ticker, quantity, price, side):
        ord= {}
        ord['ticker'] = ticker
        ord['quantity'] = quantity
        ord['price'] = price
        ord['side'] = side
        print "inside place order", ord
        print self.base_URI + "place_order"
        d = self.call(self.base_URI + "place_order", ord)

    def cancelOrder(self, id):
        """
        cancels an order by its id.
        :param id: order id
        """
        print "inside cancel order"
        d = self.call(self.base_URI + "cancel_order", id)


if __name__ == '__main__':

    if len(sys.argv) > 1 and sys.argv[1] == 'debug':
        log.startLogging(sys.stdout)
        debug = True
    else:
        debug = False

    log.startLogging(sys.stdout)
    # ws -> wss
    factory = WampClientFactory("wss://localhost:9000", debugWamp=debug)
    factory.protocol = TradingBot

    # null -> ....
    if factory.isSecure:
        contextFactory = ssl.ClientContextFactory()
    else:
        contextFactory = None
        # (factory) -> (factory, contextFActory)
    connectWS(factory, contextFactory)
    reactor.run()
