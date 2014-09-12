ifndef PROFILE
export PROFILE=$(realpath install/profiles/git)
endif

.PHONY: config deps dist build install upgrade

all: dist

clean:
	rm -r dist

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

tar: dist
	mkdir -p .tar/sputnik/install/profiles
	cp -r dist .tar/sputnik
	mkdir -p .tar/sputnik/tools
	cp -r tools/alembic* .tar/sputnik/tools
	sed -i "s/\(dbname = sputnik\).*/\1/" .tar/sputnik/dist/config/sputnik.ini
	cp install/install.py .tar/sputnik/install
	cp -r install/profiles/minimal .tar/sputnik/install/profiles
	cp -r install/profiles/awsrds .tar/sputnik/install/profiles
	cp -r ${PROFILE} .tar/sputnik/install/profiles
	echo "export PROFILE=install/profiles/$(notdir ${PROFILE})" > .tar/sputnik/Makefile
	cat Makefile >> .tar/sputnik/Makefile
	cd .tar && tar -cf ../sputnik.tar sputnik
	rm -r .tar

install: deps
	install/install.py install

upgrade:
	install/install.py upgrade

