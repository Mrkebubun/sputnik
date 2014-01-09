SOURCE_ROOT = .
DEBUG_ROOT = debug
BUILD_ROOT = build

SOURCE_SERVER = $(SOURCE_ROOT)/server/sputnik
SOURCE_CONFIG = $(SOURCE_ROOT)/server/config
SOURCE_WWW = $(SOURCE_ROOT)/clients/www
SOURCE_TOOLS = $(SOURCE_ROOT)/tools

DEBUG_SERVER = $(DEBUG_ROOT)/server/sputnik
DEBUG_CONFIG = $(DEBUG_ROOT)/server/config
DEBUG_WWW = $(DEBUG_ROOT)/www
DEBUG_TOOLS = $(DEBUG_ROOT)/tools

BUILD_SERVER = $(BUILD_ROOT)/server/sputnik
BUILD_CONFIG = $(BUILD_ROOT)/server/config
BUILD_WWW = $(BUILD_ROOT)/www
BUILD_TOOLS = $(BUILD_ROOT)/tools

DEBUG_SERVER_FILES := $(patsubst $(SOURCE_SERVER)/%.py, $(DEBUG_SERVER)/%.py, $(wildcard $(SOURCE_SERVER)/*.py))
DEBUG_CONFIG_FILES = $(DEBUG_CONFIG)/debug.ini $(DEBUG_CONFIG)/supervisor.conf
DEBUG_WWW_FILES := $(patsubst $(SOURCE_WWW)/%, $(DEBUG_WWW)/%, $(wildcard $(SOURCE_WWW)/*))
DEBUG_TOOLS_FILES = $(DEBUG_TOOLS)/leo.py

SERVER_FILES := $(patsubst $(SOURCE_SERVER)/%.py, $(BUILD_SERVER)/%.pyo, $(wildcard $(SOURCE_SERVER)/*.py))
CONFIG_FILES = $(BUILD_CONFIG)/sputnik.ini $(BUILD_CONFIG)/supervisor.conf
WWW_FILES := $(patsubst $(SOURCE_WWW)/%, $(BUILD_WWW)/%, $(wildcard $(SOURCE_WWW)/*))
TOOLS_FILES = $(BUILD_TOOLS)/leo

.INTERMEDIATE: $(SOURCE_TOOLS)/leo.pyo

build: $(SERVER_FILES) $(CONFIG_FILES) $(WWW_FILES) $(TOOLS_FILES)
debug: $(DEBUG_SERVER_FILES) $(DEBUG_CONFIG_FILES) $(DEBUG_WWW_FILES) $(DEBUG_TOOLS_FILES)

sputnik.debug.tar.gz: debug
	cd $(DEBUG_ROOT); tar --numeric-owner --owner=0 --group=0 -czf \
		../sputnik.debug.tar.gz *

sputnik.tar.gz: build
	cd $(BUILD_ROOT); tar --numeric-owner --owner=0 --group=0 -czf \
		../sputnik.tar.gz *

clean:
	rm -rf $(DEBUG_ROOT)
	rm -rf $(BUILD_ROOT)
	rm -f $(SOURCE_SERVER)/*.pyo
	rm -f $(SOURCE_TOOLS)/leo.pyo

$(SOURCE_SERVER)/%.pyo: $(SOURCE_SERVER)/%.py
	python -OO -m compileall -d "" -f $<

$(DEBUG_SERVER)/%.py: $(SOURCE_SERVER)/%.py
	install -D -m 0755 $< $@

$(BUILD_SERVER)/%.pyo: $(SOURCE_SERVER)/%.pyo
	install -D -m 0755 $< $@

$(DEBUG_CONFIG)/%: $(SOURCE_CONFIG)/%
	install -D -m 0644 $< $@

$(BUILD_CONFIG)/%: $(SOURCE_CONFIG)/deploy/%
	install -D -m 0644 $< $@

$(DEBUG_WWW)/%: $(SOURCE_WWW)/%
	install -D -m 0644 $< $@

$(BUILD_WWW)/%: $(SOURCE_WWW)/%
	install -D -m 0644 $< $@

$(SOURCE_TOOLS)/%.pyo: $(SOURCE_TOOLS)/%.py
	python -OO -m compileall -d "" -f $<

$(DEBUG_TOOLS)/%: $(SOURCE_TOOLS)/%
	install -D -m 0755 $< $@

$(BUILD_TOOLS)/%: $(SOURCE_TOOLS)/%.pyo
	install -D -m 0755 $< $@

