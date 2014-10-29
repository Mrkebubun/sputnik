#!/usr/bin/python

import sys
import os
import shutil
import fnmatch
import shlex
import string
import re
import copy
import subprocess
import optparse
import ConfigParser
import getpass
import compileall
import cStringIO
import tarfile
import tempfile

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
        self.upgrade = []
        
        self.profile_chain = []

        self.read_profile_dir(self.profile)
        self.read_config_status()
        self.read_aux_config()

    def resolve_profile_dir(self, target, base_profile=None):
        profile_store = os.path.join(self.git_root, "install", "profiles")
        search = []
        if base_profile:
            search.append(os.path.normpath(os.path.join(base_profile, target)))
        search.append(os.path.join(profile_store, target))
        for candidate in search:
            if os.path.isdir(candidate):
                if os.path.isfile(os.path.join(candidate, "profile.ini")):
                    return candidate
        raise Exception("Cannot find profile: %s." % target)

    def read_aux_config(self):
        parser = ConfigParser.SafeConfigParser()
        parsed = parser.read(os.path.join(self.profile, "aux.ini"))
        if len(parsed) != 1:
            return

        self.config.update(parser.items("aux"))

    def read_profile_dir(self, profile):
        profile = os.path.abspath(profile)
        if profile in self.cache:
            raise Exception("Profile dependency is circular.")
        self.cache.append(profile)

        self.profile_chain.append(profile)

        # while it would be nice, we cannot reuse the parser since we might
        # read a reference to a profile that must be parsed first
        parser = ConfigParser.SafeConfigParser()
        if "git_root" not in self.config:
            parser.set("DEFAULT", "git_root", self.git_root)

        # read profile.ini
        profile_ini = os.path.join(profile, "profile.ini")
        parsed = parser.read(profile_ini)
        if len(parsed) != 1:
            raise Exception("Cannot read profile.")

        # parent profiles must be parsed first
        if parser.has_option("meta", "inherits"):
            inherits = parser.get("meta", "inherits")
            for parent in shlex.split(inherits):
                self.read_profile_dir(self.resolve_profile_dir(parent, profile))

        # If these haven't been set anywhere upstream, default them
        if "user" not in self.config:
            parser.set("DEFAULT", "user", getpass.getuser())
        else:
            # If user has been set, set it so that the parser can use it
            parser.set("DEFAULT", "user", self.config['user'])

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
                    deps["source"].append((package_name, profile, package_path))
            except OSError:
                pass

        # read scripts
        for stage in ["pre-install", "install", "post-install", "upgrade"]:
            scripts = getattr(self, stage.replace("-", "_"))
            try:
                for line in sorted(os.listdir(os.path.join(profile, stage))):
                    script = line.strip()
                    script_name = script.lstrip("0123456789-")
                    script_path = os.path.join(profile, stage, script)
                    scripts.append((script_name, profile, script_path))
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

class Installer():
    def __init__(self, profile=None, git_root=None, dry_run=False):
        if profile == None:
            raise Exception("No profile specified.")

        self.here = os.path.dirname(os.path.abspath(__file__))
        self.git_root = git_root or \
                os.path.abspath(os.path.join(self.here, ".."))
        self.templates = os.path.abspath(os.path.join(
                            self.git_root, "server/config"))

        self.logfile = open("install.log", "a")

        self.profile = Profile(profile, self.git_root)
        self.config = self.profile.config
        
        self.env = copy.copy(os.environ)
        self.env["DEBIAN_FRONTEND"] = "noninteractive"
        for key, value in self.config.iteritems():
            self.env["profile_%s" % key] = value

        self.dry_run = dry_run

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

    def enabled(self, option):
        if option not in self.config:
            raise Exception("Missing required option: %s." % option)
        value = self.config.get(option, False)
        if value.lower() in ["1", "yes", "true", "on"]:
            return True
        if value.lower() in ["0", "no", "false", "off"]:
            return False
        raise ValueError("Not a boolean: %s" % value)

    def make_template(self, template_name, out, **kwargs):
        with open(self.get_template(template_name)) as template_file:
            template = string.Template(template_file.read())
            config = copy.copy(self.config)
            config.update(kwargs)
            try:
                out.write(template.substitute(config))
            except KeyError, e:
                self.error("Template '%s' missing required key: %s.\n" %
                        (template_name, e.args[0]))
                self.abort()
        out.write("\n")


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
        if self.dry_run:
            out = cStringIO.StringIO()
        else:
            out = open(os.path.join("config", "supervisor.conf"), "w")
        if self.enabled("bundle_supervisord"):
            self.make_template("supervisord.conf", out)

        self.make_template("supervisor.conf", out, engines_clean=self.config["engines"].replace('/', '_'))
        if not self.enabled("disable_bitcoin"):
            self.make_template("bitcoind.conf", out)
        for ticker in [x.strip() for x in self.config["engines"].split(',')]:
            self.make_template("engine.conf", out, raw_ticker=ticker,
                               clean_ticker=ticker.replace('/', '_'))

        out.close()
        
        # make sputnik.ini
        if self.dry_run:
            out = cStringIO.StringIO()
        else:
            out = open(os.path.join("config", "sputnik.ini"), "w")
        self.make_template("sputnik.ini", out)
        if self.enabled("use_sqlite"):
            self.make_template("sqlite.ini", out)
        else:
            self.make_template("postgres.ini", out)
        out.close()

        # make bitcoin.conf
        if not self.enabled("disable_bitcoin"):
            if self.dry_run:
                out = cStringIO.StringIO()
            else:
                out = open(os.path.join("config", "bitcoin.conf"), "w")
            self.make_template("bitcoin.conf", out)
            out.close()

        # make config.status
        if self.dry_run:
            out = cStringIO.StringIO()
        else:
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

    def check_source(self, (name, profile, path)):
        self.env["base_profile"] = profile
        result = self.run([path, "check"])
        del self.env["base_profile"]
        return result == 0

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

    def install_source(self, (name, profile, path)):
        self.env["base_profile"] = profile
        result = self.run([path, "install"])
        del self.env["base_profile"]
        return result

    def install_python(self, name):
        return self.run(["/usr/bin/pip", "install", name])

    def install_node(self, name):
        return self.run(["/usr/local/bin/npm", "install", "-g", name])

    def make_dep_stage(self, stage):
        prefix = ""
        deps = self.profile.deps
        if stage == "build":
            prefix = "build "
            deps = self.profile.build_deps

        self.log("Installing %sdependencies...\n" % prefix)

        # make dpkg deps
        self.log("Installing dpkg %sdependencies...\n" % prefix)
        for package in deps["dpkg"]:
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

        # make source deps
        self.log("Installing source %sdependencies...\n" % prefix)
        for package in deps["source"]:
            if not self.check_source(package):
                self.log("%s not installed. Installing... " % package[0])
                self.install_source(package)
                if self.check_source(package):
                    self.log("done.\n")
                else:
                    self.log("failed.\n")
                    self.error("Error: unable to install %s.\n" % package[0])
                    self.abort()
            else:
                self.log("%s installed.\n" % package[0])

        # make python deps
        self.log("Installing python %sdependencies...\n" % prefix)
        for package in deps["python"]:
            if not self.check_python(package):
                self.log("%s not installed. Installing... " % package)
                self.install_python(package)
                if self.check_python(package):
                    self.log("done.\n")
                else:
                    self.log("failed.\n")
                    self.error("Error: unable to install %s.\n" % package)
                    self.abort()
            else:
                self.log("%s installed.\n" % package)

        # make node deps
        self.log("Installing node %sdependencies...\n" % prefix)
        for package in deps["node"]:
            if not self.check_node(package):
                self.log("%s not installed. Installing... " % package)
                self.install_node(package)
                if self.check_node(package):
                    self.log("done.\n")
                else:
                    self.log("failed.\n")
                    self.error("Error: unable to install %s.\n" % package)
                    self.abort()
            else:
                self.log("%s installed.\n" % package)

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
        for script in getattr(self.profile, stage.replace("-", "_")):
            self.log("Running %s... " % script[0])
            self.env["base_profile"] = script[1]
            result = self.run([script[2]])
            del self.env["base_profile"]
            if result == 0:
                self.log("done.\n")
            else:
                self.log("failed.\n")
                self.error("Unable to run %s.\n" % script[0])
                self.abort()
       
    def make_dist(self):
        self.make_stage("pre-install")
 
    def make_install(self):
        self.make_stage("install")
        self.make_stage("post-install")

    def make_upgrade(self):
        self.make_stage("upgrade")
        self.make_stage("post-install")

    def make_tar(self):
        temp = tempfile.mkdtemp()
        sputnik = os.path.join(temp, "sputnik")
        
        # copy dist
        dist = os.path.join(self.git_root, "dist")
        shutil.copytree(dist, os.path.join(sputnik, "dist"))

        # copy profiles
        for profile in self.profile.profile_chain:
            shutil.copytree(profile, os.path.join(sputnik, "install", "profiles", os.path.basename(profile)))
       
        # touch up sputnik.ini
        ini_path = os.path.join(sputnik, "dist", "config", "sputnik.ini")
        with open(ini_path, 'r') as ini_file:
            lines = ini_file.readlines()
        with open(ini_path, 'w') as ini_file:
            for line in lines:
                ini_file.write(re.sub(r"^(dbname = sputnik).*", r"\1", line))

        # copy install.py and Makefile
        shutil.copy(os.path.join(self.git_root, "install", "install.py"), os.path.join(sputnik, "install", "install.py"))
        with open(os.path.join(self.git_root, "Makefile")) as makefile:
            make = makefile.read()
        with open(os.path.join(sputnik, "Makefile"), 'w') as makefile:
            name = os.path.basename(self.profile.profile)
            makefile.write("export PROFILE=install/profiles/%s\n" % name)
            makefile.write("\n")
            makefile.write(make)

        # make tar file
        cwd = os.getcwd()
        os.chdir(self.git_root)
        with tarfile.open("sputnik.tar", 'w') as tar:
            os.chdir(temp)
            tar.add("sputnik")
        os.chdir(cwd)

        # clean up
        shutil.rmtree(temp)

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
        if self.dry_run:
            return 0
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
    opts.add_option("-g", "--git-root", dest="git_root", help="Git root")
    opts.add_option("-d", "--dry-run", dest="dry_run", help="Dry run",
            action="store_true", default=False)
    (options, args) = opts.parse_args()

    profile = options.profile or os.environ.get("PROFILE")
    if profile:
        profile = os.path.abspath(profile)
        os.environ["PROFILE"] = profile

    git_root = options.git_root
    dry_run = options.dry_run

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

        installer = Installer(profile, git_root, dry_run)
        
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
        elif mode == "tar":
            installer.make_tar()
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

