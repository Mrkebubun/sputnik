from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("rest")
import json

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.resource import Resource
from twisted.web.server import Site, NOT_DONE_YET
from twisted.web.http import Request
from plugin import Plugin
import inspect
from sputnik.exception import *
from datetime import datetime
from autobahn.wamp import types, auth
import hmac
import hashlib


class RESTProxy(Resource, Plugin):
    isLeaf = True
    def init(self):
        plugin_list = [
               "sputnik.webserver.plugins.rpc.registrar.RegistrarService",
               "sputnik.webserver.plugins.rpc.token.TokenService",
               "sputnik.webserver.plugins.rpc.info.InfoService",
               "sputnik.webserver.plugins.rpc.market.MarketService",
               "sputnik.webserver.plugins.rpc.private.PrivateService",
               "sputnik.webserver.plugins.rpc.trader.TraderService"]

        plugins = [self.require(plugin) for plugin in plugin_list]
        self.procs = {}

        # Register WAMPv2 RPC calls as REST fns
        test = lambda x: inspect.ismethod(x) or inspect.isfunction(x)
        for plugin in plugins:
            for k in inspect.getmembers(plugin, test):
                proc = k[1]
                if "_wampuris" in proc.__dict__:
                    pat = proc.__dict__["_wampuris"][0]
                    if pat.is_endpoint():
                        uri = pat.uri()
                        self.procs[uri] = proc

        self.auth_required = ["trader", "private", "token"]
        self.blocked_procs = []
        self.administrator = self.require("sputnik.webserver.plugins.backend.administrator.AdministratorProxy")

    @inlineCallbacks
    def check_auth(self, data):
        auth = data.get('auth')
        if auth is not None and 'username' in auth and 'key' in auth and 'nonce' in auth and 'signature' in auth:
            databases = self.manager.services["sputnik.webserver.plugins.db"]
            user = None

            for db in databases:
                user = yield db.lookup(auth['username'])
                if user is not None:
                    break

            # Check the nonce
            if user is not None:
                # Check the token and expiration
                now = datetime.utcnow()
                if user['api_key'] is None or user['api_expiration'] <= now or user['api_key'] != auth['key']:
                    raise RestException("exceptions/rest/not_authorized")

                # Check the HMAC
                message = "%d:%s:%s" % (nonce, auth['username'], auth['key'])
                signature = hmac.new(user['api_secret'], msg=message, digestmod=hashlib.sha256).hexdigest().upper()
                if auth['signature'].upper() != signature:
                    raise RestException("exceptions/rest/not_authorized")

                nonce_check = yield self.administrator.proxy.check_and_update_api_nonce(user['username'],
                                                                                        auth['nonce'])
                if not nonce_check:
                    raise RestException("exceptions/rest/not_authorized")

                returnValue({'authid': user['username']})
            else:
                raise RestException("exceptions/rest/not_authorized")
        else:
            raise RestException('exceptions/rest/invalid_rest_request')

    @inlineCallbacks
    def process_request(self, request, data):
        uri = '.'.join(request.postpath)
        if uri not in self.procs or uri in self.blocked_procs:
            raise RestException("exceptions/rest/no_such_function", uri)

        if 'payload' not in data:
            raise RestException('exceptions/rest/invalid_rest_request')

        if request.postpath[1] in self.auth_required:
            auth = yield self.check_auth(data)
            if auth is not None:
                data['payload']['details'] = auth
            else:
                raise RestException("exceptions/rest/not_authorized")

        fn = self.procs[uri]
        result = yield fn(**data['payload'])
        returnValue(result)

    def log(self, request, data):
        """Log the request

        """
        log((request.getClientIP(),
            request.getUser(),
            request.method,
            request.uri,
            request.clientproto,
            request.code,
            request.sentLength or "-",
            request.getHeader("referer") or "-",
            request.getHeader("user-agent") or "-",
            json.dumps(request.args),
            data))

    def render(self, request):
        request.setHeader('content-type', 'application/json')

        data = request.content.read()
        self.log(request, data)

        try:
            if request.method != "POST":
                raise RestException("exceptions/rest/unsupported_method")
            else:
                try:
                    parsed_data = json.loads(data)
                except ValueError as e:
                    raise RestException("exceptions/rest/invalid_json", *e.args)

                d = self.process_request(request, data=parsed_data)

            def deliver_result(result, request):
                if not result['success']:
                    error("request %s returned error %s" % (request, result['error']))
                request.write(json.dumps(result, sort_keys=True, indent=4, separators=(',', ': ')))
                request.finish()

            def sputnik_failure(failure):
                failure.trap(SputnikException)
                error(failure)
                return {'success': False, 'error': failure.value.args}

            def generic_failure(failure):
                error("UNHANDLED ERROR: %s" % failure.value)
                error(failure)
                return {'success': False, 'error': ("exceptions/rest/generic_error",)}

            d.addErrback(sputnik_failure).addErrback(generic_failure).addCallback(deliver_result, request)
            return NOT_DONE_YET


        except RestException as e:
            error(e)
            result = {'success': False, 'error': e.args}
            return json.dumps(result, sort_keys=True,
                              indent=4, separators=(',', ': ')).encode('utf-8')
        except Exception as e:
            error("UNRECOGNIZED ERROR: %s" % str(e.args))
            error(e)
            result = {'success': False, 'error': 'exceptions/rest/internal_error'}
            return json.dumps(result, sort_keys=True,
                              indent=4, separators=(',', ': ')).encode('utf-8')


