#!/usr/bin/python
__author__ = 'sameer'

import os
import sys
import argparse


sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
    "../server"))

from sputnik import config
from sputnik import database, models, util
from datetime import datetime
from sqlalchemy.orm.exc import NoResultFound
import time

parser = argparse.ArgumentParser(description="Audit the ledger")
parser.add_argument("-a", "--adjust", dest="adjust", action="store_true",
                    help="should we adjust positions", default=False)

kwargs = vars(parser.parse_args())
session = database.make_session()

adjust = kwargs['adjust']

if adjust:
    print "BE SURE EVERYTHING IS SHUT BEFORE RUNNING THIS PROGRAM"
    time.sleep(30)

# pre-fetch users and postings
print "pre-fetching"
users = session.query(models.User).all()
postings = session.query(models.Posting).all()

# Go through journal entries
journals = session.query(models.Journal)
total = journals.count()
print "%d journals to cover" % total
count = 0
for journal in journals:
    print "%d/%d" % (count, total)
    if not journal.audit:
        print "Error in Journal:\n%s" % journal
        # Make sure we don't do any adjustments if there is a basic problem like this
        adjust = False
    count += 1

# Go through positions
positions = session.query(models.Position)
total = positions.count()
print "%d positions to cover" % total
count = 0
for position in positions:
    print "%d/%d" % (count, total)
    contract = position.contract
    position_calculated, calculated_timestamp = util.position_calculated(position, session)
    difference = position.position - position_calculated
    if difference != 0:
        # Mention problem
        print "Audit failure for %s" % position
        timestamp = position.position_cp_timestamp or util.timestamp_to_dt(0)
        for posting in position.user.postings:
            if posting.contract_id == contract.id and posting.journal.timestamp > timestamp:
                print "\t%s" % posting

        # Run an adjustment
        if adjust:
            position.position = position_calculated
            position.position_checkpoint = position.position
            position.position_cp_timestamp = calculated_timestamp

            session.add(position)
            session.commit()
            print "Updated Position: %s" % position

    count += 1


