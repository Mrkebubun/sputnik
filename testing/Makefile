#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

TESTS=test_accountant test_administrator test_cashier test_ledger test_engine test_sputnik test_zmq_util test_margin test_fees
TESTS_UI=test_ui
ALL=$(TESTS) $(TESTS_UI)

all: $(ALL)

ui: $(TESTS_UI)

no_ui: $(TESTS)

clean:
	rm -rf .coverage* htmlcov _trial_temp

report:
	/usr/local/bin/coverage combine
	/usr/local/bin/coverage html
    
$(ALL):
	/usr/local/bin/coverage run -p --branch --source ../server/sputnik `which trial` $@
