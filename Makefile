ifndef PROFILE
export PROFILE=$(realpath install/profiles/git)
endif

config:
	cd dist && ../install/lib/config generate

deps:
	install/install.sh deps
