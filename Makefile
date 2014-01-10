SOURCE_ROOT = .
BUILD_ROOT = build
DEBUG_ROOT = $(BUILD_ROOT)/debug
DEPLOY_ROOT = $(BUILD_ROOT)/deploy

SOURCE_SERVER = $(SOURCE_ROOT)/server/sputnik
SOURCE_CONFIG = $(SOURCE_ROOT)/server/config
SOURCE_KEYS = $(SOURCE_ROOT)/server/keys
SOURCE_WWW = $(SOURCE_ROOT)/clients/www
SOURCE_TOOLS = $(SOURCE_ROOT)/tools
SOURCE_DEPS = $(SOURCE_ROOT)/install/deps

DEBUG_SERVER = $(DEBUG_ROOT)/server/sputnik
DEBUG_CONFIG = $(DEBUG_ROOT)/config
DEBUG_KEYS = $(DEBUG_ROOT)/keys
DEBUG_WWW = $(DEBUG_ROOT)/www
DEBUG_TOOLS = $(DEBUG_ROOT)/tools
DEBUG_DEPS = $(DEBUG_ROOT)/deps

DEPLOY_SERVER = $(DEPLOY_ROOT)/server/sputnik
DEPLOY_CONFIG = $(DEPLOY_ROOT)/config
DEPLOY_KEYS = $(DEPLOY_ROOT)/keys
DEPLOY_WWW = $(DEPLOY_ROOT)/www
DEPLOY_TOOLS = $(DEPLOY_ROOT)/tools
DEPLOY_DEPS = $(DEPLOY_ROOT)/deps

DEBUG_SERVER_FILES := $(patsubst $(SOURCE_SERVER)/%.py, $(DEBUG_SERVER)/%.py, $(wildcard $(SOURCE_SERVER)/*.py))
DEBUG_CONFIG_FILES = $(DEBUG_CONFIG)/debug.ini $(DEBUG_CONFIG)/supervisor.conf
DEBUG_KEYS_FILES = $(DEBUG_KEYS)/server.key $(DEBUG_KEYS)/server.crt
DEBUG_WWW_FILES := $(patsubst $(SOURCE_WWW)/%, $(DEBUG_WWW)/%, $(wildcard $(SOURCE_WWW)/*))
DEBUG_TOOLS_FILES = $(DEBUG_TOOLS)/leo.py
DEBUG_DEPS_FILES := $(DEBUG_DEPS)/dpkg-dependencies $(patsubst $(SOURCE_DEPS)/source-dependencies.debug/%, $(DEBUG_DEPS)/source-dependencies/%, $(wildcard $(SOURCE_DEPS)/source-dependencies.debug/*)) $(DEBUG_DEPS)/python-dependencies

DEPLOY_SERVER_FILES := $(patsubst $(SOURCE_SERVER)/%.py, $(DEPLOY_SERVER)/%.pyo, $(wildcard $(SOURCE_SERVER)/*.py))
DEPLOY_CONFIG_FILES = $(DEPLOY_CONFIG)/sputnik.ini $(DEPLOY_CONFIG)/supervisor.conf
DEPLOY_KEYS_FILES = $(DEPLOY_KEYS)/server.key $(DEPLOY_KEYS)/server.crt
DEPLOY_WWW_FILES := $(patsubst $(SOURCE_WWW)/%, $(DEPLOY_WWW)/%, $(wildcard $(SOURCE_WWW)/*))
DEPLOY_TOOLS_FILES = $(DEPLOY_TOOLS)/leo
DEPLOY_DEPS_FILES := $(DEPLOY_DEPS)/dpkg-dependencies $(patsubst $(SOURCE_DEPS)/source-dependencies.deploy/%, $(DEPLOY_DEPS)/source-dependencies/%, $(wildcard $(SOURCE_DEPS)/source-dependencies.deploy/*)) $(DEPLOY_DEPS)/python-dependencies

.INTERMEDIATE: $(SOURCE_TOOLS)/leo.pyo

all: sputnik.debug.tar.gz

sputnik.debug.tar.gz: debug
	cd $(DEBUG_ROOT); tar --numeric-owner --owner=0 --group=0 -czf ../$@ *

sputnik.deploy.tar.gz: deploy
	cd $(DEPLOY_ROOT); tar --numeric-owner --owner=0 --group=0 -czf ../$@ *

debug: $(DEBUG_SERVER_FILES) $(DEBUG_CONFIG_FILES) $(DEBUG_KEYS_FILES) $(DEBUG_WWW_FILES) $(DEBUG_TOOLS_FILES) $(DEBUG_DEPS_FILES) $(DEBUG_ROOT)/install.sh

deploy: $(DEPLOY_SERVER_FILES) $(DEPLOY_CONFIG_FILES) $(DEPLOY_KEYS_FILES) $(DEPLOY_WWW_FILES) $(DEPLOY_TOOLS_FILES) $(DEPLOY_DEPS_FILES) $(DEPLOY_ROOT)/install.sh

clean:
	rm -rf $(BUILD_ROOT)
	rm -f $(SOURCE_SERVER)/*.pyo
	rm -f $(SOURCE_TOOLS)/leo.pyo

$(SOURCE_SERVER)/%.pyo: $(SOURCE_SERVER)/%.py
	python -OO -m compileall -d "" -f $<

$(DEBUG_SERVER)/%.py: $(SOURCE_SERVER)/%.py
	install -D -m 0755 $< $@

$(DEPLOY_SERVER)/%.pyo: $(SOURCE_SERVER)/%.pyo
	install -D -m 0755 $< $@

$(DEBUG_CONFIG)/%: $(SOURCE_CONFIG)/%
	install -D -m 0644 $< $@

$(DEPLOY_CONFIG)/%: $(SOURCE_CONFIG)/deploy/%
	install -D -m 0644 $< $@

$(DEBUG_KEYS)/%.crt: $(SOURCE_KEYS)/%.crt
	install -D -m 0644 $< $@

$(DEBUG_KEYS)/%.key: $(SOURCE_KEYS)/%.key
	install -D -m 0600 $< $@

$(DEPLOY_KEYS)/%.crt: $(SOURCE_KEYS)/%.crt
	install -D -m 0644 $< $@

$(DEPLOY_KEYS)/%: $(SOURCE_KEYS)/%
	install -D -m 0600 $< $@

$(DEBUG_WWW)/%: $(SOURCE_WWW)/%
	install -D -m 0644 $< $@

$(DEPLOY_WWW)/%: $(SOURCE_WWW)/%
	install -D -m 0644 $< $@

$(SOURCE_TOOLS)/%.pyo: $(SOURCE_TOOLS)/%.py
	python -OO -m compileall -d "" -f $<

$(DEBUG_TOOLS)/%: $(SOURCE_TOOLS)/%
	install -D -m 0755 $< $@

$(DEPLOY_TOOLS)/%: $(SOURCE_TOOLS)/%.pyo
	install -D -m 0755 $< $@

$(DEBUG_DEPS)/%: $(SOURCE_DEPS)/%.debug
	install -D -m 0644 $< $@

$(DEBUG_DEPS)/source-dependencies/%: $(SOURCE_DEPS)/source-dependencies.debug/%
	install -D -m 0755 $< $@

$(DEPLOY_DEPS)/%: $(SOURCE_DEPS)/%.deploy
	install -D -m 0644 $< $@

$(DEPLOY_DEPS)/source-dependencies/%: $(SOURCE_DEPS)/source-dependencies.deploy/%
	install -D -m 0755 $< $@

$(DEBUG_ROOT)/install.sh: $(SOURCE_ROOT)/install/install.sh
	install -D -m 0755 $< $@

$(DEPLOY_ROOT)/install.sh: $(SOURCE_ROOT)/install/install.sh
	install -D -m 0755 $< $@

