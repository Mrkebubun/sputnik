#!/usr/bin/python
#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

import datetime
import os
import signal

from supervisor.supervisorctl import ControllerPluginBase

# Add the following lines to supervisor.conf to enable:
#
# [ctlplugin:datestamp]
# supervisor.ctl_factory = datestamp.plugin:make_plugin
#

def increment(basename):
    tokens = basename.rsplit(".", 2)
    try:
        return tokens[0] + "." + str(int(tokens[1])+1)
    except (IndexError, ValueError):
        return basename + ".1"

def rotate(path):
    dirname, basename = os.path.split(path)
    rotate_to = os.path.join(dirname, increment(basename))
    if os.path.exists(rotate_to):
        rotate(rotate_to)
    os.rename(path, rotate_to)
        

def datestamp(path):
    # This script is intended to be run right after midnight.
    # Stamp the log with _yeesterday's_ date
    yesterday = datetime.datetime.today().date() - datetime.timedelta(1)
    rotate_to = path + "." + yesterday.isoformat()
    if os.path.exists(rotate_to):
        rotate(rotate_to)
    os.rename(path, rotate_to)


class DatestampControllerPlugin(ControllerPluginBase):
    def help_datestamp(self):
        self.ctl.output("datestamp\t Datestamp logs and rotate.")

    def do_datestamp(self, arg):
        supervisor = self.ctl.get_supervisor()
        try:
            processes = supervisor.getAllProcessInfo()
            for process in processes:
                stdout = datestamp(process["stdout_logfile"])
            pid = supervisor.getPID()
            os.kill(pid, signal.SIGUSR2)
        except Exception, e:
            self.ctl.output("Error rotating logs: %s" % e)


def make_plugin(controller, **config):
    return DatestampControllerPlugin(controller, **config)

