#!/usr/bin/python

import os
import sys
import threading
import time
import argparse
import boto.ec2
import boto.cloudformation
import random, string

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

class Instance:
    def __init__(self, client=None, region=None, profile=None, key=None,
            verbose=False, safety=False):
        self.client = client
        self.region = region
        self.profile = profile
        self.key = key
        self.verbose = verbose
        self.safety = safety

        self.default_region = "us-west-1"

        if not client:
            raise AutoDeployException("Client cannot be None.")
        
        # default uninstalled state
        self.deployed = False
        self.broken = False
        self.key_present = False
        self.stack_present = False

        self.searched = False
        self.found = False

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
                    if self._search(client):
                        self.region = r
                        break
            print
            self.searched = True
            if self.region:
                # we found what we wanted, and we are already connected
                return

        # we found nothing, default to Oregon
        region = region or self.default_region

        # Oddly, creating a connection does not raise an exception if the
        # region is invalid. It only returns None. We check here.
        if not boto.ec2.get_region(region):
            raise Exception("No such region: %s" % region)
            
        self._connect(region)
        self._search(client)

    def _connect(self, region):
        self.ec2 = boto.ec2.connect_to_region(region)
        self.cf = boto.cloudformation.connect_to_region(region)

    def _search(self, client):
        try:
            self.ec2.get_all_key_pairs(client)
            self.key_present = True
        except KeyboardInterrupt:
            raise
        except:
            pass

        try:
            self.stack = self.cf.describe_stacks(client)[0]
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

    def deploy(self):
        if self.broken:
            raise INSTANCE_BROKEN

        if self.deployed:
            raise INSTANCE_EXISTS
        
        if self.searched:
            if self.safety:
                raise AutoDeployException("Explicitly specify a region.")

        with open("autodeploy.template") as template_file:
            template = template_file.read()

        print "Creating instance for %s..." % self.client
        os.mkdir(self.client)

        key_filename = "%s/ssh_login_key.pem" % self.client
        if os.path.isfile(key_filename):
            raise AutoDeployException("Key file exists. Will not overwrite.")

        print "\tcreating and downloading key..."
        key = self.ec2.create_key_pair(self.client)
        umask = os.umask(0177)
        with open(key_filename, "w") as key_file:
            key_file.write(key.material)
        os.umask(umask)
       
        print "\tcreating stack..."
        self.db_password = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        self.cf.create_stack(self.client, template,
                parameters=[("KeyName", self.client),
                    ("DBPassword", self.db_password)])
        db_pass_filename = "%s/dbpassword.txt" % self.client
        with open(db_pass_filename, "w") as db_file:
            db_file.write(self.db_password)

        sys.stdout.write("Please wait (this may take a few minutes)... ")
        with Spinner():
            while True:
                self.stack = self.cf.describe_stacks(self.client)[0]
                if self.stack.stack_status == "CREATE_COMPLETE":
                    break
                elif self.stack.stack_status == "CREATE_IN_PROGRESS":
                    time.sleep(10)
                else:
                    raise INSTANCE_BROKEN
        print
        print "Instance for %s created." % self.client
        for output in self.stack.outputs:
            if output.key == "InstanceId":
                 instance_id = output.value
                 break
        else:
            raise INSTANCE_BROKEN
        sys.stdout.write("Waiting for instance to boot (this may take a few minutes)... ")
        instance = self.ec2.get_all_instances(instance_id)[0].instances[0]
        with Spinner():
            while True:
                instance.update()
                if instance.state == "running":
                    output = instance.get_console_output().output
                    if output:
                        break
                    time.sleep(10)
                elif instance.state == "pending":
                    time.sleep(10)
                else:
                    raise INSTANCE_BROKEN
        print
        print "Instance %s booted." % instance_id
        output = instance.get_console_output().output.split("\n")
        for line in output:
            if line.startswith("ecdsa-sha2-nistp256 "):
                ssh_host_ecdsa_key = line.strip()
                server_key_filename = "%s/ssh_server_key.pub" % self.client
                with open(server_key_filename, "w") as key_file:
                    key_file.write(ssh_host_ecdsa_key)
                break
        else:
            raise INSTANCE_BROKEN

    def delete(self):
        if self.broken:
            response = raw_input("Delete broken instance %s? " % self.client)
            if response != "yes":
                print "Aborting."
                return
        else:
            response = raw_input("Delete instance %s? " % self.client)
            if response != "yes":
                print "Aborting."
                return

        print "Deleting instance %s..." % self.client

        if self.stack_present:
            print "\tremoving stack..."
            self.cf.delete_stack(self.client)
        
        if self.key_present:
            print "\tremoving key..."
            self.ec2.delete_key_pair(self.client)
        
        print "Instance %s removed." % self.client

    def status(self):
        if not self.found:
            raise INSTANCE_NOT_FOUND
      
        # self.stack should have been prepopulated by constructor
        print "Instance: %s" % self.client
        print "Region: %s" % self.region
        print "Stack Status: %s" % self.stack.stack_status
        if self.verbose:
            for event in self.stack.describe_events():
                status = event.resource_status
                reason = event.resource_status_reason
                if not reason:
                    reason = ""
                print "{0:25} {1:}".format("\t" + status, reason[:50])
                for i in range(50, len(reason), 50):
                    print " "*26 + reason[i:i+50]

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
                            fingerprint = line.strip().split(" ")[2]
                            print "ECDSA fingerprint: %s" % fingerprint
                            break
                else:
                    print "Public key: <not yet available>"
            except KeyboardInterrupt:
                raise
            except Exception, e:
                raise e

    def install(self):
        if self.broken:
            raise INSTANCE_BROKEN

        if not self.deployed:
            raise INSTANCE_NOT_FOUND

        raise NotImplemented

    def upgrade(self):
        if self.broken:
            raise INSTANCE_BROKEN

        if not self.deployed:
            raise INSTANCE_NOT_FOUND

        raise NotImplemented
    
    def query(self):
        if self.broken:
            raise INSTANCE_BROKEN
        
        if not self.deployed:
            raise INSTANCE_NOT_FOUND
        
        raise NotImplemented

parser = argparse.ArgumentParser(description="Deploy sputnik to AWS.")
client = argparse.ArgumentParser(add_help=False)
client.add_argument("client", action="store",
                    help="Short identifier for client.")
parser.add_argument("--region", dest="region", action="store",
                    help="Region where to deploy. Default: us-west-1.")
parser.add_argument("-v", "--verbose", dest="verbose", action="store_true")
subparsers = parser.add_subparsers(description="Actions that can be performed.",
                                   metavar="command",
                                   dest="command")
parser_deploy = subparsers.add_parser("deploy", parents=[client],
                                      help="Deploy instance.")
parser_status = subparsers.add_parser("status", parents=[client],
                                      help="Get instance deployment status.")
parser_delete = subparsers.add_parser("delete", parents=[client],
                                      help="Delete instance.")
parser_install = subparsers.add_parser("install", parents=[client],
                                       help="Install instance.")
parser_install.add_argument("--profile", dest="profile", action="store",
                            required=True, help="Path to profile.")
parser_install.add_argument("--key", dest="key", action="store",
                            required=True, help="Path to SSH key.")
parser_upgrade = subparsers.add_parser("upgrade", parents=[client],
                                       help="Upgrade instance.")
parser_upgrade.add_argument("--profile", dest="profile", action="store",
                            required=True, help="Path to profile.")
parser_upgrade.add_argument("--key", dest="key", action="store",
                            required=True, help="Path to SSH key.")
parser_query = subparsers.add_parser("query", parents=[client],
                                     help="Query running instance for version.")
parser_query.add_argument("--key", dest="key", action="store",
                          required=True, help="Path to SSH key.")

kwargs = vars(parser.parse_args())
command = kwargs["command"]
del kwargs["command"]

instance = Instance(**kwargs)
method = getattr(instance, command)

try:
    method()
except AutoDeployException, e:
    print e

