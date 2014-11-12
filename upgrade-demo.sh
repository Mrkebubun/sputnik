#!/bin/sh
# This only works for demo, we have autodeploy
# for everything else now
# TODO: Move demo into autodeploy and get rid of this script
git pull -u origin
rm -rf install/profiles/demo
cp -r /srv/autodeploy/demo/profile install/profiles/demo
PROFILE_NAME=demo
HOSTNAME=ec2-54-187-247-12.us-west-2.compute.amazonaws.com

HASH=`ssh ${HOSTNAME} cat /srv/sputnik/server/config/sputnik.ini | grep git_hash | awk '{ print $3 }'`
echo "Replacing version: ${HASH}"
echo ${HASH} >> /srv/autodeploy/demo/versions

make clean
PROFILE=install/profiles/${PROFILE_NAME} make tar
scp sputnik.tar ${HOSTNAME}:. 
ssh ${HOSTNAME} rm -rf sputnik
ssh ${HOSTNAME} tar xf sputnik.tar
ssh -t ${HOSTNAME} "(cd sputnik; sudo make upgrade)"
rm -rf install/profiles/demo
