#!/usr/bin/python

import sys
import os
import optparse

here = os.path.dirname(os.path.abspath(__file__))
lib = os.path.join(here, "lib")

env_path = os.environ.get("PYTHONPATH", "").split(":")
env_path.append(lib)
os.environ["PYTHONPATH"] = ":".join(env_path)
sys.path.append(lib)

import config

def main():
    usage = "usage: %prog [options] config|deps|build|install"
    opts = optparse.OptionParser(usage=usage)
    opts.add_option("-p", "--profile", dest="profile", help="Profile directory")
    (options, args) = opts.parse_args()

    profile=None

    profile = options.profile or os.environ.get("PROFILE")
    if not profile:
        sys.stderr.write("No profile specified.\n")
        sys.stderr.flush()
        sys.exit(1)
    
    confdata = config.get_config(profile)

    if len(args) == 0:
        sys.stderr.write("Please specify a mode.\n")
        sys.stderr.flush()
        sys.exit(1)

    mode = args[0]
    
    print confdata

if __name__ == "__main__":
    main()

