import json

from twisted.internet import reactor
from twisted.web.resource import Resource
from twisted.web.server import Site

class RESTMethod(Resource):
    public_methods = ["get_info"]
    private_methods = ["place_order"]

    def __init__(self, name):
        Resource.__init__(self)
        self.method = name

    def render_GET(self, request):
        print request.site.public_proxy
        if self.method not in self.public_methods:
            return json.dumps({"success":False, "error":"Method not found."})
    
    def render_POST(self, request):
        if self.method not in self.private_methods:
            return json.dumps({"success":False, "error":"Method not found."})

class RESTProxy(Resource):
    def getChild(self, name, request):
        return RESTMethod(name)

root = Resource()
root.putChild("api", RESTProxy())
factory = Site(root)
factory.public_proxy = "This should be a pool of anonymous connections."
factory.private_proxy = "This should be a cache of connections." \
    "It should keep a connection open for a few minutes per authenticated user."
reactor.listenTCP(8000, factory)
reactor.run()

