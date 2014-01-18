ifndef PROFILE
PROFILE=$(realpath install/profiles/git)
endif

config:
	cd dist && ../server/config/makeconf.py $(PROFILE)/profile.ini

