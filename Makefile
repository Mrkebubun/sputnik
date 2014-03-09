HOST=$(shell hostname)
ifeq (${HOST},cube)
ifndef PROFILE
export PROFILE=$(realpath install/profiles/sputnik)
endif
endif

ifndef PROFILE
export PROFILE=$(realpath install/profiles/git+postgres)
endif

.PHONY: config deps build install upgrade

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
	tar -cf sputnik.tar install dist Makefile

install:
	install/install.py install

upgrade:
	install/install.py upgrade

