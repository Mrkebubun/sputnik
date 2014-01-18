#!/usr/bin/python

import sys
import string
from ConfigParser import ConfigParser

parser = ConfigParser()
parser.read(sys.argv[1])

substitutions = dict(parser.items("profile"))

# make supervisor.conf
config = open("supervisor.conf", "w")
templates = []
with open("supervisor.conf.template") as template_file:
    template = string.Template(template_file.read())
    config.write(template.substitute(substitutions))

if not parser.getboolean("profile", "disable-bitcoin"):
    config.write("\n")
    with open("bitcoin.conf.template") as template_file:
        template = string.Template(template_file.read())
        config.write(template.substitute(substitutions))

config.close()
    
# make sputnik.ini
config = open("sputnik.ini", "w")
templates = []
with open("sputnik.ini.template") as template_file:
    template = string.Template(template_file.read())
    config.write(template.substitute(substitutions))

config.write("\n")
if parser.getboolean("profile", "use-sqlite"):
    with open("sqlite.ini.template") as template_file:
        template = string.Template(template_file.read())
        config.write(template.substitute(substitutions))
else:
    with open("postgres.ini.template") as template_file:
        template = string.Template(template_file.read())
        config.write(template.substitute(substitutions))

config.close()

# make bitcoin.conf

if not parser.getboolean("profile", "disable-bitcoin"):
        config = open("bitcoin.conf", "w")
        templates = []
        with open("bitcoin.conf.template") as template_file:
            template = string.Template(template_file.read())
            config.write(template.substitute(substitutions))

        config.close()

