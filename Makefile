#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

ifndef PROFILE
export PROFILE=$(realpath install/profiles/git)
endif

.PHONY: config deps dist build install upgrade

all: dist

clean:
	rm -rf dist

build-deps:
	install/install.py build-deps

deps:
	install/install.py deps

config:
	install/install.py config

build:
	install/install.py build

dist: config build
	install/install.py dist

test:
	cd testing && make no_ui

clients_tar:
	mkdir -p .tar/clients
	cp -r clients/python/* .tar/clients
	cd .tar && tar -cf ../clients.tar clients
	rm -r .tar
    
tar: dist
	install/install.py tar

install: deps
	install/install.py install

upgrade: deps 
	install/install.py upgrade

