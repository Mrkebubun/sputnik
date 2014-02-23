#!/usr/bin/python

import sys
import os
import shutil
import fnmatch
import string
import copy
import subprocess
import optparse
import ConfigParser
import getpass
import compileall

# __file__ may be a relative path, and this causes problem when we chdir
__file__ = os.path.abspath(__file__)

class Installer:
    def __init__(self, profile=None):
        if profile == None:
            raise Exception("No profile specified.")

        self.profile = profile
        self.logfile = open("install.log", "a")

        self.here = os.path.dirname(os.path.abspath(__file__))
        self.git_root = os.path.abspath(os.path.join(self.here, ".."))
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
            self.env["profile_%s" % key] = value

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
        
        shutil.rmtree("config", True)
        os.mkdir("config")

        # make supervisor.conf
        out = open("config/supervisor.conf", "w")
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
        out = open("config/sputnik.ini", "w")
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
            out = open("config/bitcoin.conf", "w")
            with open(self.get_template("bitcoin.conf")) as template_file:
                template = string.Template(template_file.read())
                out.write(template.substitute(self.config))
            out.close()

    def check_dpkg(self, name):
        # We can actually query this using the python 'apt' module.
        # However, this may not be installed and there is no good reason
        # to drag it in.

        return self.run(["/usr/bin/dpkg", "-s", name]) == 0

    def check_source(self, name):
        return self.run([os.path.join(self.profile, "deps", "source", name),
            "check"]) == 0

    def check_python(self, name):
        # We can query packages using the pip module.

        # import pip _now_ since it may not exist at script launch
        import pip
        import pip.req
        import pkg_resources

        # if we installed a package, this is out of date
        reload(pkg_resources)

        req = pip.req.InstallRequirement.from_line(name)
        req.check_if_exists()
        return req.satisfied_by != None

    def install_dpkg(self, name):
        return self.run(["/usr/bin/apt-get", "-y", "install", name])

    def install_source(self, name):
        return self.run([os.path.join(self.profile, "deps", "source", name),
            "install"])

    def install_python(self, name):
        return self.run(["/usr/bin/pip", "install", name])

    def make_deps(self):
        self.log("Installing dependencies...\n")

        # make dpkg deps
        self.log("Installing dpkg dependencies...\n")
        try:
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
                            self.error("Error: unable to install %s.\n" %
                                        package)
                            self.abort()
                    else:
                        self.log("%s installed.\n" % package)
        except IOError:
            self.log("No dpkg dependencies found.")

        # make source deps
        self.log("Installing source dependencies...\n")
        try: 
            for line in sorted(os.listdir(
                    os.path.join(self.profile, "deps", "source"))):
                package = line.strip()
                if not self.check_source(package):
                    package_name = package.lstrip("0123456789-")
                    self.log("%s not installed. Installing... " % package_name)
                    self.install_source(package)
                    if self.check_source(package):
                        self.log("done.\n")
                    else:
                        self.log("failed.\n")
                        self.error("Error: unable to install %s.\n" %
                            package_name)
                        self.abort()
                else:
                    self.log("%s installed.\n" % package)
        except OSError:
            self.log("No source dependencies found.\n")

        # make python deps
        self.log("Installing python dependencies...\n")
        try:
            with open(os.path.join(self.profile, "deps", "python")) as deps:
                for line in deps:
                    package = line.strip()
                    if not self.check_python(package):
                        self.log("%s not installed. Installing... " % package)
                        self.install_python(package)
                        if self.check_python(package):
                            self.log("done.\n")
                        else:
                            self.log("failed.\n")
                            self.error("Error: unable to install %s.\n" %
                                        package)
                            self.abort()
                    else:
                        self.log("%s installed.\n" % package)
        except IOError:
            self.log("No python dependencies found.\n")

    def make_build(self):
        if not self.config.get("pycompiled"):
            return

        # make build directory
        build_root = os.path.join(self.git_root, "dist", "build")
        build_server = os.path.join(build_root, "server", "sputnik")
        shutil.rmtree(build_server, True)

        # byte-compile compile
        server_source = os.path.join(self.git_root, "server", "sputnik")
        compileall.compile_dir(server_source)
        
        # copy files
        def ignore(path, names):
            ignored = []
            for name in names:
                if not fnmatch.fnmatch(name, "*.pyc"):
                    ignored.append(name)
            return ignored
        shutil.copytree(server_source, build_server, ignore=ignore)

    def make_install(self):
        # do pre-install
        self.log("Running pre-install scripts...\n")
        try: 
            for line in sorted(os.listdir(
                    os.path.join(self.profile, "pre-install"))):
                script = line.strip()
                script_name = script.lstrip("0123456789-")
                script_path = os.path.join(self.profile, "pre-install", script)
                self.log("Running %s... " % script_name)
                if self.run([script_path]) == 0:
                    self.log("done.\n")
                else:
                    self.log("failed.\n")
                    self.error("Unable to run %s.\n" % script_name)
                    self.abort()
        except OSError:
            self.log("No pre-install scripts found.\n")
       
        # do install
        self.log("Running install scripts...\n")
        try: 
            for line in sorted(os.listdir(
                    os.path.join(self.profile, "install"))):
                script = line.strip()
                script_name = script.lstrip("0123456789-")
                script_path = os.path.join(self.profile, "install", script)
                self.log("Running %s... " % script_name)
                if self.run([script_path]) == 0:
                    self.log("done.\n")
                else:
                    self.log("failed.\n")
                    self.error("Unable to run %s.\n" % script_name)
                    self.abort()
        except OSError:
            self.log("No install scripts found.\n")

        # do post-install
        self.log("Running post-install scripts...\n")
        try: 
            for line in sorted(os.listdir(
                    os.path.join(self.profile, "post-install"))):
                script = line.strip()
                script_name = script.lstrip("0123456789-")
                script_path = os.path.join(self.profile, "post-install", script)
                self.log("Running %s... " % script_name)
                if self.run([script_path]) == 0:
                    self.log("done.\n")
                else:
                    self.log("failed.\n")
                    self.error("Unable to run %s.\n" % script_name)
                    self.abort()
        except OSError:
            self.log("No post-install scripts found.\n")

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

    profile = options.profile or os.environ.get("PROFILE")
    if profile:
        profile = os.path.abspath(profile)

    if len(args) == 0:
        sys.stderr.write("Please specify a mode.\n")
        sys.stderr.flush()
        sys.exit(1)

    mode = args[0]
    
    try: 
        # change to work directory
        here = os.path.dirname(os.path.abspath(__file__))
        dist = os.path.join(here, "..", "dist")      
 
        if not os.path.isdir(dist):
            os.mkdir(dist)
        os.chdir(os.path.join(here, "..", "dist"))

        installer = Installer(profile)    
        
        if mode == "config":
            installer.make_config()
        elif mode == "deps":
            installer.make_deps()
        elif mode == "build":
            installer.make_build()
        elif mode == "install":
            installer.make_install()
        elif mode == "upgrade":
            installer.env["UPGRADE"] = "upgrade"
            installer.make_install()
        elif mode == "vars":
            for key, value in installer.config.iteritems():
                print "%s%s" % ((key + ":").ljust(20), value)
        elif mode == "env":
            for key, value in installer.config.iteritems():
                print "export profile_%s=\"%s\"" % (key, value)
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

