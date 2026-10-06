"""Raster layer picker with named band combos."""
from qgis.core import QgsProject
from qgis.gui import QgsMapLayerComboBox, QgsRasterBandComboBox
from qgis.PyQt.QtWidgets import QFormLayout, QGroupBox

from ..compat import RASTER_LAYER
from .common import Translatable

BAND_KEYS = {"blue": "c.blue", "green": "c.green", "red": "c.red", "nir": "c.nir"}


class RasterBox(QGroupBox, Translatable):
    def __init__(self, bands=("blue", "green", "red"), parent=None):
        super().__init__(parent)
        self._t(self.setTitle, "c.image")
        f = QFormLayout(self)
        self.cb = QgsMapLayerComboBox()
        self.cb.setFilters(RASTER_LAYER)
        f.addRow(self._lbl("c.raster"), self.cb)
        self.band = {}
        for i, name in enumerate(bands, start=1):
            c = QgsRasterBandComboBox()
            self.band[name] = (c, i)
            f.addRow(self._lbl(BAND_KEYS[name]), c)
        self.cb.layerChanged.connect(self._layer)
        self._layer(self.cb.currentLayer())

    def _layer(self, lyr):
        for c, default in self.band.values():
            c.setLayer(lyr)
            if lyr is not None and lyr.bandCount() >= default:
                c.setBand(default)

    def layer(self):
        return self.cb.currentLayer()

    def indices(self):
        return {name: c.currentBand() for name, (c, _d) in self.band.items()}

    def set_path(self, path):
        """Select the project layer whose source is path (added by another tab)."""
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.source() == path:
                self.cb.setLayer(lyr)
                return True
        return False
