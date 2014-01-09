SOURCE_ROOT = .
BUILD_ROOT = build

SOURCE_SERVER = $(SOURCE_ROOT)/server/sputnik
SOURCE_CONFIG = $(SOURCE_ROOT)/server/config
SOURCE_WWW = $(SOURCE_ROOT)/clients/www
SOURCE_TOOLS = $(SOURCE_ROOT)/tools

BUILD_SERVER = $(BUILD_ROOT)/server/sputnik
BUILD_CONFIG = $(BUILD_ROOT)/server/config
BUILD_WWW = $(BUILD_ROOT)/www
BUILD_TOOLS = $(BUILD_ROOT)/tools

SERVER_FILES := $(patsubst $(SOURCE_SERVER)/%.py, $(BUILD_SERVER)/%.pyo, $(wildcard $(SOURCE_SERVER)/*.py))
CONFIG_FILES = $(BUILD_CONFIG)/sputnik.ini
WWW_FILES := $(patsubst $(SOURCE_WWW)/%, $(BUILD_WWW)/%, $(wildcard $(SOURCE_WWW)/*))
TOOLS_FILES = $(BUILD_TOOLS)/leo

.INTERMEDIATE: $(SOURCE_TOOLS)/leo.pyo

build: $(SERVER_FILES) $(CONFIG_FILES) $(WWW_FILES) $(TOOLS_FILES)

tar: sputnik.tar.gz

sputnik.tar.gz: build
	cd $(BUILD_ROOT); tar --numeric-owner --owner=0 --group=0 -czf \
		../sputnik.tar.gz *

clean:
	rm -rf $(BUILD_ROOT)
	rm -f $(SOURCE_SERVER)/*.pyo
	rm -f $(SOURCE_TOOLS)/leo.pyo

$(SOURCE_SERVER)/%.pyo: $(SOURCE_SERVER)/%.py
	python -OO -m compileall -d "" -f $<

$(BUILD_SERVER)/%.pyo: $(SOURCE_SERVER)/%.pyo
	install -D -m 0755 $< $@

$(BUILD_CONFIG)/sputnik.ini: $(SOURCE_CONFIG)/sputnik.ini
	install -D -m 0755 $(SOURCE_CONFIG)/sputnik.ini $(BUILD_CONFIG)/sputnik.ini

$(BUILD_WWW)/%: $(SOURCE_WWW)/%
	install -D -m 0644 $< $@

$(SOURCE_TOOLS)/leo.pyo: $(SOURCE_TOOLS)/leo.py
	python -OO -m compileall -d "" -f $<

$(BUILD_TOOLS)/leo: $(SOURCE_TOOLS)/leo.pyo
	install -D -m 0755 $< $@

