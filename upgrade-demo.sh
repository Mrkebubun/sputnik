#!/bin/sh
# This only works for demo, we have autodeploy
# for everything else now
# TODO: Move demo into autodeploy and get rid of this script
cp -r /srv/autodeploy/demo/profile install/profiles/demo
PROFILE_NAME=demo
HOSTNAME=demo.m2.io
git pull -u origin
make clean
echo "[aux]" > aux.ini
PROFILE=install/profiles/${PROFILE_NAME} make tar
scp sputnik.tar ${HOSTNAME}:. 
ssh ${HOSTNAME} rm -rf sputnik
ssh ${HOSTNAME} tar xf sputnik.tar
ssh -t ${HOSTNAME} "(cd sputnik; sudo make upgrade)"
rm -rf install/profiles/demo
