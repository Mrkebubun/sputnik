ifndef PROFILE
export PROFILE=$(realpath install/profiles/git)
endif

install: config deps
	install/install.py install

config:
	install/install.py config

deps:
	install/install.py deps

