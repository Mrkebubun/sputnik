#!/usr/bin/python

import os
import argparse
import boto.ec2
import boto.cloudformation

class AutoDeployException(Exception): pass

INSTANCE_BROKEN = AutoDeployException("Instance is broken. Please check.")
INSTANCE_EXISTS = AutoDeployException("Instance already exists.")
INSTANCE_NOT_FOUND = AutoDeployException("Instance not found in region.")

class Instance:
    def __init__(self, client=None, region="us-west-1", profile=None, key=None):
        self.client = client
        self.region = region
        self.profile = profile
        self.key = key

        # Oddly, creating a connection does not raise an exception if the
        # region is invalid. It only returns None. We check here.
        if not boto.ec2.get_region(region):
            raise Exception("No such region: %s" % region)

        self.ec2 = boto.ec2.connect_to_region(region)
        self.cf = boto.cloudfront.connect_to_region(region)

        # default uninstalled state
        self.deployed = False
        self.broken = False
        self.key_present = False
        self.stack_present = False

        try:
            self.ec2.get_all_key_pairs(client)
            self.key_present = True
        except:
            pass

        try:
            stack = self.cf.describe_stacks(client)
            self.stack_present = True
        except:
            pass

        if self.key_present and not self.stack_present:
            self.broken = True

        if self.stack_present and not self.key_present:
            self.broken = True

        if self.key_present and self.stack_present:
            self.deployed = True

    def deploy(self):
        if self.broken:
            raise INSTANCE_BROKEN

        if self.deployed:
            raise INSTANCE_EXISTS

        with open("autodeploy.template") as template_file:
            template = template_file.read()

        print "Creating instance %s..." % self.client

        if os.path.isfile(self.key):
            print "\tuploading key..."
            with open(self.key, "rb") as key_file:
                material = key_file.read()
            self.ec2.import_key_pair(self.client, material)
        else:
            print "\tcreating and downloading key..."
            key = self.ec2.create_keypair(self.client)
            umask = os.umask(0177)
            with open(self.key, "wb") as key_file:
                key_file.write(key.material)
            os.umask(umask)
       
        print "\tcreating stack..."
        cf.create_stack(self.client, self.template,
                parameters=[("KeyName", self.client)])

        print "Instance %s created." % self.client


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

    def delete(self):
        if self.broken:
            response = raw_input("Delete broken instance %s? " % self.lient)
            if response is not "yes":
                print "Aborting."
                return
        else:
            response = raw_input("Delete instance %s? " % self.client)
            if response is not "yes":
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

parser = argparse.ArgumentParser(description="Deploy sputnik to AWS.")
parser.add_argument("--client", dest="client", action="store", required=True,
                    help="Short identifier for client.")
parser.add_argument("--region", dest="region", action="store",
                    default="us-west-1",
                    help="Region where to deploy. Default: us-west-1.")
subparsers = parser.add_subparsers(description="Actions that can be performed.",
                                   metavar="Available commands:",
                                   dest="command")
parser_deploy = subparsers.add_parser("deploy", help="Deploy instance.")
parser_deploy.add_argument("--profile", dest="profile", action="store",
                           required=True, help="Path to profile.")
parser_deploy.add_argument("--key", dest="key", action="store",
                            required=True,
                            help="Path to SSH key. If the key exists, it will be used. Otherwise, a new one will be generated.")
parser_upgrade = subparsers.add_parser("upgrade", help="Upgrade instance.")
parser_upgrade.add_argument("--profile", dest="profile", action="store",
                            required=True, help="Path to profile.")
parser_upgrade.add_argument("--key", dest="key", action="store",
                            required=True, help="Path to SSH key.")
parser_status = subparsers.add_parser("status", help="Query instance.")
parser_status.add_argument("--key", dest="key", action="store",
                           required=True, help="Path to SSH key.")
parser_delete = subparsers.add_parser("delete", help="Delete instance.")

kwargs = vars(parser.parse_args())
command = kwargs["command"]
del kwargs["command"]

instance = Instance(**kwargs)
method = getattr(instance, command)
method()

