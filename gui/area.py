"""Reusable 'Area' box: optional polygon layer + optional extent."""
from qgis.core import (QgsCoordinateTransform,
                       QgsProject, QgsRectangle)
from qgis.gui import QgsExtentWidget, QgsMapLayerComboBox
from qgis.PyQt.QtWidgets import QCheckBox, QFormLayout, QGroupBox

from ..compat import POLYGON_LAYER
from ..algorithms.aoi import union_features
from .common import Translatable, features_of
from .i18n import tr


class AreaError(Exception):
    pass


class AreaBox(QGroupBox, Translatable):
    def __init__(self, iface, window, parent=None):
        super().__init__(parent)
        self._t(self.setTitle, "c.area")
        f = QFormLayout(self)
        self.cb_layer = QgsMapLayerComboBox()
        self.cb_layer.setFilters(POLYGON_LAYER)
        self.cb_layer.setAllowEmptyLayer(True)
        self.cb_layer.setLayer(None)
        self._t(self.cb_layer.setToolTip, "c.layer.tip")
        self.chk_sel = QCheckBox()
        self._t(self.chk_sel.setText, "c.selected")
        self.extent = QgsExtentWidget(None, QgsExtentWidget.WidgetStyle.CondensedStyle)
        self.extent.setNullValueAllowed(True, tr("c.none"))
        self.extent.clear()
        self._t(self.extent.setToolTip, "c.extent.tip")
        if iface is not None:
            canvas = iface.mapCanvas()
            self.extent.setMapCanvas(canvas)
            self.extent.setOriginalExtent(canvas.extent(), canvas.mapSettings().destinationCrs())
            self.extent.setOutputCrs(canvas.mapSettings().destinationCrs())
        # drawing on the canvas needs the window out of the way
        self.extent.toggleDialogVisibility.connect(window.setVisible)
        f.addRow(self._lbl("c.layer"), self.cb_layer)
        f.addRow("", self.chk_sel)
        f.addRow(self._lbl("c.extent"), self.extent)

    def has_area(self):
        return self.cb_layer.currentLayer() is not None or self._extent_set()

    def _extent_set(self):
        r = self.extent.outputExtent()
        return self.extent.isValid() and not r.isNull() and not r.isEmpty()

    def get(self, dest_crs):
        """(bounding box, dissolved polygon) in dest_crs; either may be None."""
        tctx = QgsProject.instance().transformContext()
        box = None
        if self._extent_set():
            src = self.extent.outputCrs()
            r = self.extent.outputExtent()
            if src.isValid() and src != dest_crs:
                r = QgsCoordinateTransform(src, dest_crs, tctx).transformBoundingBox(r)
            box = QgsRectangle(r)
        geom = None
        lyr = self.cb_layer.currentLayer()
        if lyr is not None:
            geom, _n = union_features(features_of(lyr, self.chk_sel.isChecked()), lyr.crs(),
                                      dest_crs, tctx)
            if geom is None:
                raise AreaError(tr("c.nopoly"))
            gb = geom.boundingBox()
            box = gb if box is None else box.intersect(gb)
            if box.isEmpty():
                raise AreaError(tr("c.nooverlap"))
        return box, geom

    def _retranslate_extra(self):
        self.extent.setNullValueAllowed(True, tr("c.none"))
