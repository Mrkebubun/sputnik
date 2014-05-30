#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $DIR

git pull -u origin >/dev/null 2>/dev/null
# For now just test the non-UI stuff until we get selenium installed at sputnikmkt.com
make clean >/dev/null
make -k no_ui_report > /tmp/test_output.$$ 2>/dev/null
if [ $? -ne 0 ]; then
  cat /tmp/test_output.$$
fi
rm /tmp/test_output.$$
exit $?

