ifndef PROFILE
export PROFILE=$(realpath install/profiles/git+postgres)
endif

.PHONY: config deps build install upgrade

all: config build

clean:
	rm -r dist

config:
	install/install.py config

deps:
	install/install.py deps

build:
	install/install.py build

upgrade:
	install/install.py upgrade

install: deps
	install/install.py install

tar: config build
	tar -cf sputnik.tar install dist Makefile

