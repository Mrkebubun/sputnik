#!/usr/bin/python

import sys
import os
import shutil
import fnmatch
import shlex
import string
import copy
import subprocess
import optparse
import ConfigParser
import getpass
import compileall

# __file__ may be a relative path, and this causes problem when we chdir
__file__ = os.path.abspath(__file__)

class Profile:
    def __init__(self, profile, git_root=None):
        self.cache = []

        here = os.path.dirname(os.path.abspath(__file__))
        self.git_root = git_root or os.path.abspath(os.path.join(here, ".."))

        self.profile = os.path.abspath(profile)
        self.config = {}
        self.deps = {"dpkg":[], "python":[], "node":[], "source":[]}
        self.build_deps = {"dpkg":[], "python":[], "node":[], "source":[]}
        self.pre_install = []
        self.install = []
        self.post_install = []

        self.read_profile_dir(self.profile)
        self.read_config_status()

    def read_profile_dir(self, profile):
        profile = os.path.abspath(profile)
        if profile in self.cache:
            raise Exception("Profile dependency is circular.")
        self.cache.append(profile)

        # while it would be nice, we cannot reuse the parser since we might
        # read a reference to a profile that must be parsed first
        parser = ConfigParser.SafeConfigParser()
        parser.set("DEFAULT", "git_root", self.git_root)
        parser.set("DEFAULT", "user", getpass.getuser())
        # TODO: Do we need this?
        # self.parser.set("DEFAULT", "bitcoin_user", getpass.getuser())

        # read profile.ini
        profile_ini = os.path.join(profile, "profile.ini")
        parsed = parser.read(profile_ini)
        if len(parsed) != 1:
            raise Exception("Cannot read profile.")

        # parent profiles must be parsed first
        if parser.has_option("meta", "inherits"):
            inherits = parser.get("meta", "inherits")
            for parent in shlex.split(inherits):
                if "/" not in parent:
                    parent = os.path.join(profile, "..", parent)
                self.read_profile_dir(parent)

        # store profile information
        # for scripts, store the originating profile as well so we can run it
        #  in the correct context (for example, if the script needs access to
        #  resources from the original profile)

        # read dependencies
        for stage in ["deps", "build-deps"]:
            deps = getattr(self, stage.replace("-", "_"))
            for dep_type in ["dpkg", "python", "node"]:
                try:
                    with open(os.path.join(profile, stage, dep_type)) \
                            as dep_list:
                        for line in dep_list:
                            package = line.strip()
                            deps[dep_type].append(package)
                except IOError:
                    pass
            try:
                for line in sorted(os.listdir(os.path.join(
                        profile, stage, "source"))):
                    package = line.strip()
                    package_name = package.lstrip("0123456789-")
                    package_path = os.path.join(
                            profile, stage, "source", package)
                    deps["source"].append((profile, package_name, package_path))
            except OSError:
                pass

        # read scripts
        for stage in ["pre-install", "install", "post-install"]:
            scripts = getattr(self, stage.replace("-", "_"))
            try:
                for line in sorted(os.listdir(os.path.join(profile, stage))):
                    script = line.strip()
                    script_name = script.lstrip("0123456789-")
                    script_path = os.path.join(profile, stage, script)
                    scripts.append((profile, script_name, script_path))
            except OSError:
                pass
       
        self.config.update(dict(parser.items("profile")))

    def read_config_status(self):
        config_status = os.path.join(self.git_root, "dist", "config.status")
        parser = ConfigParser.SafeConfigParser()
        parsed = parser.read(config_status)
        
        if len(parsed) == 1:
            for key in dict(parser.items("git")):
                # TODO: Is this necessary? What is wrong with update()?
                if key not in self.config:
                    self.config[key] = parser.get("git", key)
            dbname = "sputnik_" + self.config["git_branch"].replace("-", "_")
            self.config["dbname"] = dbname

class Installer:
    def __init__(self, profile=None, git_root=None):
        if profile == None:
            raise Exception("No profile specified.")

        self.profile = profile
        self.logfile = open("install.log", "a")

        self.here = os.path.dirname(os.path.abspath(__file__))
        self.git_root = os.path.abspath(os.path.join(self.here, ".."))
        self.templates = os.path.abspath(os.path.join(
                            self.git_root, "server/config"))

        self.parser = ConfigParser.SafeConfigParser()
        self.parser.set("DEFAULT", "git_root", self.git_root)
        self.parser.set("DEFAULT", "user", getpass.getuser())
        self.parser.set("DEFAULT", "bitcoin_user", getpass.getuser())
        profile_ini = os.path.join(profile, "profile.ini")
        config_status = os.path.join(self.git_root, "dist", "config.status")
        parsed = self.parser.read(profile_ini)
        if len(parsed) != 1:
            raise Exception("Cannot read profile.")
        parsed = self.parser.read(config_status)

        self.config = dict(self.parser.items("profile"))
        if len(parsed) == 1:
            for key in dict(self.parser.items("git")):
                if key not in self.config:
                    self.config[key] = self.parser.get("git", key)
            dbname = "sputnik_" + self.config["git_branch"].replace("-", "_")
            self.config["dbname"] = dbname
        
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
       
        version = self.version()
        self.config["git_hash"] = version[0]
        self.config["git_date"] = version[1]
        self.config["git_tag"] = version[2]
        self.config["git_branch"] = version[3]
        self.config["dbname"] = "sputnik_" + version[3].replace("-", "_")

        shutil.rmtree("config", True)
        os.mkdir("config")

        # make supervisor.conf
        out = open("config/supervisor.conf", "w")
        if self.parser.getboolean("profile", "bundle_supervisord"):
            with open(self.get_template("supervisord.conf")) as template_file:
                template = string.Template(template_file.read())
                out.write(template.substitute(self.config))
        with open(self.get_template("supervisor.conf")) as template_file:
            template = string.Template(template_file.read())
            out.write(template.substitute(self.config))
        if not self.parser.getboolean("profile", "disable_bitcoin"):
            out.write("\n")
            with open(self.get_template("bitcoind.conf")) as template_file:
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

        # make config.status
        out = open("config.status", "w")
        status = ConfigParser.SafeConfigParser()
        status.add_section("git")
        status.set("git", "git_hash", version[0])
        status.set("git", "git_date", version[1])
        status.set("git", "git_tag", version[2])
        status.set("git", "git_branch", version[3])
        status.write(out)
        out.close()

    def check_dpkg(self, name):
        # We can actually query this using the python 'apt' module.
        # However, this may not be installed and there is no good reason
        # to drag it in.

        return self.run(["/usr/bin/dpkg", "-s", name]) == 0

    def check_source(self, name, stage="deps"):
        return self.run([os.path.join(self.profile, stage, "source", name),
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

    def check_node(self, name):
        # we can use npm to check for packages, but this works too,
        # and does not require grep'ing for the name in the output
        return self.run(["/usr/local/bin/node", "-e",
            "'require(\"%s\")'" % name]) == 0

    def install_dpkg(self, name):
        return self.run(["/usr/bin/apt-get", "-y", "install", name])

    def install_source(self, name):
        return self.run([os.path.join(self.profile, "deps", "source", name),
            "install"])

    def install_python(self, name):
        return self.run(["/usr/bin/pip", "install", name])

    def install_node(self, name):
        return self.run(["/usr/local/bin/npm", "install", "-g", name])

    def make_dep_stage(self, stage):
        stage_name = stage + " "
        if stage == "deps":
            stage_name = ""
        stage_dir = stage
        if stage == "build":
            stage_dir = "build-deps"
        self.log("Installing %sdependencies...\n" % stage_name)

        # make dpkg deps
        self.log("Installing dpkg %sdependencies...\n" % stage_name)
        try:
            with open(os.path.join(self.profile, stage_dir, "dpkg")) as deps:
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
            self.log("No dpkg %sdependencies found.\n" % stage_name)

        # make source deps
        self.log("Installing source %sdependencies...\n" % stage_name)
        try: 
            for line in sorted(os.listdir(
                    os.path.join(self.profile, stage_dir, "source"))):
                package = line.strip()
                if not self.check_source(package, stage_dir):
                    package_name = package.lstrip("0123456789-")
                    self.log("%s not installed. Installing... " % package_name)
                    self.install_source(package)
                    if self.check_source(package, stage_dir):
                        self.log("done.\n")
                    else:
                        self.log("failed.\n")
                        self.error("Error: unable to install %s.\n" %
                            package_name)
                        self.abort()
                else:
                    self.log("%s installed.\n" % package)
        except OSError:
            self.log("No source %sdependencies found.\n" % stage_name)

        # make python deps
        self.log("Installing python %sdependencies...\n" % stage_name)
        try:
            with open(os.path.join(self.profile, stage_dir, "python")) as deps:
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
            self.log("No python %sdependencies found.\n" % stage_name)

        # make node deps
        self.log("Installing node %sdependencies...\n" % stage_name)
        try:
            with open(os.path.join(self.profile, stage_dir, "node")) as deps:
                for line in deps:
                    package = line.strip()
                    if not self.check_node(package):
                        self.log("%s not installed. Installing... " % package)
                        self.install_node(package)
                        if self.check_node(package):
                            self.log("done.\n")
                        else:
                            self.log("failed.\n")
                            self.error("Error: unable to install %s.\n" %
                                        package)
                            self.abort()
                    else:
                        self.log("%s installed.\n" % package)
        except IOError:
            self.log("No node %sdependencies found.\n" % stage_name)

    def make_deps(self):
        self.make_dep_stage("deps")

    def make_build_deps(self):
        self.make_dep_stage("build")

    def make_build(self):
        if not self.config.get("pycompiled"):
            return

        # make build directory
        build_root = os.path.join(self.git_root, "dist", "build")
        build_server = os.path.join(build_root, "server", "sputnik")
        build_tools = os.path.join(build_root, "tools")
        shutil.rmtree(build_server, True)
        shutil.rmtree(build_tools, True)

        # byte-compile compile
        server_source = os.path.join(self.git_root, "server", "sputnik")
        tools_source = os.path.join(self.git_root, "tools")
        compileall.compile_dir(server_source)
        compileall.compile_dir(tools_source)
        
        # copy files
        def ignore(path, names):
            ignored = []
            for name in names:
                if not fnmatch.fnmatch(name, "*.pyc"):
                    ignored.append(name)
            return ignored
        shutil.copytree(server_source, build_server, ignore=ignore)
        shutil.copytree(tools_source, build_tools, ignore=ignore)

    def make_stage(self, stage):
        # do stage
        self.log("Running %s scripts...\n" % stage)
        try: 
            for line in sorted(os.listdir(
                    os.path.join(self.profile, stage))):
                script = line.strip()
                script_name = script.lstrip("0123456789-")
                script_path = os.path.join(self.profile, stage, script)
                self.log("Running %s... " % script_name)
                if self.run([script_path]) == 0:
                    self.log("done.\n")
                else:
                    self.log("failed.\n")
                    self.error("Unable to run %s.\n" % script_name)
                    self.abort()
        except OSError:
            self.log("No %s scripts found.\n" % stage)
       
    def make_dist(self):
        self.make_stage("pre-install")
 
    def make_install(self):
        self.make_stage("install")
        self.make_stage("post-install")

    def make_upgrade(self):
        self.make_stage("upgrade")
        self.make_stage("post-install")

    def version(self):
        p = subprocess.Popen(
                ["/usr/bin/git", "log", "--pretty=format:%H%n%aD", "-1"],
                stdin=None, stdout=subprocess.PIPE,
                stderr=self.logfile)
        hash = p.stdout.readline().rstrip()
        date = p.stdout.readline().rstrip()
        p = subprocess.Popen(["/usr/bin/git", "describe", "--always", "--tags"],
                             stdin=None, stdout=subprocess.PIPE,
                             stderr=self.logfile)
        tag = p.stdout.readline().rstrip()
        p = subprocess.Popen(["/usr/bin/git", "rev-parse", "--abbrev-ref",
                              "HEAD"], stdin=None, stdout=subprocess.PIPE,
                              stderr=self.logfile)
        branch = p.stdout.readline().rstrip()
        return [hash, date, tag, branch]

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
        os.environ["PROFILE"] = profile

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
        os.chdir(dist)

        installer = Installer(profile)    
        
        if mode == "config":
            installer.make_config()
        elif mode == "build-deps":
            installer.make_build_deps()
        elif mode == "deps":
            installer.make_deps()
        elif mode == "build":
            installer.make_build()
        elif mode == "dist":
            installer.make_dist()
        elif mode == "install":
            installer.make_install()
        elif mode == "upgrade":
            installer.env["UPGRADE"] = "upgrade"
            installer.make_upgrade()
        elif mode == "vars":
            for key, value in installer.config.iteritems():
                print "%s%s" % ((key + ":").ljust(20), value)
        elif mode == "env":
            for key, value in installer.config.iteritems():
                print "export profile_%s=\"%s\"" % (key, value)
        elif mode == "version":
            print installer.version()
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

