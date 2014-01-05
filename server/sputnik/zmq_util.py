import inspect
import json
import logging
from txzmq import ZmqFactory, ZmqEndpoint, ZmqPullConnection
import zmq

def export(obj):
    obj._exported = True
    return obj

class _Exported:
    def __init__(self, obj):
        self.obj = obj
        self.mapper = {}
        for k in inspect.getmembers(obj.__class__, inspect.ismethod):
            if hasattr(k[1], "_exported"):
                self.mapper[k[0]] = k[1]

    def dispatch(self, method_name, *args, **kwargs):
        try:
            method = self.mapper[method_name]
        except KeyError:
            logging.warn("Method not found: %s" % method_name)
            return
        try:
            method(self.obj, *args, **kwargs)
        except Exception, e:
            logging.warn("Caught exception handling %s." % method_name)
            logging.exception(e)

    def process(self, message):
        # txzmq returns a list
        if isinstance(message, list):
            for part in message:
                self.process(part)
            return

        try:
            request = json.loads(message)
            method = request.get("method", None)
            args = request.get("arg", [])
            kwargs = request.get("kwargs", {})
            if method == None:
                logging.warn("Missing method name.")
                return
            if not isinstance(args, list):
                logging.warn("Arguments are not a list.")
                return
            if not isinstance(kwargs, dict):
                logging.warn("Keyword arguments are not a dict.")
                return
            self.dispatch(method, *args, **kwargs)
        except ValueError:
            logging.warn("Invalid JSON received.")

def share(obj, address):
    exported = _Exported(obj)
    context = zmq.Context()
    receiver = context.socket(zmq.PULL)
    receiver.bind(address)
    while True:
        exported.process(receiver.recv())

def share_async(obj, address=None):
    exported = _Exported(obj)
    receiver = ZmqPullConnection(ZmqFactory(), ZmqEndpoint("bind", address))
    receiver.onPull = exported.process

class Proxy:
    def __init__(self, connection, address):
        self._connection = connection
        self._address = address

    def __getattr__(self, key):
        if key.startswith("__") and key.endswith("__"):
            raise AttributeError
        def remote_method(*args, **kwargs):
            message = {"method":key, "args":args, "kwargs":kwargs}
            if hasattr(self._connection, "push"):
                # txzmq connection
                self._connection.push(json.dumps(message))
            else:
                self._connection.send(json.dumps(message))
        return remote_method

def proxy_async(address):
    sender = ZmqPushConnection(ZmqFactory(), ZmqEndpoint("connect", address))
    return Proxy(sender, address)

def proxy(address):
    context = zmq.Context()
    sender = context.socket(zmq.PUSH)
    sender.connect(address)
    return Proxy(sender, address)

