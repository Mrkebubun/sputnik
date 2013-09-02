#!/bin/sh

cd `dirname $0`/../server/pepsi/
./engine.py BTC.13.7.12.gt.70 > /dev/null 2>&1 &
./engine.py USD.13.7.31 > /dev/null 2>&1 &

