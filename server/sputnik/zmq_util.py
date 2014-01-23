import inspect
import json
import logging
from txzmq import ZmqFactory, ZmqEndpoint
from txzmq import ZmqREQConnection, ZmqREPConnection
from txzmq import ZmqPullConnection, ZmqPushConnection
from twisted.internet.defer import Deferred, maybeDeferred
from functools import partial

def export(obj):
    obj._exported = True
    return obj

class _Exported:
    def __init__(self, wrapped, receiver):
        self.wrapped = wrapped
        self.receiver = receiver
        self.mapper = {}
        for k in inspect.getmembers(wrapped.__class__, inspect.ismethod):
            if hasattr(k[1], "_exported"):
                self.mapper[k[0]] = k[1]

 
    def dispatch(self, message_id, rpc_call):
        def rpc_error(message):
            logging.warn("RPC Error: %s" % message)
            if message_id == None:
                return
            response = {"success":False, "result":message}
            self.receiver.reply(message_id, json.dumps(response))

        # parse the JSON
        try:
            request = json.loads(rpc_call)
        except ValueError:
            return self.rpc_error("Invalid JSON received.")

        # extract method name and arguments
        method_name = request.get("method", None)
        args = request.get("arg", [])
        kwargs = request.get("kwargs", {})

        # sanitize input
        if method_name == None:
            return rpc_error("Missing method name.")
        if not isinstance(args, list):
            return rpc_error("Arguments are not a list.")
        if not isinstance(kwargs, dict):
            return rpc_error("Keyword arguments are not a dict.")
        if method_name not in self.mapper:
            return rpc_error("Method not found: %s" % method_name)

        def result(value):
            logging.info("Got result for method %s." % method_name)
            if message_id == None:
                return
            # test to see if the result will serialize
            try:
                json.dumps(value)
            except:
                value = str(value)
            response = {"success":True, "result":value}
            self.receiver.reply(message_id, json.dumps(response))

        def exception(failure):
            logging.warn("Caught exception into dispatched method.")
            logging.warn(failure)
            if message_id == None:
                return
            response = {"success":False, "result":str(failure.value)}
            self.receiver.reply(message_id, json.dumps(response))

        logging.info("Dispatching %s..." % method_name)
        method = self.mapper[method_name]
        d = maybeDeferred(method, self.wrapped, *args, **kwargs)
        d.addCallbacks(result, exception)

def share(obj, address=None, mode="router"):
    if mode == "router":
        receiver = ZmqREPConnection(ZmqFactory(), ZmqEndpoint("bind", address))
    elif mode == "pull":
        receiver = ZmqPullConnection(ZmqFactory(), ZmqEndpoint("bind", address))
    else:
        raise Exception("Mode not recognized.")
    exported = _Exported(obj, receiver)
    receiver.gotMessage = exported.dispatch
    receiver.onPull = lambda x: partial(exported.dispatch, None)(x[0])

class RemoteException(Exception):
    pass

class Proxy:
    def __init__(self, connection, address, mode):
        self._connection = connection
        self._address = address
        self.mode = mode

    def __getattr__(self, key):
        if key.startswith("__") and key.endswith("__"):
            raise AttributeError
        def remote_method(*args, **kwargs):
            message = {"method":key, "args":args, "kwargs":kwargs}
            if self.mode == "push":
                return self._connection.push(json.dumps(message))
            d = self._connection.sendMsg(json.dumps(message))
            def strip_multipart(message):
                return message[0]
            def parse_result(message):
                message = json.loads(message)
                if message["success"] == True:
                    return message["result"]
                else:
                    raise RemoteException(message["result"])
            d.addCallback(strip_multipart)
            d.addCallback(parse_result)
            return d
        return remote_method

def proxy(address, mode="dealer"):
    if mode == "dealer":
        sender = ZmqREQConnection(ZmqFactory(), ZmqEndpoint("connect", address))
    elif mode == "push":
        sender = ZmqPushConnection(ZmqFactory(),
            ZmqEndpoint("connect", address))
    else:
        raise Exception("Mode not recognized.")
    return Proxy(sender, address, mode)

