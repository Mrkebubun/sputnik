ifndef PROFILE
export PROFILE=$(realpath install/profiles/git)
endif

.PHONY: dist config deps build install upgrade

all: config build

clean:
	rm -r dist

dist:
	mkdir -p dist

config: dist
	install/install.py config

deps:
	install/install.py deps

build: dist
	install/install.py build

upgrade: install

install: deps
	install/install.py install

