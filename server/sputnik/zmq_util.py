import inspect
import json
import logging
from txzmq import ZmqFactory, ZmqEndpoint, ZmqREQConnection, ZmqREPConnection
from twisted.internet.defer import Deferred, maybeDeferred

def export(obj):
    obj._exported = True
    return obj

class _Exported:
    def __init__(self, obj, receiver):
        self.obj = obj
        self.receiver = receiver
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
            return maybeDeferred(method, self.obj, *args, **kwargs)
        except Exception, e:
            logging.warn("Caught exception handling %s." % method_name)
            logging.exception(e)

    def process(self, message_id, message):
        response = {"success":True, "result":None}
        
        def reply(value):
            try:
                json.dumps(value)
            except:
                value = str(value)
            response["result"] = value
            self.receiver.reply(message_id, json.dumps(response))

        def rpc_error(message):
            response["success"] = False
            response["result"] = message
            self.receiver.reply(message_id, json.dumps(response))

        def error(failure):
            value = failure.value
            try:
                json.dumps(value)
            except:
                value = str(failure.value)
            response["success"] = False
            response["result"] = value
            self.receiver.reply(message_id, json.dumps(response))

        try:
            request = json.loads(message)
            method = request.get("method", None)
            args = request.get("arg", [])
            kwargs = request.get("kwargs", {})
            if method == None:
                logging.warn("Missing method name.")
                return rpc_error("Missing method name.")
            if not isinstance(args, list):
                logging.warn("Arguments are not a list.")
                return rpc_error("Arguments are not a list.")
            if not isinstance(kwargs, dict):
                logging.warn("Keyword arguments are not a dict.")
                return rpc_error("Keyword arguments are not a dict.")
            d = self.dispatch(method, *args, **kwargs)
            d.addCallbacks(reply, error)
        except ValueError:
            logging.warn("Invalid JSON received.")
            return rpc_error("Invalid JSON received.")

def share(obj, address=None):
    receiver = ZmqREPConnection(ZmqFactory(), ZmqEndpoint("bind", address))
    exported = _Exported(obj, receiver)
    receiver.gotMessage = exported.process

class RemoteException(Exception):
    pass

class Proxy:
    def __init__(self, connection, address):
        self._connection = connection
        self._address = address

    def __getattr__(self, key):
        if key.startswith("__") and key.endswith("__"):
            raise AttributeError
        def remote_method(*args, **kwargs):
            message = {"method":key, "args":args, "kwargs":kwargs}
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

def proxy(address):
    sender = ZmqREQConnection(ZmqFactory(), ZmqEndpoint("connect", address))
    return Proxy(sender, address)

