ifndef PROFILE
export PROFILE=$(realpath install/profiles/git)
endif

.PHONY: config deps build install upgrade

all: config deps build

clean:
	rm dist/*

config:
	install/install.py config

deps:
	install/install.py deps

build:

upgrade: install

install:
	install/install.py install

