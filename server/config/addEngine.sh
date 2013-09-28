#! /bin/bash

# the ticker of the new contract is the command line arg

echo  "
[program:engine_$1]
command = /srv/sputnik/server/pepsi/engine.py -c /srv/sputnik/server/config/debug.ini $1
autorestart = true
exitcodes = 0
user = www-data
redirect_stderr = true
stdout_logfile = /srv/sputnik/logs/%(program_name)s.log
directory = /srv/sputnik/server/pepsi" >> 

/home/ 

/sputnik/server/config/supervisor.conf

echo "
[program:engine_$1]
command = /home/jonathan/sputnik/server/pepsi/engine.py -c /home/jonathan/sputnik/server/config/debug.ini $1
autorestart = true
exitcodes = 0
user = jonathan
redirect_stderr = true
stdout_logfile = /home/jonathan/sputnik/logs/%(program_name)s.log
directory = /home/jonathan/sputnik/server/pepsi" >> /etc/supervisor/conf.d/sputnik.conf
