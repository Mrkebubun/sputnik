#! /bin/bash
ps aux | grep pepsiColaServer.py | awk '{print $2}' | xargs -I {} sudo kill -9 {}
