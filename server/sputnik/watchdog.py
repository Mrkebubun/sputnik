import zmq_util

class WatchdogExport:
    def ping(self):
        return "pong"

def watchdog(address):
    return zmq_util.router_share_async(WatchdogExport(), address)

class Watchdog:
    pass

