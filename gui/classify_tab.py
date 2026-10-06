"""Tab 6: supervised benthic classification with a three-state depth mask."""
import os

from qgis.core import QgsProject, QgsSettings
from qgis.gui import (QgsFieldComboBox, QgsFileWidget, QgsMapLayerComboBox,
                      QgsRasterBandComboBox)
from qgis.PyQt.QtCore import QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                                 QDoubleSpinBox, QFormLayout, QGroupBox,
                                 QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                                 QPushButton, QScrollArea, QSpinBox,
                                 QTableWidget, QTableWidgetItem, QVBoxLayout,
                                 QWidget)

from ..compat import POINT_GEOMETRY, POINT_LAYER, POLYGON_LAYER, RASTER_LAYER, layer_filters
from ..algorithms.aoi import read_training, union_features
from ..author import CREDIT
from ..core import pipeline, vectorize
from ..core.lang import L
from .common import RunPanel, Translatable, add_raster, add_vector, features_of, help_row
from .i18n import tr
from .rasterbox import RasterBox

S = "Glub/classify/"
BANDS = ("blue", "green", "red", "nir")
COLS = ("cl.col.class", "cl.col.nval", "cl.col.pa", "cl.col.ua", "cl.col.area")
SIGNS = ("cl.sign.auto", "cl.sign.depth", "cl.sign.elev")
SIGN_VALUES = ("auto", 1.0, -1.0)


def _raster_combo(allow_empty=True):
    cb = QgsMapLayerComboBox()
    cb.setFilters(RASTER_LAYER)
    if allow_empty:
        cb.setAllowEmptyLayer(True)
        cb.setLayer(None)
    return cb


def _form(box):
    f = QFormLayout(box)
    f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return f


def _gray(label):
    label.setWordWrap(True)
    label.setStyleSheet("color: gray")
    return label


def training_from_layer(layer, field, selected_only, dest_crs):
    is_point = layer.geometryType() == POINT_GEOMETRY
    return read_training(features_of(layer, selected_only), layer.crs(), is_point, dest_crs,
                         QgsProject.instance().transformContext(), field)


class ClassifyTab(QWidget, Translatable):
    HELP = "s4-6"
    classified = pyqtSignal(str)

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
        body = QVBoxLayout(inner)
        cols = QHBoxLayout()
        body.addLayout(cols)
        left, right = QVBoxLayout(), QVBoxLayout()
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)

        # ---- left: features
        self.rbox = RasterBox(BANDS)
        left.addWidget(self.rbox)
        gf = QGroupBox()
        self._t(gf.setTitle, "cl.feat")
        ff = _form(gf)
        ff.addRow(help_row("s4-6-feat"))
        row = QHBoxLayout()
        self.chk_b = {}
        for b in BANDS:
            c = QCheckBox()
            self._t(c.setText, "ba.b." + b)
            c.setChecked(b != "nir")
            self.chk_b[b] = c
            row.addWidget(c)
        row.addStretch()
        ff.addRow(self._lbl("cl.use"), row)
        self.cb_dii = _raster_combo()
        self._t(self.cb_dii.setToolTip, "cl.dii.tip")
        ff.addRow(self._lbl("cl.dii"), self.cb_dii)
        self.chk_depthfeat = QCheckBox()
        self._t(self.chk_depthfeat.setText, "cl.depthfeat")
        self._t(self.chk_depthfeat.setToolTip, "cl.depthfeat.tip")
        ff.addRow(self.chk_depthfeat)
        self.cb_tex = QComboBox()
        self._t(self.cb_tex.setToolTip, "cl.tex.tip")
        ff.addRow(self._lbl("cl.tex"), self.cb_tex)
        left.addWidget(gf)

        # ---- left: reference data
        gt = QGroupBox()
        self._t(gt.setTitle, "cl.train")
        ft = _form(gt)
        ft.addRow(help_row("s4-6-ref"))
        self.cb_train = QgsMapLayerComboBox()
        self.cb_train.setFilters(layer_filters(POINT_LAYER, POLYGON_LAYER))
        self.cb_field = QgsFieldComboBox()
        self.cb_train.layerChanged.connect(self.cb_field.setLayer)
        self.cb_field.setLayer(self.cb_train.currentLayer())
        self.chk_sel = QCheckBox()
        self._t(self.chk_sel.setText, "c.selected")
        self.sp_maxpoly = QSpinBox()
        self.sp_maxpoly.setRange(0, 100000)
        self.sp_maxpoly.setValue(200)
        ft.addRow(self._lbl("cl.train.layer"), self.cb_train)
        ft.addRow("", self.chk_sel)
        ft.addRow(self._lbl("cl.train.field"), self.cb_field)
        ft.addRow(self._lbl("cl.maxpoly"), self.sp_maxpoly)
        self.sp_shrink = QDoubleSpinBox()
        self.sp_shrink.setRange(0, 1000)
        self.sp_shrink.setDecimals(1)
        self.sp_shrink.setSuffix(" m")
        self._t(self.sp_shrink.setToolTip, "cl.shrink.tip")
        ft.addRow(self._lbl("cl.shrink"), self.sp_shrink)
        h = QLabel()
        self._t(h.setText, "cl.train.help")
        ft.addRow(_gray(h))
        left.addWidget(gt)

        # ---- left: output
        go = QGroupBox()
        self._t(go.setTitle, "c.output")
        fo = _form(go)
        self.fw_out = QgsFileWidget()
        self.fw_out.setStorageMode(QgsFileWidget.StorageMode.GetDirectory)
        self.chk_add = QCheckBox()
        self._t(self.chk_add.setText, "c.addmap")
        self.chk_add.setChecked(True)
        self.chk_prob = QCheckBox()
        self._t(self.chk_prob.setText, "cl.addprob")
        fo.addRow(self._lbl("c.outdir"), self.fw_out)
        fo.addRow("", self.chk_add)
        fo.addRow("", self.chk_prob)
        self.chk_vec = QCheckBox()
        self._t(self.chk_vec.setText, "cl.vec")
        self._t(self.chk_vec.setToolTip, "cl.vec.tip")
        fo.addRow("", self.chk_vec)
        left.addWidget(go)
        left.addStretch()

        # ---- right: depth mask
        gm = QGroupBox()
        self._t(gm.setTitle, "cl.mask")
        fm = _form(gm)
        fm.addRow(help_row("s4-6-mask"))
        self.cb_opt = _raster_combo()
        self._t(self.cb_opt.setToolTip, "cl.opt.tip")
        self.cb_opt_band = QgsRasterBandComboBox()
        self.cb_opt.layerChanged.connect(self.cb_opt_band.setLayer)
        self.cb_opt_sign = QComboBox()
        self.sp_optlim = QDoubleSpinBox()
        self.sp_optlim.setRange(0, 100)
        self.sp_optlim.setDecimals(1)
        self.sp_optlim.setSuffix(" m")
        self._t(self.sp_optlim.setSpecialValueText, "cl.optlim.auto")
        self._t(self.sp_optlim.setToolTip, "cl.optlim.tip")
        self.cb_trust = _raster_combo()
        self._t(self.cb_trust.setToolTip, "cl.trust.tip")
        self.cb_eco = _raster_combo()
        self._t(self.cb_eco.setToolTip, "cl.eco.tip")
        self.cb_eco_band = QgsRasterBandComboBox()
        self.cb_eco.layerChanged.connect(self.cb_eco_band.setLayer)
        self.cb_eco_sign = QComboBox()
        self.sp_ecolim = QDoubleSpinBox()
        self.sp_ecolim.setRange(1, 200)
        self.sp_ecolim.setDecimals(1)
        self.sp_ecolim.setSuffix(" m")
        self.sp_ecolim.setValue(float(QgsSettings().value(S + "ecolim", 35.0)))
        self._t(self.sp_ecolim.setToolTip, "cl.ecolim.tip")
        fm.addRow(self._lbl("cl.opt"), self.cb_opt)
        fm.addRow("", self.cb_opt_band)
        fm.addRow(self._lbl("cl.sign"), self.cb_opt_sign)
        fm.addRow(self._lbl("cl.optlim"), self.sp_optlim)
        fm.addRow(self._lbl("cl.trust"), self.cb_trust)
        fm.addRow(self._lbl("cl.eco"), self.cb_eco)
        fm.addRow("", self.cb_eco_band)
        fm.addRow(self._lbl("cl.sign"), self.cb_eco_sign)
        fm.addRow(self._lbl("cl.ecolim"), self.sp_ecolim)
        self.cb_sig = QgsMapLayerComboBox()
        self.cb_sig.setFilters(POLYGON_LAYER)
        self.cb_sig.setAllowEmptyLayer(True)
        self.cb_sig.setLayer(None)
        self._t(self.cb_sig.setToolTip, "cl.sig.tip")
        self.sp_nsig = QDoubleSpinBox()
        self.sp_nsig.setRange(1, 10)
        self.sp_nsig.setSingleStep(0.5)
        self.sp_nsig.setValue(3.0)
        srow = QHBoxLayout()
        self.row_sig = srow
        self.chk_sig = {}
        for b in ("blue", "green", "red"):
            cb = QCheckBox()
            self._t(cb.setText, "ba.b." + b)
            cb.setChecked(b != "red")
            self.chk_sig[b] = cb
            srow.addWidget(cb)
        srow.addStretch()
        fm.addRow(self._lbl("cl.sig"), self.cb_sig)
        fm.addRow(self._lbl("cl.nsig"), self.sp_nsig)
        fm.addRow(self._lbl("cl.sigbands"), srow)
        hm = QLabel()
        self._t(hm.setText, "cl.mask.help")
        fm.addRow(_gray(hm))
        right.addWidget(gm)

        # ---- right: classifier and validation
        gc = QGroupBox()
        self._t(gc.setTitle, "cl.model")
        fc = _form(gc)
        fc.addRow(help_row("s4-6-model"))
        self.cb_method = QComboBox()
        self.sp_trees = QSpinBox()
        self.sp_trees.setRange(10, 5000)
        self.sp_trees.setValue(300)
        self.chk_bal = QCheckBox()
        self._t(self.chk_bal.setText, "cl.balanced")
        self._t(self.chk_bal.setToolTip, "cl.balanced.tip")
        self.chk_bal.setChecked(False)
        self.sp_minp = QDoubleSpinBox()
        self.sp_minp.setRange(0.0, 0.99)
        self.sp_minp.setSingleStep(0.05)
        self.sp_minp.setDecimals(2)
        self.sp_minp.setValue(0.0)
        self._t(self.sp_minp.setSpecialValueText, "cl.minprob.off")
        self._t(self.sp_minp.setToolTip, "cl.minprob.tip")
        self.cb_method.currentIndexChanged.connect(self._method_changed)
        self.cb_split = QComboBox()
        self.sp_block = QDoubleSpinBox()
        self.sp_block.setRange(1, 1e6)
        self.sp_block.setDecimals(0)
        self.sp_block.setValue(500)
        self.sp_block.setSuffix(" m")
        self.cb_split.currentIndexChanged.connect(lambda i: self.sp_block.setEnabled(i != 1))
        self.sp_val = QDoubleSpinBox()
        self.sp_val.setRange(0.05, 0.9)
        self.sp_val.setSingleStep(0.05)
        self.sp_val.setValue(0.3)
        self.sp_seed = QSpinBox()
        self.sp_seed.setRange(0, 2 ** 31 - 1)
        self.sp_seed.setValue(42)
        self.le_bins = QLineEdit("0,2,5,10,15,20")
        fc.addRow(self._lbl("cl.method"), self.cb_method)
        fc.addRow(self._lbl("cl.trees"), self.sp_trees)
        fc.addRow("", self.chk_bal)
        fc.addRow(self._lbl("cl.minprob"), self.sp_minp)
        fc.addRow(self._lbl("cl.split"), self.cb_split)
        fc.addRow(self._lbl("cl.block"), self.sp_block)
        fc.addRow(self._lbl("cl.valfrac"), self.sp_val)
        fc.addRow(self._lbl("cl.seed"), self.sp_seed)
        fc.addRow(self._lbl("cl.bins"), self.le_bins)
        right.addWidget(gc)
        gpo = QGroupBox()
        self.g_post = gpo
        self._t(gpo.setTitle, "cl.post")
        fpo = _form(gpo)
        self.cb_filter = QComboBox()
        self.sp_mmu = QSpinBox()
        self.sp_mmu.setRange(0, 1000000)
        self._t(self.sp_mmu.setToolTip, "cl.mmu.tip")
        fpo.addRow(self._lbl("cl.filter"), self.cb_filter)
        fpo.addRow(self._lbl("cl.mmu"), self.sp_mmu)
        hp = QLabel()
        self._t(hp.setText, "cl.post.help")
        fpo.addRow(_gray(hp))
        right.addWidget(gpo)
        right.addStretch()

        # ---- results
        gr = QGroupBox()
        self._t(gr.setTitle, "cl.results")
        vr = QVBoxLayout(gr)
        self.lbl_oa = QLabel()
        self.lbl_oa.setWordWrap(True)
        vr.addWidget(self.lbl_oa)
        self.table = QTableWidget(0, len(COLS))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(140)
        vr.addWidget(self.table)
        self.btn_report = QPushButton()
        self._t(self.btn_report.setText, "cl.open")
        self.btn_report.setEnabled(False)
        self.btn_report.clicked.connect(self._open_report)
        vr.addWidget(self.btn_report)
        body.addWidget(gr)

        self.run = RunPanel()
        self.run.btn_run.clicked.connect(self.start)
        outer.addWidget(self.run)
        self._retranslate_extra()
        self.fw_out.setFilePath(QgsSettings().value(S + "out", ""))

    # ------------------------------------------------------------ helpers
    def set_raster(self, path):
        self.rbox.set_path(path)

    def set_dii(self, path):
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.source() == path:
                self.cb_dii.setLayer(lyr)
                return

    def _method_changed(self, i):
        self.sp_trees.setEnabled(i == 0)

    def _refill(self, combo, keys):
        i = max(combo.currentIndex(), 0)
        combo.blockSignals(True)
        combo.clear()
        for k in keys:
            combo.addItem(tr(k))
        combo.setCurrentIndex(i)
        combo.blockSignals(False)

    def _retranslate_extra(self):
        self._refill(self.cb_opt_sign, SIGNS)
        self._refill(self.cb_eco_sign, SIGNS)
        self._refill(self.cb_method, ("cl.m.rf", "cl.m.ml"))
        self._refill(self.cb_split, ("cl.split.blocks", "cl.split.random", "cl.split.common"))
        i = max(self.cb_filter.currentIndex(), 0)
        self.cb_filter.clear()
        self.cb_filter.addItems([tr("cl.filter.off"), "3 × 3", "5 × 5"])
        self.cb_filter.setCurrentIndex(i)
        j = max(self.cb_tex.currentIndex(), 0)
        self.cb_tex.clear()
        self.cb_tex.addItems([tr("cl.filter.off"), "3 × 3", "5 × 5"])
        self.cb_tex.setCurrentIndex(j)
        self.table.setHorizontalHeaderLabels([tr(k) for k in COLS])

    def _open_report(self):
        if self.report and os.path.exists(self.report):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.report))

    # ------------------------------------------------------------ run
    def start(self):
        lyr = self.rbox.layer()
        if lyr is None:
            self.run.error(tr("c.need.raster"))
            return
        allidx = self.rbox.indices()
        idx = {b: allidx[b] for b in BANDS if self.chk_b[b].isChecked()}
        dii = self.cb_dii.currentLayer()
        if not idx and dii is None:
            self.run.error(tr("cl.need.feat"))
            return
        if not idx:  # the reflectance still defines the grid and the water pixels
            idx = {"blue": allidx["blue"]}
            self.run.append(L("Reflectance blue band used only to define the grid and the water pixels.",
                              "La banda azul de reflectancia solo se usa para la rejilla y los píxeles de agua."), True)
            use_refl = False
        else:
            use_refl = True
        train, field = self.cb_train.currentLayer(), self.cb_field.currentField()
        if train is None or not field:
            self.run.error(tr("cl.need.train"))
            return
        out_dir = self.fw_out.filePath()
        if not out_dir:
            self.run.error(tr("c.need.out"))
            return
        try:
            edges = [float(s) for s in self.le_bins.text().split(",") if s.strip()]
        except ValueError:
            self.run.error(tr("c.failed", self.le_bins.text()))
            return
        opt, eco, trust = self.cb_opt.currentLayer(), self.cb_eco.currentLayer(), self.cb_trust.currentLayer()
        if self.chk_depthfeat.isChecked() and opt is None:
            self.run.error(tr("cl.need.opt"))
            return
        if opt is None and eco is not None and self.sp_optlim.value() == 0:
            self.run.error(tr("cl.need.optlim"))
            return
        training, skipped = training_from_layer(train, field, self.chk_sel.isChecked(), lyr.crs())
        n_feat = len(training.get("xs") or training.get("wkts") or [])
        if skipped:
            self.run.append(tr("cl.skipped", skipped), True)
        if n_feat < 4:
            self.run.error(tr("cl.few", n_feat))
            return
        QgsSettings().setValue(S + "out", out_dir)
        QgsSettings().setValue(S + "ecolim", self.sp_ecolim.value())

        mask = {}
        if opt is not None:
            mask.update(opt_path=opt.source(), opt_band=self.cb_opt_band.currentBand(),
                        opt_sign=SIGN_VALUES[self.cb_opt_sign.currentIndex()])
        if self.sp_optlim.value() > 0:
            mask["opt_limit"] = self.sp_optlim.value()
        if trust is not None:
            mask["trust_path"] = trust.source()
        if eco is not None:
            mask.update(eco_path=eco.source(), eco_band=self.cb_eco_band.currentBand(),
                        eco_sign=SIGN_VALUES[self.cb_eco_sign.currentIndex()], eco_limit=self.sp_ecolim.value())
        sig = self.cb_sig.currentLayer()
        if sig is not None:
            sbands = [b for b in ("blue", "green", "red") if self.chk_sig[b].isChecked()]
            if not sbands:
                self.run.error(tr("cl.need.sigband"))
                return
            gs, _n = union_features(sig.getFeatures(), sig.crs(), lyr.crs(),
                                    QgsProject.instance().transformContext())
            if gs is None:
                self.run.error(tr("c.nopoly"))
                return
            mask.update(deep_wkt=gs.asWkt(), sig_bands={b: allidx[b] for b in sbands},
                        n_sigma=self.sp_nsig.value())
        extra = []
        if self.chk_depthfeat.isChecked():
            extra.append((opt.source(), self.cb_opt_band.currentBand(), "depth"))
            self.run.append(tr("cl.depthwarn"), True)
        method = "rf" if self.cb_method.currentIndex() == 0 else "ml"
        opts = dict(method=method, trees=self.sp_trees.value(), balanced=self.chk_bal.isChecked(),
                    split=("blocks", "random", "blocks_all")[self.cb_split.currentIndex()],
                    block_size=self.sp_block.value(), val_fraction=self.sp_val.value(),
                    seed=self.sp_seed.value(), max_per_polygon=self.sp_maxpoly.value(), depth_bins=edges,
                    shrink=self.sp_shrink.value(), filter_window=(0, 3, 5)[self.cb_filter.currentIndex()],
                    mmu=self.sp_mmu.value(), min_prob=self.sp_minp.value(),
                    texture_window=(0, 3, 5)[max(self.cb_tex.currentIndex(), 0)])
        no = L("none", "ninguno")
        kind = {"points": L("points", "puntos"), "polygons": L("polygons", "polígonos")}[training["kind"]]
        split_txt = {"blocks": L("blocks by class", "bloques por clase"), "random": L("random", "al azar"),
                     "blocks_all": L("common blocks", "bloques comunes")}[opts["split"]]
        settings = [
            (L("Reflectance", "Reflectancia"), lyr.source()),
            (L("Reflectance bands used", "Bandas de reflectancia usadas"),
             ", ".join(L(f"{k} (band {v})", f"{k} (banda {v})") for k, v in idx.items()) if use_refl else no),
            (L("Water-column indices", "Índices de columna de agua"), dii.source() if dii else no),
            (L("Reference data", "Verdad de campo"),
             L(f"{train.name()} ({kind}), field '{field}', {n_feat} features",
               f"{train.name()} ({kind}), campo '{field}', {n_feat} objetos")),
            (L("Depth for the optical limit", "Profundidad para el límite óptico"), opt.source() if opt else no),
            (L("StarShoal trust", "Confianza de StarShoal"), trust.source() if trust else no),
            (L("Independent bathymetry", "Batimetría independiente"), eco.source() if eco else no),
            (L("Deep-water polygon (signal test)", "Polígono de agua profunda (prueba de señal)"),
             sig.name() if sig else no),
            (L("Method", "Método"), "Random Forest" if method == "rf" else L("Maximum likelihood (Gaussian)",
                                                                              "Máxima verosimilitud (gaussiana)")),
            (L("Split", "Separación"),
             L(f"{split_txt}, block {opts['block_size']:g} m, validation {opts['val_fraction']:g}, seed {opts['seed']}",
               f"{split_txt}, bloque {opts['block_size']:g} m, validación {opts['val_fraction']:g}, "
               f"semilla {opts['seed']}")),
        ]
        src = lyr.source()
        feat_idx = idx
        dii_path = dii.source() if dii else None
        if not use_refl:
            opts["refl_features"] = False

        to_vec = self.chk_vec.isChecked()

        def work(log, progress, is_canceled):
            res = pipeline.classify_file(src, feat_idx, training, opts, out_dir, dii_path=dii_path,
                                         extra=extra, mask=mask, settings=settings, credit=CREDIT,
                                         log=log, progress=progress)
            if to_vec:
                written = res[2]
                base = written.get("classes_filtered") or written["classes"]
                try:   # the maps are already written: a polygon failure must not lose the run
                    written["polygons"] = vectorize.polygonize(base, os.path.splitext(base)[0] + ".gpkg",
                                                               log=log)["path"]
                except Exception as e:
                    log(L(f"Polygons not written: {e}", f"No se han escrito los polígonos: {e}"), True)
            return res

        self.btn_report.setEnabled(False)
        self.table.setRowCount(0)
        self.lbl_oa.clear()
        self.run.start("GLUB! · classification", work, self._done)

    def _done(self, result):
        s, _warns, written = result
        a, m = s["acc"], s["mask"]
        oa = "n/a" if not a["n"] else f"{100 * a['oa']:.1f} %"
        text = tr("cl.oa", oa, a["n"], m["visible"], m["hidden"], m["too_deep"])
        g = s.get("groups_acc")
        if g:
            text += "\n" + tr("cl.oa.poly", f"{100 * g['oa']:.1f} %", g["n"])
        f = s.get("filtered")
        if f and f.get("acc"):
            ga = f.get("groups_acc")
            text += "\n" + tr("cl.oa.filt", f"{100 * f['acc']['oa']:.1f} %",
                               f" / {100 * ga['oa']:.1f} %" if ga else "")
        if s.get("min_prob"):
            nv = a["n"] + a.get("n_unsure", 0)
            text += "\n" + tr("cl.oa.unsure", s["min_prob"], s["n_unsure_px"],
                              f"{100 * a.get('n_unsure', 0) / max(nv, 1):.1f} %")
        self.lbl_oa.setText(text)
        classes = s["classes"]
        self.table.setRowCount(len(classes))
        unit = " ha" if s["ha"] else " px"

        def pct(v):
            return "n/a" if v != v else f"{100 * v:.0f} %"

        for r, c in enumerate(classes):
            vals = [c, str(s["n_val_class"][r]), pct(a["pa"][r]) if a["n"] else "n/a",
                    pct(a["ua"][r]) if a["n"] else "n/a", f"{s['map_px'][r] * (s['ha'] or 1):.1f}{unit}"]
            for col, v in enumerate(vals):
                self.table.setItem(r, col, QTableWidgetItem(v))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.report = written.get("report")
        self.btn_report.setEnabled(bool(self.report))
        if self.chk_add.isChecked():
            if self.chk_prob.isChecked():
                add_raster(written["probability"], "max_probability", "prob")
            add_raster(written["classes"], "classes", "classes", legend=written["legend"])
            if written.get("classes_filtered"):
                add_raster(written["classes_filtered"], "classes_filtered", "classes", legend=written["legend"])
            if written.get("polygons"):
                add_vector(written["polygons"], "classes", os.path.splitext(os.path.basename(written["polygons"]))[0])
        self.run.autosave(os.path.dirname(written["classes"]))
        self.classified.emit(written["classes"])

    def advanced(self):
        return [self.chk_depthfeat, self.cb_tex, self.sp_maxpoly, self.sp_shrink, self.cb_opt_band, self.cb_opt_sign, self.cb_trust, self.cb_eco_band, self.cb_eco_sign, self.sp_nsig, self.row_sig, self.sp_trees, self.chk_bal, self.sp_minp, self.cb_split, self.sp_block, self.sp_val, self.sp_seed, self.le_bins, self.g_post]
