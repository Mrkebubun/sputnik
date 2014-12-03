from collections import defaultdict
from twisted.internet.defer import inlineCallbacks, returnValue, DeferredList

import observatory

debug, log, warn, error, critical = observatory.get_loggers("plugin_manager")

class PluginException(Exception):
    pass

class PluginManager:
    def __init__(self):
        self.plugins = {}
        self.services = defaultdict(list)

    @inlineCallbacks
    def load(self, path):
        module_name, class_name = path.rsplit(".", 1)
        mod = __import__(module_name)
        for component in module_name.split(".")[1:]:
            mod = getattr(mod, component)
        klass = getattr(mod, class_name)
        plugin = klass()
        plugin.module_name = module_name
        plugin.service_name = module_name.rsplit(".", 1)[0]
        plugin.class_name = class_name
        plugin.plugin_path = path
        returnValue((yield self._load_plugin(plugin)))

    def unload(self, path):
        return self._unload_plugin(self.plugins[path])

    @inlineCallbacks
    def _load_plugin(self, plugin):
        path = plugin.plugin_path
        debug("Loading plugin %s..." % path)
        if path in self.plugins:
            warn("Plugin %s already loaded." % path)
            return
        debug("Configuring plugin %s..." % path)
        try:
            plugin.configure(self)
            # wait until plugin is done
            yield plugin.init()
        except Exception, e:
            error("Unable to load plugin %s." % path)
            error()
            raise PluginException("Unable to load plugin %s." % path)
        debug("Plugin %s loaded." % path)
        self.plugins[path] = plugin
        self.services[plugin.service_name].append(plugin)
        returnValue(plugin)

    @inlineCallbacks
    def _unload_plugin(self, plugin):
        warn("There is no guarantee module code is completely removed.")
        path = plugin.plugin_path
        debug("Unloading plugin %s..." % path)
        if path not in self.plugins:
            warn("Plugin %s not loaded." % path)
            return
        debug("Deconfiguring plugin %s..." % path)
        # wait until plugin is done
        try:
            yield plugin.shutdown()
        except Exception, e:
            error("Unable to unload plugin %s." % path)
            error()
            raise PluginException("Unable to unload plugin %s." % path)
        finally:
            if path in self.plugins:
                del self.plugins[path]
            if plugin in self.services[plugin.service_name]:
                self.services[plugin.service_name].remove(plugin)
        debug("Plugin %s unloaded." % path)

class Plugin:
    def __init__(self):
        pass

    def configure(self, manager):
        self.manager = manager

    def init(self):
        pass

    def shutdown(self):
        pass

def run_with_plugins(plugin_paths, callback, *args, **kwargs):
    plugin_manager = PluginManager()
    deferreds = []
    for plugin_path in plugin_paths:
        deferreds.append(plugin_manager.load(plugin_path))
    dl = DeferredList(deferreds)
    def run_callback(result):
        for success, value in result:
            if not success:
                return
        callback(plugin_manager, *args, **kwargs)
    def cleanup(_):
        plugin_paths.reverse()
        for plugin_path in plugin_paths:
            plugin_manager.unload(plugin_path)
        return _
    dl.addCallback(run_callback)
    dl.addBoth(cleanup)
    dl.addErrback(error)

