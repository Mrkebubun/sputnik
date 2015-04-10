#!/usr/bin/python
#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

import os
import sys
import json
import datetime
from collections import defaultdict

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.protocols.policies import TimeoutMixin
from twisted.python import log

from sqlalchemy.exc import SQLAlchemyError, DBAPIError
from sqlalchemy.sql import select

import config
import util
import database
from models import Posting, Journal, User, Contract
from zmq_util import router_share_async, export, ComponentExport
from util import timed
from rpc_schema import schema
from watchdog import watchdog
import time
from exception import *

ARGUMENT_ERROR = LedgerException("exceptions/ledger/argument_error")
UID_MISMATCH = LedgerException("exceptions/ledger/uid_mismatch")
QUANTITY_MISMATCH = LedgerException("exceptions/ledger/quantity_mismatch")
TYPE_MISMATCH = LedgerException("exceptions/ledger/type_mismatch")
COUNT_MISMATCH = LedgerException("exceptions/ledger/count_mismatch")
GROUP_TIMEOUT = LedgerException("exceptions/ledger/group_timeout")
INTERNAL_ERROR = LedgerException("exceptions/ledger/internal_error")
DATABASE_ERROR = LedgerException("exceptions/ledger/database_error")

class PostingGroup(TimeoutMixin):
    def __init__(self, timeout=None):
        self.uid = None
        self.postings = []
        self.deferreds = []
        self.setTimeout(timeout)

    def add(self, posting):
        self.uid = posting["uid"]
        self.resetTimeout()
        result = Deferred()
        self.postings.append(posting)
        self.deferreds.append(result)
        return result

    def ready(self):
        # try to throw a COUNT_MISMATCH rather than a GROUP_TIMEOUT if the
        # counts are incorrect and we have postings coming in later
        max_count = max(posting["count"] for posting in self.postings)
        return len(self.postings) >= max_count

    def succeed(self):
        self.setTimeout(None)
        for deferred in self.deferreds:
            deferred.callback(True)

    def fail(self, exception):
        self.setTimeout(None)
        for deferred in self.deferreds:
            deferred.errback(exception)

    def timeoutConnection(self):
        log.err("Posting group with uid: %s timed out." % self.uid)
        log.err("Postings were:")
        for posting in self.postings:
            log.err(str(posting))
        self.fail(GROUP_TIMEOUT)

class Ledger:
    def __init__(self, engine, timeout=None):
        self.engine = engine
        self.pending = defaultdict(lambda: PostingGroup(timeout))

    def execute(self, *args, **kwargs):
        conn = self.engine.connect()
        count = 0
        while count < 10:
            try:
                result = conn.execute(*args, **kwargs)
                conn.close()
                return result
            except DBAPIError as e:
                if e.connection_invalidated:
                    log.err("Connection invalidated! Trying again - %s" % str(e))
                else:
                    log.err("Unable to execute query: %s %s: %s - trying again" % (args, kwargs, str(e)))

                conn = self.engine.connect()
                count += 1

        log.err("Tried to reconnect 10 times, no joy")
        raise DATABASE_ERROR

    @timed
    def atomic_commit(self, postings):

        start = time.time()
        log.msg("atomic commit called for %s at %f" % (postings, start))
        try:
            # sanity check
            if len(postings) == 0:
                raise INTERNAL_ERROR


            types = [posting["type"] for posting in postings]
            counts = [posting["count"] for posting in postings]

            if not all(type == types[0] for type in types):
                raise TYPE_MISMATCH
            if not all(count == counts[0] for count in counts):
                raise COUNT_MISMATCH

            # balance check
            debitsum = defaultdict(int)
            creditsum = defaultdict(int)

            log.msg("auditing postings at %f" % (time.time() - start))
            for posting in postings:
                if posting["direction"] == "debit":
                    debitsum[posting["contract"]] += posting["quantity"]
                if posting["direction"] == "credit":
                    creditsum[posting["contract"]] += posting["quantity"]

            for ticker in debitsum:
                if debitsum[ticker] - creditsum[ticker] is not 0:
                    raise QUANTITY_MISMATCH

            # create the journal and postings
            # The journal is created separately from the postings but this is ok because
            # all the postings are created at once. If the posting commit fails then we'll
            # just end up with an empty journal which won't break anything
            # TODO: Create the journal and postings together
            log.msg("creating the journal at %f" % (time.time() - start))
            ins = Journal.__table__.insert()

            result = self.execute(ins, type=types[0], timestamp=datetime.datetime.utcnow())

            journal_id = result.inserted_primary_key[0]

            log.msg("creating the db postings at %f" % (time.time() - start))
            db_postings = []
            for posting in postings:
                contract_table = Contract.__table__
                s = select([contract_table.c.id], contract_table.c.ticker==posting["contract"])
                result = self.execute(s)
                contract_id = result.first()[0]

                user_table = User.__table__
                s = select([user_table.c.type], user_table.c.username==posting["username"])
                result = self.execute(s)
                user_type = result.first()[0]

                username = posting["username"]
                quantity = posting["quantity"]
                direction = posting["direction"]
                note = posting["note"]
                if posting["timestamp"] is not None:
                    timestamp = util.timestamp_to_dt(posting["timestamp"])
                else:
                    timestamp = None

                if direction == 'debit':
                    if user_type == 'Asset':
                        sign = 1
                    else:
                        sign = -1
                else:
                    if user_type == 'Asset':
                        sign = -1
                    else:
                        sign = 1

                posting = {'username': username,
                           'contract_id': contract_id,
                           'quantity': sign * quantity,
                           'note': note,
                           'timestamp': timestamp,
                           'journal_id': journal_id
                }
                db_postings.append(posting)
                log.msg("done making posting at %f: %s" % (time.time() - start, posting))


            ins = Posting.__table__.insert()
            result = self.execute(ins, db_postings)
            log.msg("Inserted %d rows of %d postings" % (result.rowcount, len(db_postings)))
            log.msg("Done committing postings at %f" % (time.time() - start))


            return True

        except Exception, e:
            log.err("Caught exception trying to commit. Postings were:")
            for posting in postings:
                log.err(str(posting))
            log.err("Stack trace follows:")
            log.err()
            if isinstance(e, SQLAlchemyError):
                raise DATABASE_ERROR
            raise e

        finally:
            # We have a long running session object, so we must make sure it
            # is clean at all times. If there is an exception in the exception
            # handler, session.rollback() might not get called. This way it is
            # guaranteed to happen.
            # 
            # This is safe to run after a commit.
            pass

    def post_one(self, posting):
        uid = posting["uid"]
        group = self.pending[uid]

        # acquire the deferred we will return
        response = group.add(posting)
        
        # Note: it is important we do _not_ check the posting group for
        # consistency yet. Wait until we have them all.

        if group.ready():
            try:
                self.atomic_commit(group.postings)
                group.succeed()
            except Exception, e:
                group.fail(e)
            del self.pending[uid]
       
        return response

    def post(self, postings):
        # an empty postings list might mean an error caller side
        # return ARGUMENT_ERROR
        if len(postings) == 0:
            log.err("Received empty argument list.")
            raise ARGUMENT_ERROR

        # make sure all the postings have the same uid
        uids = [posting["uid"] for posting in postings]
        if not all(uid == uids[0] for uid in uids):
            raise UID_MISMATCH
        
        # at this point, all posting will succeed or fail simulatenously
        # return the first one
        deferreds = [self.post_one(posting) for posting in postings]
        return deferreds[0]


class AccountantExport(ComponentExport):
    def __init__(self, ledger):
        self.ledger = ledger
        ComponentExport.__init__(self, ledger)

    @export
    @schema("rpc/ledger.json#post")
    def post(self, *postings):
        return self.ledger.post(list(postings))

def create_posting(type, username, contract, quantity, direction, note=None, timestamp=None):
    if timestamp is None:
        timestamp = util.dt_to_timestamp(datetime.datetime.utcnow())

    return {"username":username, "contract":contract, "quantity":quantity,
            "direction":direction, "note": note, "type": type, "timestamp": timestamp}

if __name__ == "__main__":
    fo = log.startLogging(sys.stdout)
    fo.formatTime = lambda x: datetime.datetime.fromtimestamp(x).strftime("%Y-%m-%d %H:%M:%S.%f")
    engine = database.make_engine()
    timeout = config.getint("ledger", "timeout")
    ledger = Ledger(engine, timeout)
    accountant_export = AccountantExport(ledger)
    watchdog(config.get("watchdog", "ledger"))
    router_share_async(accountant_export,
            config.get("ledger", "accountant_export"))
    reactor.run()

