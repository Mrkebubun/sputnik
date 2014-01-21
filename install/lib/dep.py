#!/usr/bin/python

import os
import sys
import string
from optparse import OptionParser
from ConfigParser import ConfigParser

import config

usage = "usage: %prog [options] generate|read|env"
opts = OptionParser(usage=usage)
opts.add_option("-p", "--profile", dest="profile", help="Profile directory")
(options, args) = opts.parse_args()

profile=None

profile = options.profile or os.environ.get("PROFILE")
if not profile:
    sys.stderr.write("No profile specified.\n")
    sys.stderr.flush()
    sys.exit(1)

confdata = config.get_config(profile)
config.env(confdata)

if len(args) == 0:
    sys.stderr.write("Please specify a dependency set.\n")
    sys.stderr.flush()
    sys.exit(1)

mode = args[0]
if mode == "dpkg":
    pass
elif mode == "python":
    print os.environ
elif mode == "source":
    pass
else:
    sys.stderr.write("Dependency set not recognized.\n")
    sys.stderr.flush()
    sys.exit(1)

