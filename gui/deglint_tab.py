"""Tab 3: Hedley sunglint correction."""
import os

from qgis.core import QgsProject
from qgis.gui import QgsFileWidget, QgsMapLayerComboBox
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (QCheckBox, QDoubleSpinBox, QFormLayout,
                                 QGroupBox, QLabel, QScrollArea, QVBoxLayout,
                                 QWidget)

from ..compat import POLYGON_LAYER
from ..algorithms.aoi import union_features
from ..core import pipeline
from .common import RunPanel, Translatable, add_raster, features_of
from .i18n import tr
from .rasterbox import RasterBox


class DeglintTab(QWidget, Translatable):
    HELP = "s4-3"
    corrected = pyqtSignal(str)

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

        self.rbox = RasterBox(("blue", "green", "red", "nir"))
        self.rbox.cb.layerChanged.connect(self._default_out)
        lay.addWidget(self.rbox)

        g = QGroupBox()
        self._t(g.setTitle, "dg.deep")
        f = QFormLayout(g)
        self.cb_deep = QgsMapLayerComboBox()
        self.cb_deep.setFilters(POLYGON_LAYER)
        self.cb_deep.setAllowEmptyLayer(True)
        self.cb_deep.setLayer(None)
        self.chk_sel = QCheckBox()
        self._t(self.chk_sel.setText, "c.selected")
        help_ = QLabel()
        help_.setWordWrap(True)
        help_.setStyleSheet("color: gray")
        self._t(help_.setText, "dg.deep.help")
        self.sp_pct = QDoubleSpinBox()
        self.sp_pct.setRange(0, 20)
        self.sp_pct.setDecimals(1)
        f.addRow(self._lbl("dg.deep.layer"), self.cb_deep)
        f.addRow("", self.chk_sel)
        f.addRow(help_)
        f.addRow(self._lbl("dg.pct"), self.sp_pct)
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
            self.fw_out.setFilePath(base + "_deglint.tif")

    def start(self):
        lyr = self.rbox.layer()
        if lyr is None:
            self.run.error(tr("c.need.raster"))
            return
        deep = self.cb_deep.currentLayer()
        if deep is None:
            self.run.error(tr("dg.need.deep"))
            return
        out = self.fw_out.filePath()
        if not out:
            self.run.error(tr("c.need.out"))
            return
        if not out.lower().endswith(".tif"):
            out += ".tif"
        geom, _n = union_features(features_of(deep, self.chk_sel.isChecked()), deep.crs(), lyr.crs(),
                                  QgsProject.instance().transformContext())
        if geom is None:
            self.run.error(tr("c.nopoly"))
            return
        src, idx, wkt, pct = lyr.source(), self.rbox.indices(), geom.asWkt(), self.sp_pct.value()

        def work(log, progress, is_canceled):
            progress(10)
            pipeline.deglint_file(src, idx, wkt, out, pct, log)
            return out

        self.run.start("GLUB! · sunglint", work, self._done)

    def _done(self, path):
        if self.chk_add.isChecked():
            add_raster(path, os.path.splitext(os.path.basename(path))[0], "rgb")
        self.corrected.emit(path)

    def advanced(self):
        return [self.sp_pct]
