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
    def check_auth(self, request, data, auth):
        key = auth.get("key")
        signature = request.getHeader("Authorization")
        if not all([key, signature]):
            raise RestException("exceptions/rest/not_authorized")

        databases = self.manager.services["sputnik.webserver.plugins.db"]
        user = None

        for db in databases:
            user = yield db.lookup(key)
            if user is not None:
                break
        else:
            raise RestException("exceptions/rest/not_authorized")

        now = datetime.utcnow()
        if user['api_key'] != key or user['api_expiration'] <= now:
            raise RestException("exceptions/rest/not_authorized")

        # Check the HMAC
        actual = hmac.new(user['api_secret'].encode('utf-8'), msg=data.encode('utf-8'), digestmod=hashlib.sha256).hexdigest().upper()
        signature = signature.upper()

        if len(actual) != len(signature):
            raise RestException("exceptions/rest/not_authorized")
        valid = True
        for i in range(len(actual)):
            if actual[i] != signature[i]:
                valid = False
        if not valid:
            raise RestException("exceptions/rest/not_authorized")

        nonce = auth.get("nonce")
        if nonce is None:
            raise RestException("exceptions/rest/invalid_nonce")

        nonce_valid = yield self.administrator.proxy.check_and_update_api_nonce(user['username'], nonce)
        if not nonce_valid:
            raise RestException("exceptions/rest/not_authorized")

        returnValue({'authid': user['username']})

    @inlineCallbacks
    def process_request(self, request, data):
        try:
            parsed_data = json.loads(data)
        except ValueError as e:
            raise RestException("exceptions/rest/invalid_json", *e.args)

        auth = parsed_data.get("auth")

        uri = '.'.join(request.postpath)
        if uri not in self.procs or uri in self.blocked_procs:
            raise RestException("exceptions/rest/no_such_function", uri)

        kwargs = parsed_data.get("payload") or {}

        if request.postpath[1] in self.auth_required:
            details = yield self.check_auth(request, data, auth)
            kwargs['details'] = details

        method = self.procs[uri]
        result = yield method(**kwargs)
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
            request.getHeader("content-type") or "-",
            json.dumps(request.args),
            data))

    def render(self, request):
        request.setHeader('content-type', 'application/json')

        data = request.content.read()
        self.log(request, data.encode("utf-8"))

        try:
            if request.method != "POST":
                raise RestException("exceptions/rest/unsupported_method")

            d = self.process_request(request, data)

            def deliver_result(result):
                if not result['success']:
                    error("request %s returned error %s" % (request, result['error']))
                request.write(json.dumps(result, sort_keys=True, indent=4, separators=(',', ': ')))
                request.finish()

            def sputnik_failure(failure):
                failure.trap(SputnikException)
                error(failure)
                return {'success': False, 'error': failure.value.args}

            def generic_failure(failure):
                error("UNHANDLED EXCEPTION: %s" % failure.value)
                error(failure)
                return {'success': False, 'error': ("exceptions/rest/generic_error",)}

            d.addErrback(sputnik_failure).addErrback(generic_failure).addCallback(deliver_result)
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


