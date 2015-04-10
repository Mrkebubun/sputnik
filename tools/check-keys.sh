#!/bin/bash
#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

REVS=`git rev-list HEAD`
for rev in $REVS; do
    git checkout $rev
    git grep 'secret ='
    git grep 'key ='
    git grep 'sk_live'
    git grep 'BlockScore('
    git grep 'Compropago('
    git grep 'BitGo('
    git grep 'NexMo('
done
