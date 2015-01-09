from sputnik import config
from sputnik import observatory

debug, log, warn, error, critical = observatory.get_loggers("rest")
import json

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.web.resource import Resource
from twisted.web.server import Site, NOT_DONE_YET
from twisted.web.http import Request
from plugin import Plugin
import inspect
from sputnik.exception import *

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

    def process_request(self, request, data):
        uri = '.'.join(request.postpath)
        if uri not in self.procs:
            raise RestException("exceptions/rest/no_such_function", uri)

        # TODO: Check for auth if needed
        # TODO: Add 'details' if authentication is received
        fn = self.procs[uri]

        return fn(**data)

    def log(self, request, data):
        log("PUT LOGGING HERE: %s/%s" % (request, data))

    def render(self, request):
        request.setHeader('content-type', 'application/json')

        data = request.content.read()
        self.log(request, data)

        try:
            if request.method != "POST":
                raise RestException("exceptions/rest/unsupported_method")
            else:
                parsed_data = json.loads(data)
                d = self.process_request(request, data=parsed_data)

            def deliver_result(result, request):
                request.write(json.dumps(result, sort_keys=True, indent=4, separators=(',', ': ')))
                request.finish()

            d.addCallback(deliver_result, request)
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


