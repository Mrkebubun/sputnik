#!/usr/bin/python
__author__ = 'sameer'

import os
import sys
import getpass

import string
import shlex
import textwrap
import autobahn.wamp1.protocol
import Crypto.Random.random

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
    "../server"))

from sputnik import config
from sputnik import database, models
from sqlalchemy.orm.exc import NoResultFound

session = database.make_session()
positions = session.query(models.Position).filter_by(description='User').all()
system_user = session.query(models.User).filter_by(username='system').one()

# which to adjust
# adjust = False
#adjust = 'positions'
#adjust = 'ledger'
adjust = True

def get_system_position(contract, description):
    try:
        position = session.query(models.Position).filter_by(
                user=system_user, contract=contract, description=description).one()
        return position
    except NoResultFound:
        print "Creating new position %s for %s on %s." % (description, system_user.username, contract.ticker)
        position = models.Position(system_user, contract, description=description)
        position.reference_price = 0
        session.add(position)
        return position

# Go through journal entries
journals = session.query(models.Journal).all()
for journal in journals:
    if not journal.audit:
        print "Error in Journal:\n%s" % journal
        # Make sure we don't do any adjustments if there is a basic problem like this
        adjust = False

# Go through positions
for position in positions:
    contract = position.contract
    difference = position.position - position.position_calculated
    if difference != 0:
        # Mention problem
        print "Audit failure for %s" % position
        for posting in position.postings:
            print "\t%s" % posting

        # Run an adjustment
        if adjust:
            choice = raw_input("Adjust P)osition or J)ournal:")
            if choice == 'P':
                position.position = position.position_calculated
                session.add(position)
                session.commit()
                print "Updated Position: %s" % position
            elif choice == 'J':
                credit = models.Posting(position, difference, 'credit', update_position=False)
                system_position = get_system_position(position.contract, 'Adjustment')
                debit = models.Posting(system_position, difference, 'debit')
                session.add_all([position, system_position, credit, debit])
                journal = models.Journal('Adjustment', [credit, debit])
                session.add(journal)
                session.commit()
                print journal




