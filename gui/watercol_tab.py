"""Tab 5: Lyzenga depth-invariant bottom index."""
import os

from qgis.core import QgsProject
from qgis.gui import QgsFileWidget, QgsMapLayerComboBox
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (QCheckBox, QDoubleSpinBox, QFormLayout,
                                 QGroupBox, QHBoxLayout, QLabel, QScrollArea,
                                 QVBoxLayout, QWidget)

from ..compat import POLYGON_LAYER
from ..algorithms.aoi import union_features
from ..core import pipeline
from .common import RunPanel, Translatable, add_raster, features_of
from .i18n import tr
from .rasterbox import RasterBox

BANDS = ("blue", "green", "red")


class WaterColumnTab(QWidget, Translatable):
    HELP = "s4-5"
    computed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        lay = QVBoxLayout(inner)

        self.rbox = RasterBox(BANDS)
        self.rbox.cb.layerChanged.connect(self._default_out)
        lay.addWidget(self.rbox)

        g = QGroupBox()
        self._t(g.setTitle, "wc.sand")
        f = QFormLayout(g)
        f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.cb_sand = QgsMapLayerComboBox()
        self.cb_sand.setFilters(POLYGON_LAYER)
        self.cb_sand.setAllowEmptyLayer(True)
        self.cb_sand.setLayer(None)
        self.chk_sel = QCheckBox()
        self._t(self.chk_sel.setText, "c.selected")
        help_ = QLabel()
        help_.setWordWrap(True)
        help_.setStyleSheet("color: gray")
        self._t(help_.setText, "wc.sand.help")
        self.cb_deep = QgsMapLayerComboBox()
        self.cb_deep.setFilters(POLYGON_LAYER)
        self.cb_deep.setAllowEmptyLayer(True)
        self.cb_deep.setLayer(None)
        self._t(self.cb_deep.setToolTip, "wc.deep.tip")
        self.sp_k = QDoubleSpinBox()
        self.sp_k.setRange(0, 5)
        self.sp_k.setSingleStep(0.5)
        self.sp_k.setValue(2.0)
        row = QHBoxLayout()
        self.chk_b = {}
        for b in BANDS:
            c = QCheckBox()
            self._t(c.setText, "ba.b." + b)
            c.setChecked(b != "red")
            self._t(c.setToolTip, "wc.bands.tip")
            self.chk_b[b] = c
            row.addWidget(c)
        row.addStretch()
        f.addRow(self._lbl("wc.sand.layer"), self.cb_sand)
        f.addRow("", self.chk_sel)
        f.addRow(help_)
        f.addRow(self._lbl("wc.deep"), self.cb_deep)
        f.addRow(self._lbl("ba.k"), self.sp_k)
        self.sp_floor = QDoubleSpinBox()
        self.sp_floor.setRange(0, 5)
        self.sp_floor.setSingleStep(0.5)
        self.sp_floor.setValue(1.0)
        self._t(self.sp_floor.setToolTip, "wc.floor.tip")
        f.addRow(self._lbl("wc.floor"), self.sp_floor)
        f.addRow(self._lbl("wc.bands"), row)
        lay.addWidget(g)

        go = QGroupBox()
        self._t(go.setTitle, "c.output")
        fo = QFormLayout(go)
        self.fw_out = QgsFileWidget()
        self.fw_out.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
        self.fw_out.setFilter("GeoTIFF (*.tif)")
        self.chk_add = QCheckBox()
        self._t(self.chk_add.setText, "c.addmap")
        self.chk_add.setChecked(True)
        fo.addRow(self._lbl("c.outfile"), self.fw_out)
        fo.addRow("", self.chk_add)
        lay.addWidget(go)
        lay.addStretch()

        self.run = RunPanel()
        self.run.btn_run.clicked.connect(self.start)
        outer.addWidget(self.run)
        self._default_out(self.rbox.layer())

    def set_raster(self, path):
        self.rbox.set_path(path)

    def _default_out(self, lyr):
        if lyr is not None and os.path.exists(lyr.source()):
            base, _ext = os.path.splitext(lyr.source())
            self.fw_out.setFilePath(base + "_dii.tif")

    def start(self):
        lyr = self.rbox.layer()
        if lyr is None:
            self.run.error(tr("c.need.raster"))
            return
        sand = self.cb_sand.currentLayer()
        if sand is None:
            self.run.error(tr("wc.need.sand"))
            return
        use = [b for b in BANDS if self.chk_b[b].isChecked()]
        if len(use) < 2:
            self.run.error(tr("wc.need.bands"))
            return
        out = self.fw_out.filePath()
        if not out:
            self.run.error(tr("c.need.out"))
            return
        if not out.lower().endswith(".tif"):
            out += ".tif"
        tctx = QgsProject.instance().transformContext()
        g, _n = union_features(features_of(sand, self.chk_sel.isChecked()), sand.crs(), lyr.crs(), tctx)
        if g is None:
            self.run.error(tr("c.nopoly"))
            return
        deep_wkt = None
        deep = self.cb_deep.currentLayer()
        if deep is not None:
            gd, _n = union_features(deep.getFeatures(), deep.crs(), lyr.crs(), tctx)
            if gd is None:
                self.run.error(tr("c.nopoly"))
                return
            deep_wkt = gd.asWkt()
        allidx = self.rbox.indices()
        idx = {b: allidx[b] for b in use}
        src, sand_wkt, k, fl = lyr.source(), g.asWkt(), self.sp_k.value(), self.sp_floor.value()

        def work(log, progress, is_canceled):
            progress(10)
            pipeline.watercolumn_file(src, idx, sand_wkt, out, deep_wkt, k, log, floor_sigma=fl)
            return out

        self.run.start("GLUB! · water column", work, self._done)

    def _done(self, path):
        if self.chk_add.isChecked():
            add_raster(path, os.path.splitext(os.path.basename(path))[0], "index")
        self.computed.emit(path)

    def advanced(self):
        return [self.sp_k, self.sp_floor]
