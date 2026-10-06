import os

from qgis.core import QgsApplication
from qgis.PyQt.QtGui import QIcon

try:
    from qgis.PyQt.QtWidgets import QAction, QMenu
except ImportError:  # Qt6
    from qgis.PyQt.QtGui import QAction
    from qgis.PyQt.QtWidgets import QMenu

from .provider import GlubProvider

NAME = "GLUB!"
# (translation key, tab index) for the menu entries
ENTRIES = (("tab.download", 1), ("tab.prepare", 2), ("tab.deglint", 3), ("tab.composite", 4),
           ("tab.watercol", 5), ("tab.classify", 6), ("tab.validation", 7), ("tab.change", 8))


class GlubPlugin:
    """Own menu in the menu bar (before Help), own toolbar, an entry in Raster,
    and the Processing tools for models and batch runs."""

    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.action = None
        self.menu = None
        self.toolbar = None
        self.tab_actions = []
        self.dialog = None

    def initProcessing(self):
        self.provider = GlubProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        from .gui import i18n
        i18n.set_lang(i18n.default_lang())
        self.initProcessing()
        mw = self.iface.mainWindow()
        icon = QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))
        self.action = QAction(icon, NAME, mw)
        self.action.setObjectName("GlubOpen")
        self.action.triggered.connect(lambda: self.run(0))

        self.menu = QMenu(NAME, mw)
        self.menu.setObjectName("mGlubMenu")
        self.open_action = QAction(icon, i18n.tr("menu.open"), mw)
        self.open_action.triggered.connect(lambda: self.run(0))
        self.menu.addAction(self.open_action)
        self.menu.addSeparator()
        for key, idx in ENTRIES:
            a = QAction(i18n.tr(key), mw)
            a.triggered.connect(lambda _=False, i=idx: self.run(i))
            self.menu.addAction(a)
            self.tab_actions.append((a, key))
        self.menu.addSeparator()
        self.proc_action = QAction(i18n.tr("menu.processing"), mw)
        self.proc_action.triggered.connect(self._show_processing)
        self.menu.addAction(self.proc_action)
        bar = mw.menuBar()
        help_menu = self.iface.firstRightStandardMenu()
        if help_menu is not None:
            bar.insertMenu(help_menu.menuAction(), self.menu)
        else:
            bar.addMenu(self.menu)

        self.toolbar = self.iface.addToolBar(NAME)
        self.toolbar.setObjectName("GlubToolbar")
        self.toolbar.addAction(self.action)
        self.iface.addPluginToRasterMenu(NAME, self.action)

    def _retranslate_menu(self, _code=None):
        from .gui import i18n
        self.open_action.setText(i18n.tr("menu.open"))
        self.proc_action.setText(i18n.tr("menu.processing"))
        for a, key in self.tab_actions:
            a.setText(i18n.tr(key))

    def _show_processing(self):
        """Show the Processing Toolbox filtered to the GLUB tools (best effort)."""
        try:
            from qgis.PyQt.QtWidgets import QDockWidget, QLineEdit
            dock = self.iface.mainWindow().findChild(QDockWidget, "ProcessingToolbox")
            if dock is None:
                return
            dock.setVisible(True)
            dock.raise_()
            box = dock.findChild(QLineEdit, "searchBox")
            if box is not None:
                box.setText("GLUB")
        except Exception:  # never break QGIS for a convenience
            pass

    def run(self, tab=0):
        from .gui.main_dialog import GlubDialog
        if self.dialog is None:
            self.dialog = GlubDialog(self.iface, self.iface.mainWindow())
            self.dialog.home.languageChanged.connect(self._retranslate_menu)
        self.dialog.tabs.setCurrentIndex(tab or 0)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def unload(self):
        if self.action:
            self.iface.removePluginRasterMenu(NAME, self.action)
        if self.toolbar:
            self.toolbar.deleteLater()
            self.toolbar = None
        if self.menu:
            self.iface.mainWindow().menuBar().removeAction(self.menu.menuAction())
            self.menu.deleteLater()
            self.menu = None
        self.tab_actions = []
        if self.dialog:
            self.dialog.detach_tasks()
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
