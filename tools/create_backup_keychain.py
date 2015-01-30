__author__ = 'sameer'

from sputnik.bitgo import create_keychain
from sys import argv
from pprint import pprint

if __name__ == "__main__":
    if len(argv) == 2:
        network = argv[1]
    else:
        network = "XTN"

    keychain = create_keychain(network)
    print """
Store the following backup keychain OFFLINE and in a SECURE LOCATION:

"""

    pprint(keychain)

    print """
Submit the following public key to the MultiSig Wallet Initialization form on the Sputnik administration interface:

"""

    print keychain['xpub']

