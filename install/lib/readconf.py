#!/usr/bin/python

import os
import sys
import string
from ConfigParser import ConfigParser

here = os.path.dirname(os.path.abspath(__file__))
git_root = os.path.abspath(os.path.join(here, "../.."))

parser = ConfigParser()
parser.set("DEFAULT", "git_root", git_root)
parser.read(sys.argv[1])

print parser.get("profile", sys.argv[2])

