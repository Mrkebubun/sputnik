import sys
import boto.ec2
import boto.cloudformation

name = "test" # sys.argv[1]
region = "us-west-1" # sys.argv[2]
with open("autodeploy.template") as template_file:
    template = template_file.read()

ec2 = boto.ec2.connect_to_region(region)
cf = boto.cloudformation.connect_to_region(region)

key = ec2.create_key_pair(name)
key.save("./")

cf.create_stack(name, template, parameters=[("KeyName", name)])

