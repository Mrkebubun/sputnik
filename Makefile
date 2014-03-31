HOST=$(shell hostname)
ifeq (${HOST},cube)
ifndef PROFILE
export PROFILE=$(realpath install/profiles/sputnik)
endif
endif

ifndef PROFILE
export PROFILE=$(realpath install/profiles/git)
endif

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
	sed -i "s/\(dbname = sputnik\).*/\1/" .tar/sputnik/dist/config/sputnik.ini
	cp install/install.py .tar/sputnik/install
	cp -r ${PROFILE} .tar/sputnik/install/profiles
	echo "export PROFILE=install/profiles/$(notdir ${PROFILE})" > .tar/sputnik/Makefile
	cat Makefile >> .tar/sputnik/Makefile
	cd .tar && tar -cf ../sputnik.tar sputnik
	rm -r .tar

install: deps
	install/install.py install

upgrade:
	install/install.py upgrade

