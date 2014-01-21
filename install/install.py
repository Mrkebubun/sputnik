#!/usr/bin/python

import sys
import os
import copy
import subprocess
import optparse
import ConfigParser
import getpass

here = os.path.dirname(os.path.abspath(__file__))
lib = os.path.join(here, "lib")

env_path = os.environ.get("PYTHONPATH", "").split(":")
env_path.append(lib)
os.environ["PYTHONPATH"] = ":".join(env_path)
sys.path.append(lib)

class Installer:
    def __init__(self, profile=None):
        profile = profile or os.environ.get("PROFILE")
        if profile == None:
            raise Exception("No profile specified.")

        self.profile = profile
        self.logfile = None

        self.here = os.path.dirname(os.path.abspath(__file__))
        self.git_root = os.path.abspath(os.path.join(here, ".."))
        self.templates = os.path.abspath(os.path.join(
                            self.git_root, "server/config"))

        parser = ConfigParser.ConfigParser()
        parser.set("DEFAULT", "git_root", self.git_root)
        parser.set("DEFAULT", "user", getpass.getuser())
        parsed = parser.read(os.path.join(profile, "profile.ini"))
        if len(parsed) != 1:
            raise Exception("Cannot read profile.")

        self.config = dict(parser.items("profile"))
        
        self.env = copy.copy(os.environ)
        for key, value in self.config.iteritems():
            self.env["PROFILE_%s" % key] = value

    def get_template(name):
        return os.path.join(self.templates, name + ".template")

    def make_config(self):
        # make supervisor.conf
        out = open("supervisor.conf", "w")
        with open(self.get_template("supervisor.conf")) as template_file:
            template = string.Template(template_file.read())
            out.write(template.substitute(self.config))
        if not parser.getboolean("profile", "disable_bitcoin"):
            out.write("\n")
            with open(self.get_template("bitcoin.conf")) as template_file:
                template = string.Template(template_file.read())
                out.write(template.substitute(self.config))
        out.close()
        
        # make sputnik.ini
        out = open("sputnik.ini", "w")
        with open(self.get_template("sputnik.ini")) as template_file:
            template = string.Template(template_file.read())
            out.write(template.substitute(self.config))
        out.write("\n")
        if parser.getboolean("profile", "use_sqlite"):
            with open(self.get_template("sqlite.ini")) as template_file:
                template = string.Template(template_file.read())
                out.write(template.substitute(self.config))
        else:
            with open(self.get_template("postgres.ini")) as template_file:
                template = string.Template(template_file.read())
                out.write(template.substitute(self.config))
        out.close()

        # make bitcoin.conf
        if not parser.getboolean("profile", "disable_bitcoin"):
            out = open("bitcoin.conf", "w")
            with open(self.get_template("bitcoin.conf")) as template_file:
                template = string.Template(template_file.read())
                out.write(template.substitute(self.config))
            out.close()

    def run(self, args):
        p = subprocess.Popen(args, env=self.env, stdin=None,
                             stdout=self.logfile, stderr=self.logfile)
        p.communicate()
        if p.returncode != 0:
            raise Exception("Child exited with nonzero code.")

def main():
    usage = "usage: %prog [options] config|deps|build|install"
    opts = optparse.OptionParser(usage=usage)
    opts.add_option("-p", "--profile", dest="profile", help="Profile directory")
    (options, args) = opts.parse_args()

    if len(args) == 0:
        sys.stderr.write("Please specify a mode.\n")
        sys.stderr.flush()
        sys.exit(1)

    mode = args[0]
    
    try: 
        installer = Installer(options.profile)    
        
        if mode == "config":
            installer.make_config()
        elif mode == "deps":
            installer.make_deps()
        elif mode == "build":
            installer.make_build()
        elif mode == "install":
            installer.make_install()
        elif mode == "vars":
            for key, value in installer.config.iteritems():
                print "%s%s" % ((key + ":").ljust(20), value)
        else:
            sys.stderr.write("Install mode not recognized.\n")
            sys.stderr.flush()
            sys.exit(1)

    except Exception, e:
        sys.stderr.write(str(e) + "\n")
        sys.stderr.flush()
        sys.exit(1)

if __name__ == "__main__":
    main()

