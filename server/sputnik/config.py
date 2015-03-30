#!/usr/bin/python
#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

"""
config.py looks for configuration files in a number of places and reads them.

If you wish to provide a custom config file, use the reconfigure() method.
    In order for this to be useful, this module *must* be the first one
    imported and the configure method must be called before importing anything
    else.

Config variables can be accessed via the get() method.
"""

import sys
from os import path
from ConfigParser import ConfigParser


class AutoConfigParser(ConfigParser):
    def __init__(self, *args, **kwargs):
        """

        :param args:
        :param kwargs:
        """
        ConfigParser.__init__(self, *args, **kwargs)
        self.autoconfig_filename = None

        local = path.abspath("./sputnik.ini")
        root = path.abspath(path.join(path.dirname(__file__),
            "./server/config/sputnik.ini"))
        dist = path.abspath(path.join(path.dirname(__file__),
            "../../dist/config/sputnik.ini"))
        default = path.abspath(path.join(path.dirname(__file__),
            "../config/sputnik.ini"))

        self.autoconfig_files = [local, root, dist, default]

        self.autoconfig()

    def reset(self):
        """


        """
        self.autoconfig_filename = None
        for section in self.sections():
            self.remove_section(section)

    def reconfigure(self, files):
        """

        :param files:
        """
        self.reset()
        self.read(files)

    def autoconfig(self):
        # Look for config files in order of preference.
        # read() can merge multiple config files. This can have undesired
        #   consequences in the program is not expecting it. So, stop as soon
        #   as a valid config file is found.

        """


        """
        for filename in self.autoconfig_files:
            try:
                with open(filename) as fp:
                    self.readfp(fp)
                    self.autoconfig_filename = filename
                break
            except:
                pass

parser = AutoConfigParser()

if __name__ == "__main__":
    if parser.autoconfig_filename != None:
        print "Configuration file found at %s" % parser.autoconfig_filename
        print
        for section in parser.sections():
            print "[%s]" % section
            for pair in parser.items(section):
                print "%s = %s" % pair
            print
    else:
        print "No configuration file found. Tried:"
        for filename in parser.autoconfig_files:
            print filename
        print
else:
    sys.modules[__name__] = parser

