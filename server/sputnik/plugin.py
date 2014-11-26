from collections import defaultdict
from twisted.internet.defer import inlineCallbacks, returnValue

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
        returnValue((yield self._load_plugin(plugin)))

    @inlineCallbacks
    def _load_plugin(self, plugin):
        debug("Loading plugin %s..." % plugin.name)
        if plugin.name in self.plugins:
            warn("Plugin %s already loaded." % plugin.name)
            return
        debug("Configuring plugin %s..." % plugin.name)
        try:
            plugin.configure(self)
            # wait until plugin is done
            yield plugin.init()
        except Exception, e:
            error("Unable to load plugin %s." % plugin.name)
            error()
            raise PluginException("Unable to load plugin %s." % plugin.name)
        debug("Plugin %s loaded." % plugin.name)
        self.plugins[plugin.name] = plugin
        self.services[plugin.service].append(plugin)
        returnValue(plugin)

    @inlineCallbacks
    def _unload_plugin(self, plugin):
        warn("Plugin unloading not officially supported.")
        debug("Unloading plugin %s..." % plugin.name)
        if plugin.name not in self.plugins:
            warn("Plugin %s not loaded." % plugin.name)
            return
        debug("Deconfiguring plugin %s..." % plugin.name)
        # wait until plugin is done
        try:
            yield plugin.shutdown()
        except Exception, e:
            error("Unable to unload plugin %s." % plugin.name)
            error()
            raise PluginException("Unable to unload plugin %s." % plugin.name)
        finally:
            if plugin.name in self.plugins:
                del self.plugins[plugin.name]
            if plugin in self.services[plugin.service]:
                self.services[plugin.service].remove(plugin)
        debug("Plugin %s unloaded." % plugin.name)

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

