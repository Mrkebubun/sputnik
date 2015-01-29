__author__ = 'sameer'

from twisted.trial import unittest
from twisted.internet import task, reactor
import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))

class TestExport:
    test_function_argument = None

    from sputnik import zmq_util
    @zmq_util.export
    def test_function(self, success):
        self.test_function_argument = success
        if success:
            return True
        else:
            raise Exception("Ack")

class TestAsyncRouterDealer(unittest.TestCase):
    def setUp(self):
        from sputnik import zmq_util
        import random
        port = random.randint(50000, 60000)
        self.dealer_proxy = zmq_util.dealer_proxy_async("tcp://127.0.0.1:%d" % port, timeout=None)
        self.router_share = zmq_util.router_share_async(TestExport(), "tcp://127.0.0.1:%d" % port)

    def tearDown(self):
        self.dealer_proxy._connection.factory.shutdown()
        self.router_share.connection.factory.shutdown()

    def test_success(self):
        d = self.dealer_proxy.test_function(True)
        def onSuccess(result):
            self.assertTrue(result)

        def onFail(error):
            self.assertTrue(False)

        d.addCallbacks(onSuccess, onFail)
        return d

    def test_fail(self):
        d = self.dealer_proxy.test_function(False)

        def onSuccess(result):
            self.assertTrue(False)

        def onFail(failure):
            self.flushLoggedErrors()
            self.assertEqual(failure.value.args, (u'Ack',))

        return d.addCallbacks(onSuccess, onFail)

    def test_bad_method(self):
        d = self.dealer_proxy.bad_method(True)
        def onSuccess(result):
            self.assertTrue(result)

        def onFail(failure):
            self.assertIsInstance(failure.value, Exception)

        d.addCallbacks(onSuccess, onFail)
        return d

class TestSyncRouterDealer(unittest.TestCase):
    pass

class TestAsyncPushPull(unittest.TestCase):
    def setUp(self):
        from sputnik import zmq_util
        import random
        port = random.randint(50000, 60000)
        self.push_proxy = zmq_util.push_proxy_async("tcp://127.0.0.1:%d" % port)
        self.export = TestExport()
        self.pull_share = zmq_util.pull_share_async(self.export, "tcp://127.0.0.1:%d" % port)

    def test_call_function(self):
        self.push_proxy.test_function(True)

        def check():
            self.assertTrue(self.export.test_function_argument)

        d = task.deferLater(reactor, 1, check)
        return d

    def tearDown(self):
        self.push_proxy._connection.factory.shutdown()
        self.pull_share.connection.factory.shutdown()

class TestSyncPushPull(unittest.TestCase):
    pass
