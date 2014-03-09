HOST=$(shell hostname)
ifeq (${HOST},cube)
ifndef PROFILE
export PROFILE=$(realpath install/profiles/sputnik)
endif
endif

ifndef PROFILE
export PROFILE=$(realpath install/profiles/git+postgres)
endif

# TARGETS

.PHONY: config deps dist build install upgrade

all: dist

clean:
	rm -r dist

deps:
	install/install.py deps

config:
	install/install.py config

build:
	install/install.py build

dist: config build
	install/install.py dist

tar: dist
	mkdir -p .tar/sputnik/install/profiles
	cp -r dist .tar/sputnik
	cp -r ${PROFILE} .tar/sputnik/install/profiles
	cat Makefile > .tar/sputnik/Makefile

install: deps
	install/install.py install

upgrade:
	install/install.py upgrade

