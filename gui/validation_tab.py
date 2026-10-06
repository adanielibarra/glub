"""Tab 7: stratified random validation points and the map assessment with them."""
import os

from qgis.core import QgsProject, QgsVectorLayer
from qgis.gui import QgsFieldComboBox, QgsFileWidget, QgsMapLayerComboBox
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                                 QFormLayout, QGroupBox, QLabel, QPushButton,
                                 QRadioButton, QScrollArea, QSpinBox,
                                 QVBoxLayout, QWidget)

from ..algorithms.validation_points import read_points_labels
from ..author import CREDIT
from ..compat import POINT_LAYER, RASTER_LAYER
from ..core import report, sampling
from ..core.lang import L
from .common import GROUP, RunPanel, Translatable
from .i18n import tr


def _gray(lab):
    lab.setWordWrap(True)
    lab.setStyleSheet("color: gray")
    return lab


class ValidationTab(QWidget, Translatable):
    HELP = "s4-7"
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

        gm = QGroupBox()
        self._t(gm.setTitle, "va.map")
        fm = QFormLayout(gm)
        self.cb_map = QgsMapLayerComboBox()
        self.cb_map.setFilters(RASTER_LAYER)
        self.cb_map.setAllowEmptyLayer(True)
        self.cb_map.setLayer(None)
        fm.addRow(self._lbl("va.map.layer"), self.cb_map)
        self.rb_gen = QRadioButton()
        self._t(self.rb_gen.setText, "va.mode.gen")
        self.rb_ass = QRadioButton()
        self._t(self.rb_ass.setText, "va.mode.ass")
        self.rb_gen.setChecked(True)
        fm.addRow(self.rb_gen)
        fm.addRow(self.rb_ass)
        hm = QLabel()
        self._t(hm.setText, "va.help")
        fm.addRow(_gray(hm))
        lay.addWidget(gm)

        # ---- generate
        self.g_gen = QGroupBox()
        self._t(self.g_gen.setTitle, "va.gen")
        fg = QFormLayout(self.g_gen)
        self.sp_n = QSpinBox()
        self.sp_n.setRange(0, 100000)
        self._t(self.sp_n.setSpecialValueText, "va.n.auto")
        self.sp_se = QDoubleSpinBox()
        self.sp_se.setRange(0.001, 0.2)
        self.sp_se.setDecimals(3)
        self.sp_se.setSingleStep(0.005)
        self.sp_se.setValue(0.02)
        self.sp_ua = QDoubleSpinBox()
        self.sp_ua.setRange(0.5, 0.99)
        self.sp_ua.setSingleStep(0.05)
        self.sp_ua.setValue(0.8)
        self.sp_min = QSpinBox()
        self.sp_min.setRange(0, 10000)
        self.sp_min.setValue(50)
        self.cb_mode = QComboBox()
        self.sp_hid = QSpinBox()
        self.sp_hid.setRange(0, 10000)
        self.sp_deep = QSpinBox()
        self.sp_deep.setRange(0, 10000)
        self.sp_dist = QDoubleSpinBox()
        self.sp_dist.setRange(0, 100000)
        self.sp_dist.setDecimals(0)
        self.sp_dist.setValue(30)
        self.sp_dist.setSuffix(" m")
        self.sp_seed = QSpinBox()
        self.sp_seed.setRange(0, 2 ** 31 - 1)
        self.sp_seed.setValue(42)
        self.fw_pts = QgsFileWidget()
        self.fw_pts.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
        self.fw_pts.setFilter("GeoPackage (*.gpkg)")
        self.chk_add = QCheckBox()
        self._t(self.chk_add.setText, "c.addmap")
        self.chk_add.setChecked(True)
        self.sp_n.valueChanged.connect(lambda v: (self.sp_se.setEnabled(v == 0), self.sp_ua.setEnabled(v == 0)))
        fg.addRow(self._lbl("va.n"), self.sp_n)
        fg.addRow(self._lbl("va.se"), self.sp_se)
        fg.addRow(self._lbl("va.ua"), self.sp_ua)
        fg.addRow(self._lbl("va.min"), self.sp_min)
        fg.addRow(self._lbl("va.mode"), self.cb_mode)
        fg.addRow(self._lbl("va.hidden"), self.sp_hid)
        fg.addRow(self._lbl("va.deep"), self.sp_deep)
        fg.addRow(self._lbl("va.dist"), self.sp_dist)
        fg.addRow(self._lbl("cl.seed"), self.sp_seed)
        fg.addRow(self._lbl("va.out"), self.fw_pts)
        fg.addRow("", self.chk_add)
        hg = QLabel()
        self._t(hg.setText, "va.gen.help")
        fg.addRow(_gray(hg))
        lay.addWidget(self.g_gen)

        # ---- assess
        self.g_ass = QGroupBox()
        self._t(self.g_ass.setTitle, "va.ass")
        fa = QFormLayout(self.g_ass)
        self.cb_pts = QgsMapLayerComboBox()
        self.cb_pts.setFilters(POINT_LAYER)
        self.cb_pts.setAllowEmptyLayer(True)
        self.cb_pts.setLayer(None)
        self.cb_field = QgsFieldComboBox()
        self.cb_pts.layerChanged.connect(self._points_changed)
        self.fw_dir = QgsFileWidget()
        self.fw_dir.setStorageMode(QgsFileWidget.StorageMode.GetDirectory)
        self.btn_report = QPushButton()
        self._t(self.btn_report.setText, "va.open")
        self.btn_report.setEnabled(False)
        self.btn_report.clicked.connect(lambda: self.report and QDesktopServices.openUrl(QUrl.fromLocalFile(self.report)))
        self.lbl_res = QLabel()
        self.lbl_res.setWordWrap(True)
        fa.addRow(self._lbl("va.pts"), self.cb_pts)
        fa.addRow(self._lbl("va.field"), self.cb_field)
        fa.addRow(self._lbl("c.outdir"), self.fw_dir)
        ha = QLabel()
        self._t(ha.setText, "va.ass.help")
        fa.addRow(_gray(ha))
        fa.addRow(self.lbl_res)
        fa.addRow("", self.btn_report)
        lay.addWidget(self.g_ass)
        lay.addStretch()

        self.rb_gen.toggled.connect(self._mode)
        self.cb_map.layerChanged.connect(self._default_out)
        self.run = RunPanel()
        self.run.btn_run.clicked.connect(self.start)
        outer.addWidget(self.run)
        self._retranslate_extra()
        self._mode()

    def _retranslate_extra(self):
        i = self.cb_mode.currentIndex() if hasattr(self, "cb_mode") else 0
        self.cb_mode.clear()
        self.cb_mode.addItems([tr("va.mode.prop"), tr("va.mode.equal")])
        self.cb_mode.setCurrentIndex(max(i, 0))

    def _mode(self, *_):
        gen = self.rb_gen.isChecked()
        self.g_gen.setVisible(gen)
        self.g_ass.setVisible(not gen)

    def _points_changed(self, lyr):
        self.cb_field.setLayer(lyr)
        if lyr is not None and lyr.fields().indexOf("ref_class") >= 0:
            self.cb_field.setField("ref_class")

    def _default_out(self, lyr):
        if lyr is not None:
            self._default_paths(lyr.source())

    def _default_paths(self, path):
        if os.path.exists(path):
            d = os.path.dirname(path)
            self.fw_pts.setFilePath(os.path.join(d, "validation_points.gpkg"))
            self.fw_dir.setFilePath(os.path.join(d, "assessment"))

    def set_map(self, path):
        """Called when a classification finishes: point the tab at its classes.tif if it is on the map."""
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.source() == path:
                self.cb_map.setLayer(lyr)
                return
        self._default_paths(path)

    def start(self):
        lyr = self.cb_map.currentLayer()
        if lyr is None:
            self.run.error(tr("va.need.map"))
            return
        path = lyr.source()
        if self.rb_gen.isChecked():
            out = self.fw_pts.filePath()
            if not out:
                self.run.error(tr("c.need.out"))
                return
            if not out.lower().endswith(".gpkg"):
                out += ".gpkg"
            args = dict(n_total=self.sp_n.value(), target_se=self.sp_se.value(), expected_ua=self.sp_ua.value(),
                        min_per=self.sp_min.value(), mode=("proportional", "equal")[self.cb_mode.currentIndex()],
                        n_hidden=self.sp_hid.value(), n_deep=self.sp_deep.value(), min_dist_m=self.sp_dist.value(),
                        seed=self.sp_seed.value())

            def work(log, progress, is_canceled):
                progress(10)
                return sampling.generate(path, out, log=log, **args)

            self.run.start("GLUB! · validation points", work, self._gen_done)
        else:
            pts = self.cb_pts.currentLayer()
            field = self.cb_field.currentField()
            out_dir = self.fw_dir.filePath()
            if pts is None or not field:
                self.run.error(tr("va.need.pts"))
                return
            if not out_dir:
                self.run.error(tr("c.need.out"))
                return
            xs, ys, refs = read_points_labels(pts.getFeatures(), pts.crs(), lyr.crs(),
                                              QgsProject.instance().transformContext(), field)
            settings = [(L("Class map", "Mapa de clases"), path),
                        (L("Validation points", "Puntos de validación"),
                         L(f"{pts.name()}, field '{field}'", f"{pts.name()}, campo '{field}'"))]

            def work(log, progress, is_canceled):
                progress(10)
                summ, warns = sampling.assess(path, xs, ys, refs, out_dir, log=log)
                rep = os.path.join(out_dir, "assessment.html")
                with open(rep, "w", encoding="utf-8") as fh:
                    fh.write(report.build_assessment(settings, summ, warns, CREDIT))
                return summ, rep

            self.report = None
            self.btn_report.setEnabled(False)
            self.lbl_res.clear()
            self.run.start("GLUB! · assessment", work, self._ass_done)

    def _gen_done(self, g):
        self.run.autosave(os.path.dirname(g["points"]))
        if self.chk_add.isChecked():
            v = QgsVectorLayer(g["points"] + "|layername=validation_points", tr("va.layer"), "ogr")
            if v.isValid():
                root = QgsProject.instance().layerTreeRoot()
                grp = root.findGroup(GROUP) or root.insertGroup(0, GROUP)
                QgsProject.instance().addMapLayer(v, False)
                grp.insertLayer(0, v)
                self.cb_pts.setLayer(v)

    def _ass_done(self, result):
        summ, rep = result
        self.report = rep
        self.run.autosave(os.path.dirname(rep))
        self.btn_report.setEnabled(True)
        adj = summ["adj"]
        if adj is None:
            self.lbl_res.setText(tr("va.res.none"))
            return
        unit = " ha" if summ["ha"] else " px"
        lines = [tr("va.res.oa", f"{100 * adj['oa']:.1f} %", f"{100 * summ['ci_oa']:.1f}", summ["n_used"])]
        for j, c in enumerate(summ["classes"]):
            lines.append(f"{c}: {adj['area'][j]:.1f} ± {adj['ci'][j]:.1f}{unit}")
        self.lbl_res.setText("\n".join(lines))

    def advanced(self):
        return [self.sp_se, self.sp_ua, self.sp_min, self.cb_mode, self.sp_hid, self.sp_deep, self.sp_dist, self.sp_seed]
