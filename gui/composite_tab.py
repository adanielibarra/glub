"""Tab 4: median composite of several dates."""
import os

from qgis.core import QgsProject, QgsRasterLayer
from qgis.gui import QgsFileWidget, QgsMapLayerComboBox
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog,
                                 QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                                 QListWidget, QPushButton, QSpinBox,
                                 QVBoxLayout, QWidget)

from ..algorithms.aoi import union_features
from ..compat import POLYGON_LAYER
from ..core import clarity, pipeline
from ..core.lang import L
from .common import RunPanel, Translatable, add_raster
from .i18n import tr


class CompositeTab(QWidget, Translatable):
    HELP = "s4-4"
    composed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        g = QGroupBox()
        self._t(g.setTitle, "cp.inputs")
        v = QVBoxLayout(g)
        help_ = QLabel()
        help_.setWordWrap(True)
        help_.setStyleSheet("color: gray")
        self._t(help_.setText, "cp.help")
        v.addWidget(help_)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        v.addWidget(self.list, 1)
        row = QHBoxLayout()
        for key, fn in (("cp.add", self._add_files), ("cp.addlayers", self._add_layers), ("cp.remove", self._remove)):
            b = QPushButton()
            self._t(b.setText, key)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        v.addLayout(row)
        lay.addWidget(g, 1)

        # ---- water clarity ranking of the scenes in the list
        gq = QGroupBox()
        self._t(gq.setTitle, "cp.clar")
        fq = QFormLayout(gq)
        self.cb_deep = QgsMapLayerComboBox()
        self.cb_deep.setFilters(POLYGON_LAYER)
        self.cb_deep.setAllowEmptyLayer(True)
        self.cb_deep.setLayer(None)
        self.cb_bot = QgsMapLayerComboBox()
        self.cb_bot.setFilters(POLYGON_LAYER)
        self.cb_bot.setAllowEmptyLayer(True)
        self.cb_bot.setLayer(None)
        fq.addRow(self._lbl("cp.clar.deep"), self.cb_deep)
        fq.addRow(self._lbl("cp.clar.bottom"), self.cb_bot)
        qrow = QHBoxLayout()
        self.btn_rank = QPushButton()
        self._t(self.btn_rank.setText, "cp.clar.run")
        self.btn_rank.clicked.connect(self.rank)
        self.btn_drop = QPushButton()
        self._t(self.btn_drop.setText, "cp.clar.drop")
        self.btn_drop.setEnabled(False)
        self.btn_drop.clicked.connect(self._drop_flagged)
        qrow.addWidget(self.btn_rank)
        qrow.addWidget(self.btn_drop)
        qrow.addStretch()
        fq.addRow(qrow)
        hq = QLabel()
        hq.setWordWrap(True)
        hq.setStyleSheet("color: gray")
        self._t(hq.setText, "cp.clar.help")
        fq.addRow(hq)
        lay.addWidget(gq)
        self.flagged = []

        go = QGroupBox()
        self._t(go.setTitle, "c.output")
        fo = QFormLayout(go)
        self.sp_min = QSpinBox()
        self.sp_min.setRange(1, 100)
        self.sp_min.setValue(1)
        self.fw_out = QgsFileWidget()
        self.fw_out.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
        self.fw_out.setFilter("GeoTIFF (*.tif)")
        self.chk_add = QCheckBox()
        self._t(self.chk_add.setText, "c.addmap")
        self.chk_add.setChecked(True)
        fo.addRow(self._lbl("cp.min"), self.sp_min)
        self.sp_days = QSpinBox()
        self.sp_days.setRange(1, 3650)
        self.sp_days.setValue(45)
        self._t(self.sp_days.setToolTip, "cp.maxdays.tip")
        fo.addRow(self._lbl("cp.maxdays"), self.sp_days)
        fo.addRow(self._lbl("c.outfile"), self.fw_out)
        fo.addRow("", self.chk_add)
        lay.addWidget(go)

        self.run = RunPanel()
        self.run.btn_run.clicked.connect(self.start)
        lay.addWidget(self.run)

    def add_path(self, path):
        known = [self._path(self.list.item(i)) for i in range(self.list.count())]
        if path and path not in known:
            self.list.addItem(path)
            if not self.fw_out.filePath():
                base, _ = os.path.splitext(path)
                self.fw_out.setFilePath(base + "_median.tif")

    @staticmethod
    def _exact():
        from qgis.PyQt.QtCore import Qt
        return Qt.MatchFlag.MatchExactly

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, tr("cp.add"), "", "GeoTIFF (*.tif *.tiff)")
        for p in paths:
            self.add_path(p)

    def _add_layers(self):
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsRasterLayer) and os.path.exists(lyr.source()) and lyr.bandCount() >= 3:
                self.add_path(lyr.source())

    def _remove(self):
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))

    def _wkt(self, layer, crs):
        if layer is None:
            return None
        geom, _n = union_features(layer.getFeatures(), layer.crs(), crs, QgsProject.instance().transformContext())
        return geom.asWkt() if geom is not None else None

    def rank(self):
        paths = [self._path(self.list.item(i)) for i in range(self.list.count())]
        if len(paths) < 2:
            self.run.error(tr("cp.need"))
            return
        if self.cb_deep.currentLayer() is None:
            self.run.error(tr("cp.clar.need"))
            return
        crs = QgsRasterLayer(paths[0], "ref").crs()
        deep = self._wkt(self.cb_deep.currentLayer(), crs)
        bot = self._wkt(self.cb_bot.currentLayer(), crs)
        if deep is None:
            self.run.error(tr("c.nopoly"))
            return
        out_csv = os.path.join(os.path.dirname(paths[0]), "scene_clarity.csv")
        idx = {"blue": 1, "green": 2, "red": 3, "nir": 4}

        def work(log, progress, is_canceled):
            progress(10)
            rows, _w = clarity.rank(paths, idx, deep, bot, log, out_csv)
            return rows, paths

        self.run.start("GLUB! · water clarity", work, self._ranked, extra_buttons=(self.btn_rank,))

    def _ranked(self, result):
        rows, paths = result
        seen = {r["path"] for r in rows}
        # scenes left out by the ranking (other CRS, unreadable) stay in the list, flagged
        rows = list(rows) + [{"rank": None, "path": p, "flags": [L("not measured (see the log)",
                                                                  "sin medir (mira el registro)")]}
                             for p in paths if p not in seen]
        self.list.clear()
        self.flagged = []
        for r in rows:
            label = f"{r['rank'] or '-'}. {r['path']}"
            if r["flags"]:
                label += "   ⚠ " + "; ".join(r["flags"])
                self.flagged.append(r["path"])
            self.list.addItem(label)
            it = self.list.item(self.list.count() - 1)
            it.setData(256, r["path"])   # Qt.UserRole: the path itself
            it.setToolTip("; ".join(r["flags"]) or r["path"])
        self.btn_drop.setEnabled(bool(self.flagged))

    def _drop_flagged(self):
        for i in reversed(range(self.list.count())):
            if self._path(self.list.item(i)) in self.flagged:
                self.list.takeItem(i)
        self.flagged = []
        self.btn_drop.setEnabled(False)

    @staticmethod
    def _path(item):
        p = item.data(256)
        return p if p else item.text()

    def start(self):
        paths = [self._path(self.list.item(i)) for i in range(self.list.count())]
        if len(paths) < 2:
            self.run.error(tr("cp.need"))
            return
        out = self.fw_out.filePath()
        if not out:
            self.run.error(tr("c.need.out"))
            return
        if not out.lower().endswith(".tif"):
            out += ".tif"
        mn, md = self.sp_min.value(), self.sp_days.value()

        def work(log, progress, is_canceled):
            progress(10)
            pipeline.composite_file(paths, out, mn, log, md)
            return out

        self.run.start("GLUB! · composite", work, self._done)

    def _done(self, path):
        if self.chk_add.isChecked():
            add_raster(path, os.path.splitext(os.path.basename(path))[0], "rgb")
        self.composed.emit(path)

    def advanced(self):
        return [self.sp_min]
