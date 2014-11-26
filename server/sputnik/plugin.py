from collections import defaultdict
from twisted.internet.defer import inlineCallbacks, returnValue, DeferredList

import observatory

debug, log, warn, error, critical = observatory.get_loggers("plugin_manager")

class PluginException(Exception):
    pass

class PluginManager:
    def __init__(self):
        self.plugins = {}
        self.path_map = {}
        self.services = defaultdict(list)

    @inlineCallbacks
    def load(self, path):
        module_name, class_name = path.rsplit(".", 1)
        mod = __import__(module_name)
        for component in module_name.split(".")[1:]:
            mod = getattr(mod, component)
        klass = getattr(mod, class_name)
        plugin = klass()
        self.path_map[path] = plugin.service + "." + plugin.name
        returnValue((yield self._load_plugin(plugin)))

    def unload(self, path):
        plugin = self.plugins[self.path_map[path]]
        return self._unload_plugin(plugin)

    @inlineCallbacks
    def _load_plugin(self, plugin):
        name = plugin.service + "." + plugin.name
        debug("Loading plugin %s..." % name)
        if name in self.plugins:
            warn("Plugin %s already loaded." % name)
            return
        debug("Configuring plugin %s..." % name)
        try:
            plugin.configure(self)
            # wait until plugin is done
            yield plugin.init()
        except Exception, e:
            error("Unable to load plugin %s." % name)
            error()
            raise PluginException("Unable to load plugin %s." % name)
        debug("Plugin %s loaded." % name)
        self.plugins[name] = plugin
        self.services[plugin.service].append(plugin)
        returnValue(plugin)

    @inlineCallbacks
    def _unload_plugin(self, plugin):
        warn("There is no guarantee module code is completely removed.")
        name = plugin.service + "." + plugin.name
        debug("Unloading plugin %s..." % name)
        if name not in self.plugins:
            warn("Plugin %s not loaded." % name)
            return
        debug("Deconfiguring plugin %s..." % name)
        # wait until plugin is done
        try:
            yield plugin.shutdown()
        except Exception, e:
            error("Unable to unload plugin %s." % name)
            error()
            raise PluginException("Unable to unload plugin %s." % name)
        finally:
            if name in self.plugins:
                del self.plugins[name]
            if plugin in self.services[plugin.service]:
                self.services[plugin.service].remove(plugin)
        debug("Plugin %s unloaded." % name)

class Plugin:
    def __init__(self, name, service):
        self.name = name
        self.service = service

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
    def run_callback(_):
        callback(plugin_manager, *args, **kwargs)
    def cleanup(_):
        plugin_paths.reverse()
        for plugin_path in plugin_paths:
            plugin_manager.unload(plugin_path)
    dl.addCallback(run_callback)
    dl.addBoth(cleanup)

