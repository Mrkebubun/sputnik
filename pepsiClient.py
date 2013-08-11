import sys
from pprint import pprint

from twisted.python import log
from twisted.internet import reactor, ssl

from autobahn.websocket import connectWS
from autobahn.wamp import WampClientFactory, WampCraClientProtocol

base_uri = "http://example.com/"
trade_URI = base_uri + "trades#"
safe_price_URI = base_uri + "safe_prices#"
order_book_URI = base_uri + "order_book"

fills_URI = base_uri + "user/fills#";
cancels_URI = base_uri + "user/cancels#";
open_orders_URI = base_uri + "user/open_orders#";

class TradingBot(WampCraClientProtocol):
    """
   Authenticated WAMP client using WAMP-Challenge-Response-Authentication ("WAMP-CRA").

   """

    def __init__(self):
        self.base_URI = "http://example.com/procedures/"
        self.user = 'a'
        self.psswd = 'a'

    def action(self):
        '''
        overwrite me
        '''
        return True

    """
    reactive events - on* 
    """

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

    def onAuthSuccess(self, permissions):
        print "Authentication Success!", permissions

        self.subToTradeStream(16)
        self.subToTradeStream(17)
        self.subOpenOrders(8)
        self.subOpenOrders(16)
        self.subOpenOrders(17)
        self.subCancels(8)
        self.subCancels(16)
        self.subCancels(17)
        self.subFills(8)
        self.subFills(16)
        self.subFills(17)
        self.subToSafePrices('USD.13.7.31')
        self.subToSafePrices(8)
        self.subToSafePrices(16)
        self.subToSafePrices(17)
        self.subToOrderBook()

        self.action()
        #self.publish("http://example.com/topics/mytopic1", "Hello, world!")
        #self.sendClose()

    def onAuthError(self, e):
        uri, desc, details = e.value.args
        print "Authentication Error!", uri, desc, details

    def onOrderBook(self, topicUri, event):
        """
        overwrite me
        """
        print "in onOrderBook"
        print "Event", topicUri, event

    def onTrade(self, topicUri, event):
        """
        overwrite me
        """
        print "in onTrade"
        print "Event", topicUri, event

    def onSafePrice(self, topicUri, event):
        """
        overwrite me
        """
        print "in onSafePriceg"
        print "Event", topicUri, event

    def onOpenOrder(self, topicUri, event):
        """
        overwrite me
        """
        print "in onOpenOrder"
        print "Event", topicUri, event

    def onCancel(self, topicUri, event):
        """
        overwrite me
        """
        print "in onCancel"
        print "Event", topicUri, event

    def onFill(self, topicUri, event):
        """
        overwrite me
        """
        print "in onFill"
        print "Event", topicUri, event

    """
    Subscriptions
    """
    def subOpenOrders(self,ticker):
       self.subscribe(open_orders_URI + str(ticker), self.onOpenOrder) 
       print 'subscribed to: ',open_orders_URI 

    def subCancels(self,ticker):
       self.subscribe(cancels_URI + str(ticker), self.onCancel) 
       print 'subscribed to: ', cancels_URI

    def subFills(self,ticker):
       self.subscribe(fills_URI + str(ticker), self.onFill) 
       print 'subscribed to: ', fills_URI

    def subToOrderBook(self):
       self.subscribe(order_book_URI, self.onOrderBook) 
       print order_book_URI

    def subToTradeStream(self,ticker):
       self.subscribe(trade_URI + str(ticker), self.onTrade) 
       print trade_URI + str(ticker)

    def subToSafePrices(self,ticker):
       self.subscribe(safe_price_URI + str(ticker), self.onSafePrice) 
       print safe_price_URI + str(ticker)


    """
    RPC calls
    """

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
