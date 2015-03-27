#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


__author__ = 'sameer'
from txjsonrpc.web.jsonrpc import Proxy
from twisted.internet import reactor

class BitcoinRpcTimeout(Exception):
    pass

class BitcoinRpc(object):
    def __init__(self, config_file, timeout=None):
        self.timeout = timeout
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
            d = self.proxy.callRemote(key, *args, **kwargs)

            if self.timeout is not None:
                timeout = reactor.callLater(self.timeout, d.errback,
                    BitcoinRpcTimeout("Bitcoin call timed out: %s" % key))

                def cancelTimeout(result):
                    if timeout.active():
                        timeout.cancel()
                    return result

                d.addBoth(cancelTimeout)

            return d

        return proxy_method
