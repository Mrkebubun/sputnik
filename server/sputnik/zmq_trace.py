#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

import inspect
import uuid
import copy
import observatory
import sys

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.enterprise import adbapi
import twisted.python.log
import twisted.python.util

def new_context(n=2):
    stack = inspect.stack()
    caller_frame = stack[n][0]
    context = {}
    uid = str(uuid.uuid4())
    context["uid"] = uid
    caller_frame.f_locals["_context"] = context
    del caller_frame
    return context

def get_context():
    stack = inspect.stack()
    found = None
    for i in range(len(stack)):
        frame = stack[i][0]
        context = frame.f_locals.get("_context")
        if context:
            found = context
            del frame
            break
        del frame
    del stack
    if found:
        return found

class SputnikTracer(twisted.python.log.FileLogObserver):
    def __init__(self):
        self.dbpool = adbapi.ConnectionPool("sqlite3", "/tmp/sputnik.log",
                check_same_thread=False)
        self.dbpool.runQuery("CREATE TABLE IF NOT EXISTS log (time REAL, uid TEXT, parent_uid TEXT, level INTEGER, system TEXT, message TEXT);")

    def emit(self, eventDict):
        text = twisted.python.log.textFromEventDict(eventDict)
        if text is None:
            return

        context = get_context() or {}

        time = eventDict["time"]
        uid = context.get("uid")
        parent_uid = context.get("parent_uid")
        level = eventDict.get("level", 20)
        system = eventDict["system"]

        self.dbpool.runQuery("INSERT INTO log VALUES (?, ?, ?, ?, ?, ?);",
                (time, uid, parent_uid, level, system, text))


import zmq_util

export_decode = zmq_util.Export.decode
export_encode = zmq_util.Export.encode

def new_export_decode(self, message):
    method_name, args, kwargs = export_decode(self, message)
    context = new_context()
    if "_context" in kwargs:
        context["parent_uid"] = kwargs["_context"]["uid"]
        context["uid"] = kwargs["_context"]["call"]
        del kwargs["_context"]
    return method_name, args, kwargs

def new_export_encode(self, success, value):
    json = export_encode(self, success, value)
    context = get_context()
    return json

zmq_util.Export.decode = new_export_decode
zmq_util.Export.encode = new_export_encode

def new_getattr(self, key):
    """

    :param key:
    :returns:
    :raises: Exception
    """
    if key.startswith("__") and key.endswith("__"):
        raise AttributeError

    def remote_method_traced(*args, **kwargs):
        """

        :param args:
        :param kwargs:
        :returns: Deferred
        :raises: Exception
        """
        context = get_context()
        if not context:
            context = new_context()
        uid = context["uid"]

        send_context = {}
        send_context["uid"] = uid
        send_context["call"] = str(uuid.uuid4())
        kwargs["_context"] = send_context
       
        message = self.encode(key, args, kwargs)
        d = self.send(message)

        def strip_multipart(message):
            return message[0]

        def parse_result(message):
            success, result = self.decode(message)
            if success:
                return result
            # In this case the 'result' is an exception so we should
            # raise it
            raise result

        if isinstance(d, Deferred):
            d.addCallback(strip_multipart)
            d.addCallback(parse_result)

        return d

    return remote_method_traced

zmq_util.Proxy.__getattr__ = new_getattr
zmq_util.DealerProxyAsync.__getattr__ = new_getattr
zmq_util.PushProxyAsync.__getattr__ = new_getattr

observer = SputnikTracer()
twisted.python.log.addObserver(observer.emit)

