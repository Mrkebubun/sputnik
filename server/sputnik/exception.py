#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

class SputnikException(Exception): pass
class AccountantException(SputnikException): pass
class AdministratorException(SputnikException): pass
class CashierException(SputnikException): pass
class LedgerException(SputnikException): pass
class WebserverException(SputnikException): pass
class ZendeskException(SputnikException): pass
class PostgresException(SputnikException): pass
class RestException(SputnikException): pass
class RemoteCallException(Exception): pass
class RemoteCallTimedOut(SputnikException, RemoteCallException): pass