"""Single GLUB! window with all tabs."""
from qgis.PyQt.QtWidgets import QDialog, QTabWidget, QVBoxLayout

from . import i18n
from .change_tab import ChangeTab
from .classify_tab import ClassifyTab
from .composite_tab import CompositeTab
from .deglint_tab import DeglintTab
from .download_tab import DownloadTab
from .home_tab import HomeTab
from .i18n import tr
from .prepare_tab import PrepareTab
from .validation_tab import ValidationTab
from .watercol_tab import WaterColumnTab

TAB_KEYS = ("tab.home", "tab.download", "tab.prepare", "tab.deglint", "tab.composite", "tab.watercol",
            "tab.classify", "tab.validation", "tab.change")


class GlubDialog(QDialog):
    def __init__(self, iface, parent=None):
        i18n.set_lang(i18n.default_lang())
        super().__init__(parent)
        self.resize(1240, 880)
        self.tabs = QTabWidget()
        self.home = HomeTab(self)
        self.download = DownloadTab(iface, self, self)
        self.prepare = PrepareTab(iface, self, self)
        self.deglint = DeglintTab(self)
        self.composite = CompositeTab(self)
        self.watercol = WaterColumnTab(self)
        self.classify = ClassifyTab(self)
        self.validation = ValidationTab(self)
        self.change = ChangeTab(self)
        self.pages = (self.home, self.download, self.prepare, self.deglint, self.composite,
                      self.watercol, self.classify, self.validation, self.change)
        for w in self.pages:
            self.tabs.addTab(w, "")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.tabs)
        for p in self.pages[1:]:
            p.run.set_owner(p)
        from .home_tab import is_simple
        self.home.modeChanged.connect(self._set_simple)
        self._set_simple(is_simple())
        self._titles()

        # each step feeds the next one
        self.home.languageChanged.connect(self._retranslate)
        self.download.downloaded.connect(lambda paths: self.prepare.set_zip(paths[-1]))
        self.download.area.cb_layer.layerChanged.connect(self.prepare.area.cb_layer.setLayer)
        self.prepare.prepared.connect(self.deglint.set_raster)
        self.deglint.corrected.connect(self.composite.add_path)
        for sig in (self.prepare.prepared, self.deglint.corrected, self.composite.composed):
            sig.connect(self.watercol.set_raster)
            sig.connect(self.classify.set_raster)
        self.watercol.computed.connect(self.classify.set_dii)
        self.classify.classified.connect(self.validation.set_map)

    def tasks(self):
        return [p.run.task for p in self.pages[1:] if p.run.task is not None]

    def detach_tasks(self):
        for p in self.pages[1:]:
            p.run.detach()

    def _titles(self):
        self.setWindowTitle(tr("win.title"))
        for n, key in enumerate(TAB_KEYS):
            self.tabs.setTabText(n, tr(key))

    def _retranslate(self, _code=None):
        self._titles()
        for w in self.pages:
            w.retranslate()
            for child in (getattr(w, "area", None), getattr(w, "rbox", None), getattr(w, "run", None)):
                if child is not None:
                    child.retranslate()

    def _set_simple(self, simple):
        for w in self.pages[1:]:
            w.set_simple(simple)
