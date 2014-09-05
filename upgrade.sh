#!/bin/sh
PROFILE_NAME=$1
HOSTNAME=$2
git pull -u origin
make clean
PROFILE=install/profiles/${PROFILE_NAME} make tar
scp sputnik.tar ${HOSTNAME}:. 
ssh ${HOSTNAME} rm -rf sputnik
ssh ${HOSTNAME} tar xf sputnik.tar
ssh -t ${HOSTNAME} "(cd sputnik; sudo make upgrade)"
