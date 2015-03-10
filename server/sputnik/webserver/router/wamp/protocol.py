from __future__ import absolute_import

from autobahn.wamp.interfaces import ISession, IPublication, IPublisher
from autobahn.wamp.interfaces import ISubscription, ISubscriber, ICaller
from autobahn.wamp.interfaces import IRegistration, ITransportHandler


from autobahn import util, wamp
from autobahn.wamp import uri, message, types, role, exception
from autobahn.wamp.exception import ProtocolError, SessionNotReady
from autobahn.wamp.types import SessionDetails

from autobahn.wamp.protocol import BaseSession

class RouterApplicationSession:
   """
   Wraps an application session to run directly attached to a WAMP router (broker+dealer).
   """

   def __init__(self, session, routerFactory, authid = None, authrole = None):
      """
      Wrap an application session and add it to the given broker and dealer.

      :param session: Application session to wrap.
      :type session: An instance that implements :class:`autobahn.wamp.interfaces.ISession`
      :param routerFactory: The router factory to associate this session with.
      :type routerFactory: An instance that implements :class:`autobahn.wamp.interfaces.IRouterFactory`
      :param authid: The fixed/trusted authentication ID under which the session will run.
      :type authid: str
      :param authrole: The fixed/trusted authentication role under which the session will run.
      :type authrole: str
      """

      ## remember router we are wrapping the app session for
      ##
      self._routerFactory = routerFactory
      self._router = None

      ## remember wrapped app session
      ##
      self._session = session

      ## remember "trusted" authentication information
      ##
      self._trusted_authid = authid
      self._trusted_authrole = authrole

      ## set fake transport on session ("pass-through transport")
      ##
      self._session._transport = self

      self._session.onConnect()


   def isOpen(self):
      """
      Implements :func:`autobahn.wamp.interfaces.ITransport.isOpen`
      """


   def close(self):
      """
      Implements :func:`autobahn.wamp.interfaces.ITransport.close`
      """
      if self._router:
         self._router.detach(self._session)


   def abort(self):
      """
      Implements :func:`autobahn.wamp.interfaces.ITransport.abort`
      """


   def send(self, msg):
      """
      Implements :func:`autobahn.wamp.interfaces.ITransport.send`
      """
      if isinstance(msg, message.Hello):

         self._router = self._routerFactory.get(msg.realm)

         ## fake session ID assignment (normally done in WAMP opening handshake)
         self._session._session_id = util.id()

         ## set fixed/trusted authentication information
         self._session._authid = self._trusted_authid
         self._session._authrole = self._trusted_authrole
         self._session._authmethod = None
         ## FIXME: the following does blow up
         #self._session._authmethod = u'trusted'
         self._session._authprovider = None

         ## add app session to router
         self._router.attach(self._session)

         ## fake app session open
         ##
         details = SessionDetails(self._session._realm, self._session._session_id,
            self._session._authid, self._session._authrole, self._session._authmethod,
            self._session._authprovider)

         self._session._as_future(self._session.onJoin, details)
         #self._session.onJoin(details)


      ## app-to-router
      ##
      elif isinstance(msg, message.Publish) or \
           isinstance(msg, message.Subscribe) or \
           isinstance(msg, message.Unsubscribe) or \
           isinstance(msg, message.Call) or \
           isinstance(msg, message.Yield) or \
           isinstance(msg, message.Register) or \
           isinstance(msg, message.Unregister) or \
           isinstance(msg, message.Cancel) or \
          (isinstance(msg, message.Error) and
               msg.request_type == message.Invocation.MESSAGE_TYPE):

         ## deliver message to router
         ##
         self._router.process(self._session, msg)

      ## router-to-app
      ##
      elif isinstance(msg, message.Event) or \
           isinstance(msg, message.Invocation) or \
           isinstance(msg, message.Result) or \
           isinstance(msg, message.Published) or \
           isinstance(msg, message.Subscribed) or \
           isinstance(msg, message.Unsubscribed) or \
           isinstance(msg, message.Registered) or \
           isinstance(msg, message.Unregistered) or \
          (isinstance(msg, message.Error) and (
               msg.request_type == message.Call.MESSAGE_TYPE or
               msg.request_type == message.Cancel.MESSAGE_TYPE or
               msg.request_type == message.Register.MESSAGE_TYPE or
               msg.request_type == message.Unregister.MESSAGE_TYPE or
               msg.request_type == message.Publish.MESSAGE_TYPE or
               msg.request_type == message.Subscribe.MESSAGE_TYPE or
               msg.request_type == message.Unsubscribe.MESSAGE_TYPE)):

         ## deliver message to app session
         ##
         self._session.onMessage(msg)

      else:
         ## should not arrive here
         ##
         raise Exception("RouterApplicationSession.send: unhandled message {0}".format(msg))



class RouterSession(BaseSession):
   """
   WAMP router session. This class implements :class:`autobahn.wamp.interfaces.ITransportHandler`.
   """

   def __init__(self, routerFactory):
      """
      Constructor.
      """
      BaseSession.__init__(self)
      self._transport = None

      self._router_factory = routerFactory
      self._router = None
      self._realm = None

      self._goodbye_sent = False
      self._transport_is_closing = False


   def onOpen(self, transport):
      """
      Implements :func:`autobahn.wamp.interfaces.ITransportHandler.onOpen`
      """
      self._transport = transport

      self._realm = None
      self._session_id = None
      self._pending_session_id = None

      ## session authentication information
      ##
      self._authid = None
      self._authrole = None
      self._authmethod = None
      self._authprovider = None


   def onHello(self, realm, details):
      return types.Accept()


   def onAuthenticate(self, signature, extra):
      return types.Accept()


   def onMessage(self, msg):
      """
      Implements :func:`autobahn.wamp.interfaces.ITransportHandler.onMessage`
      """
      if self._session_id is None:

         if not self._pending_session_id:
            self._pending_session_id = util.id()

         def welcome(realm, authid = None, authrole = None, authmethod = None, authprovider = None):
            self._session_id = self._pending_session_id
            self._pending_session_id = None
            self._goodbye_sent = False

            self._router = self._router_factory.get(realm)
            if not self._router:
               raise Exception("no such realm")

            self._authid = authid
            self._authrole = authrole
            self._authmethod = authmethod
            self._authprovider = authprovider

            roles = self._router.attach(self)

            msg = message.Welcome(self._session_id, roles, authid = authid, authrole = authrole, authmethod = authmethod, authprovider = authprovider)
            self._transport.send(msg)

            self.onJoin(SessionDetails(self._realm, self._session_id, self._authid, self._authrole, self._authmethod, self._authprovider))

         ## the first message MUST be HELLO
         if isinstance(msg, message.Hello):

            self._realm = msg.realm

            details = types.HelloDetails(msg.roles, msg.authmethods, msg.authid, self._pending_session_id)

            d = self._as_future(self.onHello, self._realm, details)

            def success(res):
               msg = None

               if isinstance(res, types.Accept):
                  welcome(self._realm, res.authid, res.authrole, res.authmethod, res.authprovider)

               elif isinstance(res, types.Challenge):
                  msg = message.Challenge(res.method, res.extra)

               elif isinstance(res, types.Deny):
                  msg = message.Abort(res.reason, res.message)

               else:
                  pass

               if msg:
                  self._transport.send(msg)

            def failed(err):
               print(err.value)

            self._add_future_callbacks(d, success, failed)

         elif isinstance(msg, message.Authenticate):

            d = self._as_future(self.onAuthenticate, msg.signature, msg.extra)

            def success(res):
               msg = None

               if isinstance(res, types.Accept):
                  welcome(self._realm, res.authid, res.authrole, res.authmethod, res.authprovider)

               elif isinstance(res, types.Deny):
                  msg = message.Abort(res.reason, res.message)

               else:
                  pass

               if msg:
                  self._transport.send(msg)

            def failed(err):
               print(err.value)

            self._add_future_callbacks(d, success, failed)

         elif isinstance(msg, message.Abort):

            ## fire callback and close the transport
            self.onLeave(types.CloseDetails(msg.reason, msg.message))

            self._session_id = None
            self._pending_session_id = None

            #self._transport.close()

         else:
            raise ProtocolError("Received {0} message, and session is not yet established".format(msg.__class__))

      else:

         if isinstance(msg, message.Hello):
            raise ProtocolError(u"HELLO message received, while session is already established")

         elif isinstance(msg, message.Goodbye):
            if not self._goodbye_sent:
               ## the peer wants to close: send GOODBYE reply
               reply = message.Goodbye()
               self._transport.send(reply)

            ## fire callback and close the transport
            self.onLeave(types.CloseDetails(msg.reason, msg.message))

            self._router.detach(self)

            self._session_id = None
            self._pending_session_id = None

            #self._transport.close()

         elif isinstance(msg, message.Heartbeat):

            pass ## FIXME

         else:

            self._router.process(self, msg)


   # noinspection PyUnusedLocal
   def onClose(self, wasClean):
      """
      Implements :func:`autobahn.wamp.interfaces.ITransportHandler.onClose`
      """
      self._transport = None

      if self._session_id:

         ## fire callback and close the transport
         try:
            self.onLeave(types.CloseDetails())
         except Exception as e:
            if self.debug:
               print("exception raised in onLeave callback: {0}".format(e))

         self._router.detach(self)

         self._session_id = None

      self._pending_session_id = None

      self._authid = None
      self._authrole = None
      self._authmethod = None
      self._authprovider = None


   def onJoin(self, details):
      """
      Implements :func:`autobahn.wamp.interfaces.ISession.onJoin`
      """


   def onLeave(self, details):
      """
      Implements :func:`autobahn.wamp.interfaces.ISession.onLeave`
      """


   def leave(self, reason = None, message = None):
      """
      Implements :func:`autobahn.wamp.interfaces.ISession.leave`
      """
      if not self._goodbye_sent:
         msg = wamp.message.Goodbye(reason = reason, message = message)
         self._transport.send(msg)
         self._goodbye_sent = True
      else:
         raise SessionNotReady(u"Already requested to close the session")



ITransportHandler.register(RouterSession)



class RouterSessionFactory:
   """
   WAMP router session factory.
   """

   session = RouterSession
   """
   WAMP router session class to be used in this factory.
   """

   def __init__(self, routerFactory):
      """

      :param routerFactory: The router factory this session factory is working for.
      :type routerFactory: Instance of :class:`autobahn.wamp.router.RouterFactory`.
      """
      self._routerFactory = routerFactory
      self._app_sessions = {}


   def add(self, session, authid = None, authrole = None):
      """
      Adds a WAMP application session to run directly in this router.

      :param: session: A WAMP application session.
      :type session: A instance of a class that derives of :class:`autobahn.wamp.protocol.WampAppSession`
      """
      self._app_sessions[session] = RouterApplicationSession(session, self._routerFactory, authid, authrole)


   def remove(self, session):
      """
      Removes a WAMP application session running directly in this router.
      """
      if session in self._app_sessions:
         self._app_sessions[session]._session.disconnect()
         del self._app_sessions[session]


   def __call__(self):
      """
      Creates a new WAMP router session.

      :returns: -- An instance of the WAMP router session class as
                   given by `self.session`.
      """
      session = self.session(self._routerFactory)
      session.factory = self
      return session

