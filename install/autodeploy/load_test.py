#!/usr/bin/env python
__author__ = 'sameer'

from autodeploy import Instance
import random
import string

if __name__ == "__main__":
    # Customer is random
    customer = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    # First create a sputnik install
    sputnik = Instance(customer=customer, profile="install/profiles/test", template="sputnik")

    # Deploy and install
    print "Deploying Sputnik on %s" % customer
    sputnik.deploy()
    sputnik.install()

    # Get publicDNS
    public_dns = sputnik.get_output("PublicDNS")

    # Now create a marketmaker
    mm_c = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    market_maker = Instance(customer=mm_c, template="loadtester")

    print "Deploying Market Maker on %s" % mm_c
    market_maker.deploy()
    market_maker.install_clients()
    market_maker.run("nohup clients/load_tester.py --market ws://%s:8000 >&/dev/null </dev/null &" % public_dns)

    qty = 100
    # Now create some clients
    randoms = []
    for i in range(qty):
        random_c = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        random_client = Instance(customer=random_c, template="loadtester")

        randoms.append(random_c)

        print "Deploying Random Client on %s" % random_c
        random_client.deploy()
        random_client.install_clients()
        random_client.run("nohup clients/load_tester.py --random ws://%s:8000 >&/dev/null </dev/null &" % public_dns)

    print "Sputnik: %s" % customer
    print "Market Maker: %s" % mm_c
    print "Randoms: %s" % randoms