"""
config.py looks for configuration files in a number of places and reads them.

If you wish to provide a custom config file, use the reconfigure() method.
    In order for this to be useful, this module *must* be the first one
    imported and the configure method must be called before importing anything
    else.

Config variables can be accessed via the get() method.
"""

from os import path
from ConfigParser import ConfigParser

parser = ConfigParser()

def reconfigure(files):
    parser = SafeConfigParser()
    parser.read(files)    

def get(section, option, raw=False, vars=None):
    return parser.get(section, option, raw, vars)

def autoconfig():
    # Look for config files in order of preference.
    # parser.read can merge multiple config files. This can have undesired
    #   consequences in the program is not expecting it. So, stop as soon
    #   as a valid config file is found.

    local_debug = path.abspath("./debug.ini")
    local = path.abspath("./sputnik.ini")
    default_debug = path.abspath(path.join(path.dirname(__file__),
        "../config/debug.ini"))
    default = path.abspath(path.join(path.dirname(__file__),
        "../config/sputnik.ini"))

    config_files = [local_debug, local, default_debug, default]

    for filename in config_files:
        try:
            with open(filename) as fp:
                parser.readfp(fp)
            break
        except:
            pass

autoconfig()

