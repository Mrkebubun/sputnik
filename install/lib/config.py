#!/usr/bin/python

import os
import sys
import string
import getpass
from optparse import OptionParser
from ConfigParser import ConfigParser

here = os.path.dirname(os.path.abspath(__file__))
git_root = os.path.abspath(os.path.join(here, "../.."))
templates = os.path.abspath(os.path.join(git_root, "server/config"))

def get_template(name):
    return os.path.join(templates, name + ".template")

def get_config(profile):
    parser = ConfigParser()
    parser.set("DEFAULT", "git_root", git_root)
    parser.set("DEFAULT", "user", getpass.getuser())
    parsed = parser.read(os.path.join(profile, "profile.ini"))
    if len(parsed) != 1:
        sys.stderr.write("Cannot read profile.\n")
        sys.stderr.flush()
        sys.exit(1)

    config = dict(parser.items("profile"))

    return config

def generate(config):
    # make supervisor.conf
    out = open("supervisor.conf", "w")
    with open(get_template("supervisor.conf")) as template_file:
        template = string.Template(template_file.read())
        out.write(template.substitute(config))

    if not parser.getboolean("profile", "disable_bitcoin"):
        out.write("\n")
        with open(get_template("bitcoin.conf")) as template_file:
            template = string.Template(template_file.read())
            out.write(template.substitute(config))

    out.close()
    
    # make sputnik.ini
    out = open("sputnik.ini", "w")
    with open(get_template("sputnik.ini")) as template_file:
        template = string.Template(template_file.read())
        out.write(template.substitute(config))

    out.write("\n")
    if parser.getboolean("profile", "use_sqlite"):
        with open(get_template("sqlite.ini")) as template_file:
            template = string.Template(template_file.read())
            out.write(template.substitute(config))
    else:
        with open(get_template("postgres.ini")) as template_file:
            template = string.Template(template_file.read())
            out.write(template.substitute(config))

    out.close()

    # make bitcoin.conf
    if not parser.getboolean("profile", "disable_bitcoin"):
        out = open("bitcoin.conf", "w")
        with open(get_template("bitcoin.conf")) as template_file:
            template = string.Template(template_file.read())
            out.write(template.substitute(config))

        out.close()

def read(config, name):
    try:
        print config[name]
    except:
        sys.stderr.write("Variable not found.\n")
        sys.stderr.flush()
        sys.exit(1)

def env(config):
    for key, value in config.iteritems():
        os.environ["PROFILE_%s" % key] = value

def print_env(config):
    for key, value in config.iteritems():
        print "export PROFILE_%s=\"%s\"" % (key, value)

if __name__ == "__main__" :
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

    config = get_config(profile)

    if len(args) == 0:
        sys.stderr.write("Please specify a mode.\n")
        sys.stderr.flush()
        sys.exit(1)

    mode = args[0]

    if mode == "generate":
        generate(config)        
    elif mode == "read":
        if len(args) != 2:
            sys.stderr.write("Which variable would you like?\n")
            sys.stderr.flush()
            sys.exit(1)
        read(config, args[1])
    elif mode == "env":
        print_env(config)
    else:
        sys.stderr.write("Mode not supported.\n")
        sys.stderr.flush()
        sys.exit(1)

