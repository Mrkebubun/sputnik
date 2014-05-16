#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $DIR

git pull -u origin
# For now just test the non-UI stuff until we get selenium installed at sputnikmkt.com
make no_ui
