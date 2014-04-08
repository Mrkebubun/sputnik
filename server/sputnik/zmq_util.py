import inspect
import json
import logging
import zmq
import uuid
from txzmq import ZmqFactory, ZmqEndpoint
from txzmq import ZmqREQConnection, ZmqREPConnection
from txzmq import ZmqPullConnection, ZmqPushConnection
from twisted.internet import reactor
from twisted.internet.defer import Deferred, maybeDeferred
from functools import partial


logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s() %(lineno)d:\t %(message)s', level=logging.DEBUG)

class RemoteCallException(Exception): pass
class RemoteCallTimedOut(RemoteCallException): pass


def export(obj):
    obj._exported = True
    return obj


class Export:
    def __init__(self, wrapped):
        """

        :param wrapped:
        """
        self.wrapped = wrapped
        self.mapper = {}
        for k in inspect.getmembers(wrapped.__class__, inspect.ismethod):
            if hasattr(k[1], "_exported"):
                self.mapper[k[0]] = k[1]

    def decode(self, message):
        """

        :param message:
        :return: :raise RemoteCallException:
        """
        logging.debug("Decoding message...")

        # deserialize
        try:
            request = json.loads(message)
        except:
            raise RemoteCallException("Invalid JSON received.")

        # extract method name and arguments
        method_name = request.get("method", None)
        args = request.get("args", [])
        kwargs = request.get("kwargs", {})
        logging.debug("method=%s, args=%s, kwargs=%s" % (method_name, args, kwargs))

        # look up method
        method = self.mapper.get(method_name, None)
        if method is None:
            raise RemoteCallException("Method not found: %s" % method_name)

        # sanitize input
        if method_name == None:
            raise RemoteCallException("Missing method name.")
        if not isinstance(args, list):
            raise RemoteCallException("Arguments are not a list.")
        if not isinstance(kwargs, dict):
            raise RemoteCallException("Keyword arguments are not a dict.")

        return method_name, args, kwargs

    def encode(self, success, value):
        logging.debug("Encoding message...")

        # try to serialize Exception if there was a failure
        if not success:
            if isinstance(value, Exception):
                klass = value.__class__
                value = {"class":klass.__name__, "module": klass.__module__,
                    "args":value.args}

        # test to see if result serializes
        try:
            json.dumps(value)
        except:
            logging.warn("Message cannot be serialized. Converting to string.")
            # do our best to serialize
            try:
                value = repr(value)
            except:
                success = False
                value = "Result could not be serialized."

        logging.debug("success=%d, value=%s" % (success, json.dumps(value)))
        if success:
            return json.dumps({"success":success, "result":value})
        return json.dumps({"success":success, "exception":value})

class AsyncExport(Export):
    def dispatch(self, method_name, args, kwargs):
        """

        :param method_name:
        :param args:
        :param kwargs:
        :returns: maybeDeferred
        """
        logging.info("Dispatching %s..." % method_name)
        logging.debug("method_name=%s, args=%s, kwars=%s" %
            (method_name, str(args), str(kwargs)))
        method = self.mapper[method_name]
        return maybeDeferred(method, self.wrapped, *args, **kwargs)

class SyncExport(Export):
    def dispatch(self, method_name, args, kwargs):
        """

        :param method_name:
        :param args:
        :param kwargs:
        :returns:
        """
        logging.info("Dispatching %s..." % method_name)
        logging.debug("method_name=%s, args=%s, kwars=%s" %
            (method_name, str(args), str(kwargs)))
        method = self.mapper[method_name]
        return method(self.wrapped, *args, **kwargs)

class AsyncPullExport(AsyncExport):
    def __init__(self, wrapped, connection):
        """

        :param wrapped:
        :param connection:
        """
        AsyncExport.__init__(self, wrapped)
        self.connection = connection
        self.connection.onPull = self.onPull

    def onPull(self, message):
        """

        :param message:
        :returns: Deferred
        """
        try:
            # take the first part of the multipart message
            method_name, args, kwargs = self.decode(message[0])
        except Exception, e:
            return logging.warn("RPC Error: %s" % e)

        def result(value):
            logging.info("Got result for method %s." % method_name)

        def exception(failure):
            logging.warn("Caught exception in method %s." % method_name)
            logging.debug(failure)

        d = self.dispatch(method_name, args, kwargs)
        d.addCallbacks(result, exception)

class AsyncRouterExport(AsyncExport):
    def __init__(self, wrapped, connection):
        """

        :param wrapped:
        :param connection:
        """
        AsyncExport.__init__(self, wrapped)
        self.connection = connection
        self.connection.gotMessage = self.gotMessage

    def gotMessage(self, message_id, message):
        """

        :param message_id:
        :param message:
        :returns: Deferred
        """
        try:
            method_name, args, kwargs = self.decode(message)
        except Exception, e:
            logging.warn("RPC Error: %s" % e)
            return self.connection.reply(message_id, self.encode(False, e))

        def result(value):
            logging.info("Got result for method %s." % method_name)
            self.connection.reply(message_id, self.encode(True, value))

        def exception(failure):
            logging.warn("Caught exception in method %s." % method_name)
            logging.warn(failure)
            self.connection.reply(message_id,
                self.encode(False, failure.value))

        d = self.dispatch(method_name, args, kwargs)
        d.addCallbacks(result, exception)

class SyncPullExport(SyncExport):
    def __init__(self, wrapped, connection):
        """

        :param wrapped:
        :param connection:
        """
        SyncExport.__init__(self, wrapped)
        self.connection = connection

    def process(self, message):
        """

        """
        sender_id = message[0]
        message = message[1]
        try:
            # take the first part of the multipart message
            method_name, args, kwargs = self.decode(message)
        except Exception, e:
            return logging.warn("RPC Error: %s" % e)

        def result(value):
            logging.info("Got result for method %s." % method_name)

        def exception(failure):
            logging.warn("Caught exception in method %s." % method_name)
            logging.warn(failure)

        try:
            result(self.dispatch(method_name, args, kwargs))
        except Exception, e:
            exception(e)

class SyncRouterExport(SyncExport):
    def __init__(self, wrapped, connection):
        """

        :param wrapped:
        :param connection:
        """
        SyncExport.__init__(self, wrapped)
        self.connection = connection

    def process(self, message):
        """

        :param message:
        :return:
        """
        sender_id = message[0]
        message_id = message[1]
        message = message[3]
        try:
            method_name, args, kwargs = self.decode(message)
        except Exception, e:
            logging.warn("RPC Error: %s" % e)
            return self.connection.send_multipart(
                [sender_id, message_id, "", self.encode(False, e)])

        def result(value):
            logging.info("Got result for method %s id: %s-%s" % (method_name, message_id, sender_id))
            self.connection.send_multipart(
                [sender_id, message_id, "", self.encode(True, value)])

        def exception(failure):
            logging.warn("Caught exception in method %s." % method_name)
            logging.warn(failure)
            self.connection.send_multipart(
                [sender_id, message_id, "", self.encode(False, failure)])

        try:
            result(self.dispatch(method_name, args, kwargs))
        except Exception, e:
            exception(e)


def router_share_async(obj, address):
    """

    :param obj:
    :param address:
    :returns: AsyncRouterExport
    """
    socket = ZmqREPConnection(ZmqFactory(), ZmqEndpoint("bind", address))
    return AsyncRouterExport(obj, socket)

def pull_share_async(obj, address):
    """

    :param obj:
    :param address:
    :returns: AsyncPullExport
    """
    socket = ZmqPullConnection(ZmqFactory(), ZmqEndpoint("bind", address))
    return AsyncPullExport(obj, socket)

def router_share_sync(obj, address):
    """

    :param obj:
    :param address:
    """
    context = zmq.Context()
    socket = context.socket(zmq.ROUTER)
    socket.bind(address)
    sre = SyncRouterExport(obj, socket)
    while True:
        sre.process(socket.recv_multipart())

def pull_share_sync(obj, address):
    """

    :param obj:
    :param address:
    """
    context = zmq.Context()
    socket = context.socket(zmq.ROUTER)
    socket.bind(address)
    spe = SyncPullExport(obj, socket)
    while True:
        spe.process(socket.recv_multipart())

class Proxy:
    def __init__(self, connection):
        """

        :param connection:
        """
        self._connection = connection

    def decode(self, message):
        """

        :param message:
        :returns: tuple
        :raises: Exception
        """
        logging.debug("Decoding message... %s" % message)

        # deserialize
        try:
            response = json.loads(message)
        except:
            raise Exception("Invalid JSON received.")

        # extract success and result
        success = response.get("success", None)
        if success == None:
            raise Exception("Missing success status.")

        if success:
            return success, response.get("result", None)

        # decode the exception
        exception = response.get("exception", None)
        if isinstance(exception, dict):
            cname = exception.get("class", None)
            mname = exception.get("module", None)
            if not cname or not mname:
                klass = Exception
            else:
                try:
                    module = __import__(mname)
                    klass = getattr(module, cname)
                except:
                    klass = Exception
            args = exception.get("args", ())
            exception = klass(*args)
        return success, exception

    def encode(self, method_name, args, kwargs):
        logging.debug("Encoding message...")
        logging.debug("method=%s, args=%s, kwargs=%s" % (method_name, args, kwargs))

        return json.dumps({"method":method_name, "args":args, "kwargs":kwargs})

    def __getattr__(self, key):
        """

        :param key:
        :returns:
        :raises: Exception
        """
        if key.startswith("__") and key.endswith("__"):
            raise Exception(AttributeError)

        def remote_method(*args, **kwargs):
            """

            :param args:
            :param kwargs:
            :returns: Deferred
            :raises: Exception
            """
            message = self.encode(key, args, kwargs)
            d = self.send(message)

            def strip_multipart(message):
                return message[0]

            def parse_result(message):
                success, result = self.decode(message)
                if success:
                    return result
                raise Exception(result)

            if isinstance(d, Deferred):
                d.addCallback(strip_multipart)
                d.addCallback(parse_result)

            return d

        return remote_method

class DealerProxyAsync(Proxy):
    def __init__(self, connection, timeout=1):
        """

        :param connection:
        :param timeout:
        """
        self._timeout = timeout
        Proxy.__init__(self, connection)

    def send(self, message):
        """

        :param message:
        :returns: Deferred
        """
        d = self._connection.sendMsg(message)
        if self._timeout > 0:
            timeout = reactor.callLater(self._timeout, d.errback,
                RemoteCallTimedOut("Call timed out."))
            def cancelTimeout(result):
                if timeout.active():
                    timeout.cancel()
                return result
            d.addBoth(cancelTimeout)
        return d

class PushProxyAsync(Proxy):
    def send(self, message):
        """

        :param message:
        :returns:
        """
        return self._connection.push(message)

class DealerProxySync(Proxy):
    def __init__(self, connection, timeout=1):
        """

        :param connection:
        :param timeout:
        """
        self._timeout = timeout
        Proxy.__init__(self, connection)
        self._connection.RCVTIMEO = int(timeout * 1000)

    def send(self, message):
        self._id = str(uuid.uuid4())
        self._connection.send_multipart([self._id, "", message])
        try:
            data = self._connection.recv_multipart()
        except zmq.ZMQError, e:
            if str(e) == "Resource temporarily unavailable":
                raise RemoteCallTimedOut()
            raise e
        if data[0] != self._id:
            raise RemoteCallException("Invalid return ID.")
        message = data[2]
        success, result = self.decode(message)
        if success:
            return result
        raise Exception(result)

class PushProxySync(Proxy):
    def send(self, message):
        """

        :param message:
        :returns: None
        """
        self._connection.send(message)
        return None

def dealer_proxy_async(address):
    """

    :param address:
    :returns: DealerProxyAsync
    """
    socket = ZmqREQConnection(ZmqFactory(), ZmqEndpoint("connect", address))
    return DealerProxyAsync(socket)

def push_proxy_async(address):
    """


    :param address:
    :returns: PushProxyAsync
    """
    socket = ZmqPushConnection(ZmqFactory(), ZmqEndpoint("connect", address))
    return PushProxyAsync(socket)

def dealer_proxy_sync(address):
    """

    :param address:
    :returns: DealerProxySync
    """
    context = zmq.Context()
    socket = context.socket(zmq.DEALER)
    socket.connect(address)
    return DealerProxySync(socket)

def push_proxy_sync(address):
    """

    :param address:
    :returns: PushProxySync
    """
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    socket.connect(address)
    return PushProxySync(socket)

