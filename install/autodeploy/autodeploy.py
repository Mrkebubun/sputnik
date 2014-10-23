#!/usr/bin/python

import os
import sys
import threading
import time
import argparse
import boto.ec2
import boto.cloudformation
import random
import string
import pty

import fabric.api

fabric.api.env.reject_unknown_hosts = True
fabric.api.env.disable_known_hosts = True
# Do not abort on failures. We will do this manually.
fabric.api.env.warn_only = True
# Hack to make paramiko try ecdsa first.
# Otherwise, it fails when an rsa key is not found.
from paramiko.transport import Transport

Transport._preferred_keys = ('ecdsa-sha2-nistp256', 'ssh-rsa', 'ssh-dss')

import ConfigParser
import cStringIO

from os.path import join

class Spinner:
    def __enter__(self):
        self.event = threading.Event()
        self.thread = threading.Thread(target=self.spin)
        self.thread.daemon = True
        self.thread.start()
        return self.event, self.thread

    def __exit__(self, type, value, traceback):
        self.event.set()
        self.thread.join()

    def spin(self):
        states = ["|", "/", "-", "\\"]
        current = 0
        while True:
            sys.stdout.write(states[current])
            sys.stdout.flush()
            self.event.wait(0.5)
            sys.stdout.write("\b \b")
            sys.stdout.flush()
            current += 1
            current %= len(states)
            if self.event.isSet():
                break


class AutoDeployException(Exception): pass


INSTANCE_BROKEN = AutoDeployException("Instance is broken. Please check.")
INSTANCE_EXISTS = AutoDeployException("Instance already exists.")
INSTANCE_NOT_FOUND = AutoDeployException("Instance not found.")
INSTANCE_NOT_READY = AutoDeployException("Instance not ready.")
COMMAND_FAILED = AutoDeployException("Command failed.")
PROFILE_NOT_SET = AutoDeployException("Profile not set.")


class Instance:
    def __init__(self, customer=None, region=None, profile=None,
                 key=None, verbose=False, safety=False, template=None,
                 remote_command=None):
        self.customer = customer
        self.region = region
        if profile == None:
            profile = "awsrds"
        self.base_profile = profile
        self.template = template
        self.key = key
        self.verbose = verbose
        self.safety = safety
        self.remote_command = remote_command

        self.default_region = "us-west-1"

        if not customer:
            raise AutoDeployException("Customer cannot be None.")

        self.prefix = "/srv/autodeploy/%s" % self.customer
        self.key_filename = join(self.prefix, "ssh_login_key.pem")
        self.db_pass_filename = join(self.prefix, "dbpassword.txt")
        self.server_key_filename = join(self.prefix, "ssh_server_key.pub")
        self.profile_dir = join(self,prefix, "profile", self.customer)
        self.profile_ini = join(self.profile_dir, "profile.ini")
        self.server_ssl_key_dir = join(self,profile_dir, "keys")

        # default uninstalled state
        self.deployed = False
        self.broken = False
        self.key_present = False
        self.stack_present = False
        self.ready = False  # ssh accessible

        self.searched = False
        self.found = False

        self.stack = None
        self.instance = None

        if not region:
            # search for the instance
            sys.stdout.write("Searching... (use --region to specify a region) ")
            with Spinner():
                regions = map(lambda r: r.name, boto.ec2.regions())
                if self.default_region in regions:
                    # try to make searching faster
                    regions.remove(self.default_region)
                    regions.insert(0, self.default_region)
                for r in regions:
                    self._connect(r)
                    if self._search(customer):
                        self.region = r
                        break
            print
            self.searched = True
            if self.region:
                # we found what we wanted, and we are already connected
                return self._ready()

        # we found nothing, default to Oregon
        region = region or self.default_region

        # Oddly, creating a connection does not raise an exception if the
        # region is invalid. It only returns None. We check here.
        if not boto.ec2.get_region(region):
            raise Exception("No such region: %s" % region)

        self._connect(region)
        self._search(customer)
        self._ready()

    def _connect(self, region):
        self.ec2 = boto.ec2.connect_to_region(region)
        self.cf = boto.cloudformation.connect_to_region(region)

    def _search(self, customer):
        try:
            self.ec2.get_all_key_pairs(customer)
            self.key_present = True
        except KeyboardInterrupt:
            raise
        except:
            pass

        try:
            self.stack = self.cf.describe_stacks(customer)[0]
            self.stack_present = True
            if self.stack.stack_status != "CREATE_COMPLETE":
                self.broken = True
        except KeyboardInterrupt:
            raise
        except:
            pass

        if self.key_present and not self.stack_present:
            self.broken = True

        if self.stack_present and not self.key_present:
            self.broken = True

        if self.key_present or self.stack_present:
            self.found = True

        if self.key_present and self.stack_present:
            self.deployed = True

        return self.found

    def _ready(self):
        if not self.deployed:
            return

        try:
            instance_id = self.get_output("InstanceId")
            self.instance = self.ec2.get_all_instances(
                instance_id)[0].instances[0]
        except:
            self.broken = True
            return

        if not os.path.isfile(self.key_filename):
            self.broken = True
            return

        self.ip = self.instance.ip_address
        fabric.api.env.user = "ubuntu"
        fabric.api.env.host_string = self.ip
        fabric.api.env.system_known_hosts = self.server_key_filename
        fabric.api.env.key_filename = self.key_filename

        self.ready = True

    def deploy(self):
        if self.broken:
            raise INSTANCE_BROKEN

        if self.deployed:
            raise INSTANCE_EXISTS

        if self.searched:
            if self.safety:
                raise AutoDeployException("Explicitly specify a region.")

        with open("%s.template" % self.template) as template_file:
            template = template_file.read()

        print "Creating instance for %s..." % self.customer
        try:
            os.mkdir(self.prefix)
        except OSError:
            print "Warning: %s already exists" % self.prefix
        
        try:
            os.makedirs(self.profile_dir)
        except OSError:
            print "Warning: %s already exists" % self.profile_dir

        if os.path.isfile(self.key_filename):
            raise AutoDeployException("Key file exists. Will not overwrite.")

        print "\tcreating and downloading key..."
        key = self.ec2.create_key_pair(self.customer)
        umask = os.umask(0177)
        with open(self.key_filename, "w") as key_file:
            key_file.write(key.material)
        os.umask(umask)

        print "\tgenerating database password..."
        self.db_password = ''.join(random.choice(
            string.ascii_uppercase + string.digits) for _ in range(8))
        umask = os.umask(0177)
        with open(self.db_pass_filename, "w") as db_file:
            db_file.write(self.db_password)
        os.umask(umask)

        print "\tcreating stack..."
        self.cf.create_stack(self.customer, template,
                             parameters=[("KeyName", self.customer),
                                         ("DBPassword", self.db_password),
                                         ("CustomerName", self.customer)])

        sys.stdout.write("Please wait (this may take a few minutes)... ")
        with Spinner():
            while True:
                self.stack = self.cf.describe_stacks(self.customer)[0]
                if self.stack.stack_status == "CREATE_COMPLETE":
                    break
                elif self.stack.stack_status == "CREATE_IN_PROGRESS":
                    time.sleep(10)
                else:
                    raise INSTANCE_BROKEN
        print
        print "Instance for %s created." % self.customer
        instance_id = self.get_output("InstanceId")

        sys.stdout.write("Waiting for instance to boot (this may take a few minutes)... ")
        instance = self.ec2.get_all_instances(instance_id)[0].instances[0]
        with Spinner():
            while True:
                instance.update()
                if instance.state == "running":
                    break
                elif instance.state == "pending":
                    time.sleep(10)
                else:
                    raise INSTANCE_BROKEN
        print
        print "Instance %s booted." % instance_id
        sys.stdout.write("Waiting for console output (this may take a few minutes)... ")
        with Spinner():
            while True:
                output = instance.get_console_output().output
                if output:
                    break
                time.sleep(10)
        print
        print "Instance %s ready." % instance_id
        output = instance.get_console_output().output.split("\n")
        for line in output:
            if line.startswith("ecdsa-sha2-nistp256 "):
                ssh_host_ecdsa_key = line.strip()
                with open(self.server_key_filename, "w") as key_file:
                    key_file.write("%s %s" % \
                                   (instance.ip_address, ssh_host_ecdsa_key))
                break
        else:
            raise INSTANCE_BROKEN

    def delete(self):
        if self.broken:
            response = raw_input("Delete broken instance %s? " % self.customer)
            if response != "yes":
                print "Aborting."
                return
        else:
            response = raw_input("Delete instance %s? " % self.customer)
            if response != "yes":
                print "Aborting."
                return

        print "Deleting instance %s..." % self.customer

        if self.stack_present:
            print "\tremoving stack..."
            self.cf.delete_stack(self.customer)

        if self.key_present:
            print "\tremoving key..."
            self.ec2.delete_key_pair(self.customer)

        print "Instance %s removed." % self.customer

    def get_output(self, key):
        for output in self.stack.outputs:
            if output.key == key:
                return output.value

        raise INSTANCE_BROKEN

    def get_db_pass(self):
        with open(self.db_pass_filename, "r") as f:
            db_pass = f.readline()

        return db_pass

    def status(self):
        if not self.found:
            raise INSTANCE_NOT_FOUND

        # self.stack should have been prepopulated by constructor
        print "Instance: %s" % self.customer
        print "Region: %s" % self.region
        if not self.stack:
            print "Stack not found."
            return
        print "Stack Status: %s" % self.stack.stack_status
        if self.verbose:
            for event in self.stack.describe_events():
                status = event.resource_status
                reason = event.resource_status_reason
                if not reason:
                    reason = ""
                print "{0:25} {1:}".format("\t" + status, reason[:50])
                for i in range(50, len(reason), 50):
                    print " " * 26 + reason[i:i + 50]

        instance_id = None
        for output in self.stack.outputs:
            print "%s: %s" % (output.key, output.value)
            if output.key == "InstanceId":
                instance_id = output.value
        if instance_id:
            try:
                reservation = self.ec2.get_all_instances(instance_id)[0]
                instance = reservation.instances[0]
                print "Instance State: %s" % instance.state
                output = instance.get_console_output().output.split("\n")
                if output:
                    for line in output:
                        # anything that small better be ECDSA
                        # TODO: find a more reliable way to do this
                        if line.startswith("ec2: 256 "):
                            self.fingerprint = line.strip().split(" ")[2]
                            print "ECDSA fingerprint: %s" % self.fingerprint
                            break
                else:
                    print "Public key: <not yet available>"
            except KeyboardInterrupt:
                raise
            except Exception, e:
                raise e

    def check(self):
        if self.broken:
            raise INSTANCE_BROKEN

        if not self.deployed:
            raise INSTANCE_NOT_FOUND

        if not self.ready:
            raise INSTANCE_NOT_READY

    def install_clients(self):
        self.check()

        context = fabric.api.hide("everything")
        if self.verbose:
            context = fabric.api.show("everything")

        with context:
            here = os.path.dirname(os.path.abspath(__file__))
            git_root = os.path.abspath(os.path.join(here, "..", ".."))
            with fabric.api.lcd(git_root):
                result = fabric.api.local("make clients_tar")
                if result.failed:
                    raise COMMAND_FAILED

                result = fabric.api.put("clients.tar")
                if result.failed:
                    raise COMMAND_FAILED

                result = fabric.api.run("tar xf clients.tar")
                if result.failed:
                    raise COMMAND_FAILED

    def run(self):
        self.check()
        context = fabric.api.hide("everything")
        if self.verbose:
            context = fabric.api.show("everything")

        with context:
            result = fabric.api.run(self.remote_command)
            if result.failed:
                raise COMMAND_FAILED


    def install(self, upgrade=False):
        self.check()

        context = fabric.api.hide("everything")
        if self.verbose:
            context = fabric.api.show("everything")

        with context:
            here = os.path.dirname(os.path.abspath(__file__))
            git_root = os.path.abspath(os.path.join(here, "..", ".."))
            with fabric.api.lcd(git_root):
                print "Cleaning..."
                result = fabric.api.local("make clean")
                if result.failed:
                    raise COMMAND_FAILED

                parser = ConfigParser.SafeConfigParser()
                parser.read(self.profile_ini)
                if not parser.has_section("meta"):
                    parser.add_section("meta")
                parser.set("meta", "name", self.customer)
                parser.set("meta", "description", "")
                parser.set("meta", "inherits", self.base_profile)
                if not parser.has_section("profile"):
                    parser.add_section("profile")
                parser.set("profile", "dbhost", self.get_output("DbAddress"))
                parser.set("profile", "dbport", self.get_output("DbPort"))
                parser.set("profile", "dbmasterpw", self.get_db_pass())

                # If there are no keys, turn off SSL and use the AWS DNS
                if not (os.path.isfile(os.path.join(self.server_ssl_key_dir, "server.key"))
                        and os.path.isfile(os.path.join(self.server_ssl_key_dir, "server.cert"))
                        and os.path.isfile(os.path.join(self.server_ssl_key_dir, "server.chain"))):
                    parser.set("profile", "use_ssl", "no")
                    parser.set("profile", "webserver_address", self.get_output("PublicDNS"))
                    parser.set("profile", "base_uri", "ws://%s:8000" % self.get_output("PublicDNS"))
                    parser.set("profile", "webserver_port", "8888")
                    parser.set("profile", "use_www", "yes")
                    print "http://%s:8888" % self.get_output("PublicDNS")

                with open(self.profile_ini, "w") as f:
                    parser.write(f)

                print "Generating tarball..."
                result = fabric.api.local("PROFILE=%s make tar" % \
                        self.profile_dir)
                if result.failed:
                    raise COMMAND_FAILED

                print "Uploading distribution..."
                result = fabric.api.put("sputnik.tar", "sputnik.tar")
                if result.failed:
                    raise COMMAND_FAILED

            result = fabric.api.run("rm -rf sputnik")
            if result.failed:
                raise COMMAND_FAILED

            result = fabric.api.run("tar xf sputnik.tar")
            if result.failed:
                raise COMMAND_FAILED

            with fabric.api.cd("sputnik"):
                if upgrade:
                    print "Upgrading..."
                    action = "upgrade"
                else:
                    print "Installing..."
                    action = "install"

                result = fabric.api.sudo("make deps %s" % action)
                if result.failed:
                    fabric.api.get("dist/install.log", "./install.log")
                    raise COMMAND_FAILED

    def upgrade(self):
        self.install(True)

    def query(self):
        self.check()

        context = fabric.api.hide("everything")
        if self.verbose:
            context = fabric.api.show("everything")

        with context:
            result = fabric.api.run(
                "cat /srv/sputnik/server/config/sputnik.ini")
            if result.failed:
                raise COMMAND_FAILED

        parser = ConfigParser.SafeConfigParser()
        parser.readfp(cStringIO.StringIO(result))
        print "Git hash: %s" % parser.get("version", "git_hash")

    def login(self):
        if self.broken:
            raise INSTANCE_BROKEN

        if not self.deployed:
            raise INSTANCE_NOT_FOUND

        if not self.ready:
            raise INSTANCE_NOT_READY

        fabric.api.open_shell()

    @staticmethod
    def list(region=None):
        if region == None:
            regions = map(lambda r: r.name, boto.ec2.regions())
            for region in regions:
                Instance.list(region)
            return

        try:
            ec2 = boto.ec2.connect_to_region(region)
            cf = boto.cloudformation.connect_to_region(region)
            keys = map(lambda key: key.name, ec2.get_all_key_pairs())
            stacks = map(lambda stack: stack.stack_name, cf.describe_stacks())
            instances = set()
            instances.update(keys)
            instances.update(stacks)

            print "Region: %s" % region
            for instance in instances:
                print "\t%s" % instance
        except:
            print "Could not connect to %s" % region


def main():
    parser = argparse.ArgumentParser(description="Deploy sputnik to AWS.")
    customer = argparse.ArgumentParser(add_help=False)
    customer.add_argument("customer", action="store",
                          help="Short identifier for customer.")
    parser.add_argument("--region", dest="region", action="store",
                        help="Region where to deploy. Default: us-west-1.")
    parser.add_argument("-v", "--verbose", dest="verbose", action="store_true")
    subparsers = parser.add_subparsers(
        description="Actions that can be performed.", metavar="command",
        dest="command")
    parser_deploy = subparsers.add_parser("deploy", parents=[customer],
                                          help="Deploy instance.")
    parser_deploy.add_argument("--template", dest="template", action="store",
                               default="sputnik", required=False,
                               help="Which AWS template to use")
    parser_status = subparsers.add_parser("status", parents=[customer],
                                          help="Get instance deployment status.")
    parser_delete = subparsers.add_parser("delete", parents=[customer],
                                          help="Delete instance.")
    parser_install = subparsers.add_parser("install", parents=[customer],
                                           help="Install instance.")
    parser_install.add_argument("--profile", dest="profile", action="store",
                                required=False, help="Path to profile.")
    parser_upgrade = subparsers.add_parser("upgrade", parents=[customer],
                                           help="Upgrade instance.")
    parser_upgrade.add_argument("--profile", dest="profile", action="store",
                                required=False, help="Path to base profile.")
    parser_query = subparsers.add_parser("query", parents=[customer],
                                         help="Query running instance for version.")
    parser_login = subparsers.add_parser("login", parents=[customer],
                                         help="Login via ssh.")
    parser_list = subparsers.add_parser("list", help="List existing instances.")
    parser_install_clients = subparsers.add_parser("install_clients", parents=[customer],
                                                   help="Install python clients")
    parser_run = subparsers.add_parser("run", help="Run a command", parents=[customer])
    parser_run = parser_run.add_argument("remote_command",
                                         help="what is the remote command to run")


    kwargs = vars(parser.parse_args())
    command = kwargs["command"]
    del kwargs["command"]

    if command == "list":
        return Instance.list(kwargs.get("region", None))

    instance = Instance(**kwargs)
    method = getattr(instance, command)

    try:
        method()
    except AutoDeployException, e:
        print e


if __name__ == "__main__":
    main()

