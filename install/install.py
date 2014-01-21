#!/usr/bin/python

import sys
import os
import string
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
        self.logfile = open("install.log", "a")

        self.here = os.path.dirname(os.path.abspath(__file__))
        self.git_root = os.path.abspath(os.path.join(here, ".."))
        self.templates = os.path.abspath(os.path.join(
                            self.git_root, "server/config"))

        self.parser = ConfigParser.ConfigParser()
        self.parser.set("DEFAULT", "git_root", self.git_root)
        self.parser.set("DEFAULT", "user", getpass.getuser())
        parsed = self.parser.read(os.path.join(profile, "profile.ini"))
        if len(parsed) != 1:
            raise Exception("Cannot read profile.")

        self.config = dict(self.parser.items("profile"))
        
        self.env = copy.copy(os.environ)
        self.env["DEBIAN_FRONTEND"] = "noninteractive"
        for key, value in self.config.iteritems():
            self.env["PROFILE_%s" % key] = value

    def log(self, line):
        self.logfile.write(line)
        self.logfile.flush()
        sys.stdout.write(line)
        sys.stdout.flush()

    def error(self, line):
        self.logfile.write(line)
        self.logfile.flush()
        sys.stderr.write(line)
        sys.stderr.flush()

    def get_template(self, name):
        return os.path.join(self.templates, name + ".template")

    def make_config(self):
        self.log("Creating config files.\n")

        # make supervisor.conf
        out = open("supervisor.conf", "w")
        with open(self.get_template("supervisor.conf")) as template_file:
            template = string.Template(template_file.read())
            out.write(template.substitute(self.config))
        if not self.parser.getboolean("profile", "disable_bitcoin"):
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
        if self.parser.getboolean("profile", "use_sqlite"):
            with open(self.get_template("sqlite.ini")) as template_file:
                template = string.Template(template_file.read())
                out.write(template.substitute(self.config))
        else:
            with open(self.get_template("postgres.ini")) as template_file:
                template = string.Template(template_file.read())
                out.write(template.substitute(self.config))
        out.close()

        # make bitcoin.conf
        if not self.parser.getboolean("profile", "disable_bitcoin"):
            out = open("bitcoin.conf", "w")
            with open(self.get_template("bitcoin.conf")) as template_file:
                template = string.Template(template_file.read())
                out.write(template.substitute(self.config))
            out.close()

    def check_dpkg(self, name):
        # we can actually query this using the python 'apt' module
        # however, this may not be installed and there is no good reason
        # to drag it in

        return self.run(["/usr/bin/dpkg", "-s", name]) == 0

    def install_dpkg(self, name):
        return self.run(["/usr/bin/apt-get", "-y", "install", name])

    def make_deps(self):
        self.log("Installing dependencies...\n")

        # make dpkg deps
        with open(os.path.join(self.profile, "deps", "dpkg")) as deps:
            for line in deps:
                package = line.strip()
                if not self.check_dpkg(package):
                    self.log("%s not installed. Installing... " % package)
                    self.install_dpkg(package)
                    if self.check_dpkg(package):
                        self.log("done.\n")
                    else:
                        self.log("failed.\n")
                        self.error("Error: unable to install %s.\n" % package)
                        self.abort()
                else:
                    self.log("%s installed.\n" % package)

        # make source deps
        # make python deps

    def run(self, args):
        p = subprocess.Popen(args, env=self.env, stdin=None,
                             stdout=self.logfile, stderr=self.logfile)
        p.communicate()
        return p.returncode

    def abort(self):
        self.logfile.close()
        sys.exit(1)

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

