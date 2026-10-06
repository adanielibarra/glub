def classFactory(iface):
    from .plugin import GlubPlugin
    return GlubPlugin(iface)
