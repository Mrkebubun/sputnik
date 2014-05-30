TESTS=test_accountant test_administrator test_cashier test_ledger test_engine test_sputnik test_zmq_util
TESTS_UI=test_ui
ALL=$(TESTS) $(TESTS_UI)

all: $(ALL)

ui: $(TESTS_UI)

no_ui: $(TESTS)

clean:
	rm -rf .coverage* htmlcov _trial_temp

report:
	coverage combine
	coverage html

all_report: all report

no_ui_report: no_ui report
    
$(ALL):
	coverage run -p --branch --source ../server/sputnik `which trial` $@
