#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

__author__ = 'sameer'

import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../server"))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "../tools"))

from twisted.trial import unittest
from twisted.internet import reactor, task
from sputnik import zendesk
from pprint import pprint

class TestZendesk(unittest.TestCase):
    def setUp(self):
        self.zendesk = zendesk.Zendesk("mimetic", "5bZYIMtkHWTuaJijvkKuXVeaoXumETWdyCa2wTpN", 'sameer@m2.io')

    def test_create_ticket_with_files(self):
        user = {'nickname': 'Test',
                'email': 'testmail@m2.io' }
        file1 = {'filename': "content a",
                 'type': 'application/zip',
                 'data': 'zip file data'}
        file2 = {'filename': "content b",
                 'type': 'application/unknown',
                 'data': 'unknown file data'}

        d = self.zendesk.create_ticket(user, "Ignore this test ticket", "This is the body",
                                        [file1, file2])

        def _cb(results):
            pprint(results)
            self.assertTrue(True)

        def _err(failure):
            self.assertTrue(False)
            pprint(failure)

        d.addCallback(_cb)
        d.addErrback(_err)

        def wait_for_dc(result):
            dc = reactor.getDelayedCalls()
            if len(dc) > 0:
                return task.deferLater(reactor, 3, wait_for_dc, result)
            else:
                return result

        return d.addBoth(wait_for_dc)

