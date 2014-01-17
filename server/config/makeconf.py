#!/usr/bin/python

from optparse import OptionParser

parser = OptionParser()
parser.add_option("--root", dest="ROOT", default="/srv/sputnik",
    help="Root of the sputnik tree.")
parser.add_option("--conf", dest="CONF", default="/srv/sputnik/conf",
    help="Location of config files.")
parser.add_option("--logs", dest="LOGS", default="/var/log/sputnik",
    help="Directory of sputnik logs.")
parser.add_option("--keys", dest="KEYS", default="/srv/sputnik/keys",
    help="Directory of sputnik keys.")
parser.add_option("--run", dest="RUN", default="/var/run/sputnik",
    help="Directory of sputnik runtime data.")
parser.add_option("--www", dest="WWW", default="/var/www",
    help="Directory of sputnik static web files.")
parser.add_option("--use-www", dest="ENABLE_WWW", default=False,
    action="store_true", help="Use sputnik's built-in www server.")
parser.add_option("--use-sqlite", dest="SQLITE", default=False,
    action="store_true", help="Use sqlite instead of postgres.")
parser.add_option("--sqlite", dest="DATABASE",
    default="/srv/sputnik/sputnik.db", help="Location of sqlite database.")
parser.add_option("--user", dest="USER", default="sputnik",
    help="User to run sputnik as.")
parser.add_option("--disable-bitcoin", dest="BITCOIN", default=False,
    action="store_true", help="Disable bitcoin and cashier functionality.")
(options, args) = parser.parse_args()
print options
