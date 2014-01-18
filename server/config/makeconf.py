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

substitutions = dict(parser.items("profile"))

# make supervisor.conf
config = open("supervisor.conf", "w")
templates = []
with open(os.path.join(here, "supervisor.conf.template")) as template_file:
    template = string.Template(template_file.read())
    config.write(template.substitute(substitutions))

if not parser.getboolean("profile", "disable_bitcoin"):
    config.write("\n")
    with open(os.path.join(here, "bitcoin.conf.template")) as template_file:
        template = string.Template(template_file.read())
        config.write(template.substitute(substitutions))

config.close()
    
# make sputnik.ini
config = open("sputnik.ini", "w")
templates = []
with open(os.path.join(here, "sputnik.ini.template")) as template_file:
    template = string.Template(template_file.read())
    config.write(template.substitute(substitutions))

config.write("\n")
if parser.getboolean("profile", "use_sqlite"):
    with open(os.path.join(here, "sqlite.ini.template")) as template_file:
        template = string.Template(template_file.read())
        config.write(template.substitute(substitutions))
else:
    with open(os.path.join(here, "postgres.ini.template")) as template_file:
        template = string.Template(template_file.read())
        config.write(template.substitute(substitutions))

config.close()

# make bitcoin.conf

if not parser.getboolean("profile", "disable_bitcoin"):
        config = open("bitcoin.conf", "w")
        templates = []
        with open(os.path.join(here, "bitcoin.conf.template")) as template_file:
            template = string.Template(template_file.read())
            config.write(template.substitute(substitutions))

        config.close()

