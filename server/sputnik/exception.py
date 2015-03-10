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