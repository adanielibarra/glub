"""Tab 8: change between two class maps (date 1 -> date 2)."""
import os

from qgis.gui import QgsFileWidget, QgsMapLayerComboBox
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (QCheckBox, QFormLayout, QGroupBox, QLabel,
                                 QPushButton, QScrollArea, QSpinBox,
                                 QVBoxLayout, QWidget)

from ..author import CREDIT
from ..compat import RASTER_LAYER
from ..core import change, report, vectorize
from ..core.lang import L
from .common import RunPanel, Translatable, add_raster, add_vector
from .i18n import tr


class ChangeTab(QWidget, Translatable):
    HELP = "s4-8"
    def __init__(self, parent=None):
        super().__init__(parent)
        self.report = None
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        lay = QVBoxLayout(inner)

        g = QGroupBox()
        self._t(g.setTitle, "ch.maps")
        f = QFormLayout(g)
        self.cb_1 = QgsMapLayerComboBox()
        self.cb_2 = QgsMapLayerComboBox()
        for cb in (self.cb_1, self.cb_2):
            cb.setFilters(RASTER_LAYER)
            cb.setAllowEmptyLayer(True)
            cb.setLayer(None)
        self.cb_1.layerChanged.connect(self._default_out)
        f.addRow(self._lbl("ch.map1"), self.cb_1)
        f.addRow(self._lbl("ch.map2"), self.cb_2)
        h = QLabel()
        h.setWordWrap(True)
        h.setStyleSheet("color: gray")
        self._t(h.setText, "ch.help")
        f.addRow(h)
        lay.addWidget(g)

        go = QGroupBox()
        self._t(go.setTitle, "c.output")
        fo = QFormLayout(go)
        self.sp_mmu = QSpinBox()
        self.sp_mmu.setRange(0, 1000000)
        self._t(self.sp_mmu.setToolTip, "ch.mmu.tip")
        self.fw_dir = QgsFileWidget()
        self.fw_dir.setStorageMode(QgsFileWidget.StorageMode.GetDirectory)
        self.chk_add = QCheckBox()
        self._t(self.chk_add.setText, "c.addmap")
        self.chk_add.setChecked(True)
        fo.addRow(self._lbl("ch.mmu"), self.sp_mmu)
        fo.addRow(self._lbl("c.outdir"), self.fw_dir)
        fo.addRow("", self.chk_add)
        self.chk_vec = QCheckBox()
        self._t(self.chk_vec.setText, "ch.vec")
        fo.addRow("", self.chk_vec)
        self.lbl_res = QLabel()
        self.lbl_res.setWordWrap(True)
        fo.addRow(self.lbl_res)
        self.btn_report = QPushButton()
        self._t(self.btn_report.setText, "va.open")
        self.btn_report.setEnabled(False)
        self.btn_report.clicked.connect(lambda: self.report and QDesktopServices.openUrl(QUrl.fromLocalFile(self.report)))
        fo.addRow("", self.btn_report)
        lay.addWidget(go)
        lay.addStretch()

        self.run = RunPanel()
        self.run.btn_run.clicked.connect(self.start)
        outer.addWidget(self.run)

    def _default_out(self, lyr):
        if lyr is not None and os.path.exists(lyr.source()):
            self.fw_dir.setFilePath(os.path.join(os.path.dirname(lyr.source()), "change"))

    def start(self):
        l1, l2 = self.cb_1.currentLayer(), self.cb_2.currentLayer()
        if l1 is None or l2 is None or l1 == l2:
            self.run.error(tr("ch.need"))
            return
        out_dir = self.fw_dir.filePath()
        if not out_dir:
            self.run.error(tr("c.need.out"))
            return
        p1, p2, mmu = l1.source(), l2.source(), self.sp_mmu.value()
        settings = [(L("Map, date 1", "Mapa, fecha 1"), p1), (L("Map, date 2", "Mapa, fecha 2"), p2),
                    (L("Minimum change unit", "Unidad mínima de cambio"),
                     L(f"{mmu} pixels", f"{mmu} píxeles") if mmu > 1 else L("off", "no"))]

        to_vec = self.chk_vec.isChecked()

        def work(log, progress, is_canceled):
            progress(10)
            s, w = change.compare(p1, p2, out_dir, mmu, log)
            if to_vec:
                base = s["filtered"]["path"] if s.get("filtered") else s["path"]
                try:   # the change map is already written: a polygon failure must not lose the run
                    s["polygons"] = vectorize.polygonize(base, os.path.splitext(base)[0] + ".gpkg", log=log)["path"]
                except Exception as e:
                    log(L(f"Polygons not written: {e}", f"No se han escrito los polígonos: {e}"), True)
            rep = os.path.join(out_dir, "change_report.html")
            with open(rep, "w", encoding="utf-8") as fh:
                fh.write(report.build_change(settings, s, w, CREDIT))
            return s, rep

        self.report = None
        self.btn_report.setEnabled(False)
        self.lbl_res.clear()
        self.run.start("GLUB! · change", work, self._done)

    def _done(self, result):
        s, rep = result
        self.report = rep
        self.run.autosave(os.path.dirname(rep))
        self.btn_report.setEnabled(True)
        unit = " ha" if s["ha"] else " px"
        lines = [tr("ch.res", s["comparable"], s["changed"],
                    f"{100 * s['changed'] / max(s['comparable'], 1):.1f} %")]
        for r in s["per_class"]:
            lines.append(f"{r['class']}: {r['date1']:.1f} → {r['date2']:.1f}{unit} "
                         f"(−{r['loss']:.1f} / +{r['gain']:.1f})")
        self.lbl_res.setText("\n".join(lines))
        if self.chk_add.isChecked():
            add_raster(s["path"], "change", "classes", legend=s["legend"])
            if s.get("filtered"):
                add_raster(s["filtered"]["path"], "change_filtered", "classes", legend=s["legend"])
            if s.get("polygons"):
                add_vector(s["polygons"], "classes", os.path.splitext(os.path.basename(s["polygons"]))[0])

    def advanced(self):
        return [self.sp_mmu]
