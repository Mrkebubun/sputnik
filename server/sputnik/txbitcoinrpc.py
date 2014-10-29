__author__ = 'sameer'
from txjsonrpc.web.jsonrpc import Proxy

class BitcoinRpc(object):
    def __init__(self, config_file):
        with open(config_file) as f:
            content = f.read().splitlines()

        config = {split[0]: split[1] for split in [row.split('=', 1) for row in content if len(row)]}
        if 'testnet' in config:
            port = 18332
        else:
            port = 8332

        rpcuser = config['rpcuser']
        rpcpassword = config['rpcpassword']
        self.proxy = Proxy('http://%s:%s@127.0.0.1:%d' % (rpcuser, rpcpassword, port))

    def __getattr__(self, key):
        if key.startswith("__"):
            raise AttributeError

        def proxy_method(*args, **kwargs):
            return self.proxy.callRemote(key, *args, **kwargs)

        return proxy_method
