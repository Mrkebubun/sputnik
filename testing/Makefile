TESTS=test_accountant test_administrator test_cashier test_ledger test_sputnik
TESTS_UI=test_ui
ALL=$(TESTS) $(TESTS_UI)

all: $(ALL)

ui: $(TESTS_UI)

no_ui: $(TESTS)

$(ALL):
	trial $@ 
