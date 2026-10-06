"""Tab 1: search and download Sentinel-2 from the Copernicus Data Space Ecosystem."""
from qgis.core import (QgsApplication, QgsAuthMethodConfig,
                       QgsCoordinateReferenceSystem, QgsSettings)
from qgis.gui import QgsAuthConfigSelect, QgsFileWidget
from qgis.PyQt.QtCore import QDate, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit,
                                 QDoubleSpinBox, QFormLayout, QGroupBox,
                                 QHBoxLayout, QHeaderView, QLabel, QPushButton,
                                 QSizePolicy,
                                 QTableWidget, QTableWidgetItem, QVBoxLayout,
                                 QWidget)

from ..core import cdse
from .area import AreaBox, AreaError
from .common import RunPanel, Translatable
from .i18n import tr

S = "Glub/download/"
LEVELS = (("L2A", "dl.level.l2a"), ("L1C", "dl.level.l1c"))
COLS = ("dl.col.date", "dl.col.tile", "dl.col.cloud", "dl.col.size", "dl.col.name")


class DownloadTab(QWidget, Translatable):
    HELP = "s4-1"
    downloaded = pyqtSignal(list)

    def __init__(self, iface, window, parent=None):
        super().__init__(parent)
        self.products = []
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.area = AreaBox(iface, window)
        top.addWidget(self.area, 1)

        g = QGroupBox()
        self._t(g.setTitle, "dl.search")
        f = QFormLayout(g)
        self.d_from, self.d_to = QDateEdit(), QDateEdit()
        for d in (self.d_from, self.d_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("yyyy-MM-dd")
            d.setMinimumDate(QDate(2015, 6, 23))
        today = QDate.currentDate()
        self.d_to.setDate(today)
        self.d_from.setDate(today.addMonths(-3))
        self.cb_level = QComboBox()
        self.sp_cloud = QDoubleSpinBox()
        self.sp_cloud.setRange(0, 100)
        self.sp_cloud.setValue(20)
        self.sp_cloud.setSuffix(" %")
        f.addRow(self._lbl("dl.from"), self.d_from)
        f.addRow(self._lbl("dl.to"), self.d_to)
        f.addRow(self._lbl("dl.level"), self.cb_level)
        f.addRow(self._lbl("dl.cloud"), self.sp_cloud)
        top.addWidget(g, 1)
        lay.addLayout(top)

        ga = QGroupBox()
        self._t(ga.setTitle, "dl.account")
        fa = QFormLayout(ga)
        self.auth = QgsAuthConfigSelect(self)
        self.auth.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        combo = self.auth.findChild(QComboBox)
        if combo is not None:  # the widget keeps room for a message we do not use
            self.auth.setMaximumHeight(combo.sizeHint().height() + 10)
        self.lbl_auth = QLabel()
        self.lbl_auth.setWordWrap(True)
        self.lbl_auth.setOpenExternalLinks(True)
        self.lbl_auth.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_auth.setStyleSheet("color: gray")
        self._t(self.lbl_auth.setText, "dl.auth.help")
        self.fw_out = QgsFileWidget()
        self.fw_out.setStorageMode(QgsFileWidget.StorageMode.GetDirectory)
        fa.addRow(self._lbl("dl.auth"), self.auth)
        fa.addRow(self.lbl_auth)
        fa.addRow(self._lbl("c.outdir"), self.fw_out)
        ga.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        lay.addWidget(ga)

        brow = QHBoxLayout()
        self.btn_search = QPushButton()
        self._t(self.btn_search.setText, "dl.btn.search")
        self.btn_search.clicked.connect(self.search)
        self.btn_all, self.btn_none = QPushButton(), QPushButton()
        self._t(self.btn_all.setText, "dl.btn.all")
        self._t(self.btn_none.setText, "dl.btn.none")
        self.btn_all.clicked.connect(lambda: self._check_all(True))
        self.btn_none.clicked.connect(lambda: self._check_all(False))
        self.lbl_total = QLabel("")
        brow.addWidget(self.btn_search)
        brow.addWidget(self.btn_all)
        brow.addWidget(self.btn_none)
        brow.addWidget(self.lbl_total, 1)
        lay.addLayout(brow)

        self.table = QTableWidget(0, len(COLS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(len(COLS) - 1, QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(lambda *_: self._update_total())
        lay.addWidget(self.table, 1)

        self.run = RunPanel("dl.btn.download")
        self.run.btn_run.clicked.connect(self.download)
        lay.addWidget(self.run)
        self._retranslate_extra()
        self._load()

    # ------------------------------------------------------------ settings
    def _load(self):
        s = QgsSettings()
        self.fw_out.setFilePath(s.value(S + "out", ""))
        self.auth.setConfigId(s.value(S + "auth", ""))
        self.sp_cloud.setValue(float(s.value(S + "cloud", 20)))
        self.cb_level.setCurrentIndex(int(s.value(S + "level", 0)))

    def _save(self):
        s = QgsSettings()
        s.setValue(S + "out", self.fw_out.filePath())
        s.setValue(S + "auth", self.auth.configId())
        s.setValue(S + "cloud", self.sp_cloud.value())
        s.setValue(S + "level", self.cb_level.currentIndex())

    def _retranslate_extra(self):
        i = max(self.cb_level.currentIndex(), 0)
        self.cb_level.clear()
        for code, key in LEVELS:
            self.cb_level.addItem(tr(key), code)
        self.cb_level.setCurrentIndex(i)
        self.table.setHorizontalHeaderLabels([tr(k) for k in COLS])
        self._update_total()

    # ------------------------------------------------------------ search
    def search(self):
        try:
            box, _geom = self.area.get(QgsCoordinateReferenceSystem("EPSG:4326"))
        except AreaError as e:
            self.run.error(str(e))
            return
        if box is None:
            self.run.error(tr("dl.need.area"))
            return
        self._save()
        wkt = cdse.bbox_to_wkt(box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum())
        start = self.d_from.date().toString("yyyy-MM-dd")
        end = self.d_to.date().toString("yyyy-MM-dd")
        level = self.cb_level.currentData()
        cloud = self.sp_cloud.value()

        def work(log, progress, is_canceled):
            log(tr("dl.searching"))
            return cdse.search(wkt, start, end, level=level, max_cloud=cloud)

        self.run.start("GLUB! · search", work, self._show, extra_buttons=[self.btn_search])

    def _show(self, products):
        products = sorted(products, key=lambda p: p["date"] or "")
        self.products = products
        self.table.blockSignals(True)
        self.table.setRowCount(len(products))
        for r, p in enumerate(products):
            info = cdse.parse_name(p["name"]) or {}
            date = (p["date"] or "")[:10]
            it = QTableWidgetItem(date)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(r, 0, it)
            cloud = p["cloud"]
            vals = (info.get("tile", ""), "" if cloud is None else f"{cloud:.1f}",
                    "" if not p["size"] else f"{p['size'] / 1e6:.0f}", p["name"])
            for c, v in enumerate(vals, start=1):
                self.table.setItem(r, c, QTableWidgetItem(v))
        self.table.blockSignals(False)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(len(COLS) - 1, QHeaderView.ResizeMode.Stretch)
        self.run.append(tr("dl.found", len(products)) if products else tr("dl.none"))
        self._update_total()

    def _checked(self):
        return [self.products[r] for r in range(self.table.rowCount())
                if self.table.item(r, 0).checkState() == Qt.CheckState.Checked]

    def _check_all(self, on):
        st = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(st)
        self.table.blockSignals(False)
        self._update_total()

    def _update_total(self):
        mb = sum((p["size"] or 0) for p in self._checked()) / 1e6 if self.products else 0
        self.lbl_total.setText(tr("dl.total", mb) if mb else "")

    # ------------------------------------------------------------ download
    def download(self):
        todo = self._checked()
        if not todo:
            self.run.error(tr("dl.need.sel"))
            return
        out = self.fw_out.filePath()
        if not out:
            self.run.error(tr("dl.need.dir"))
            return
        authid = self.auth.configId()
        if not authid:
            self.run.error(tr("dl.need.auth"))
            return
        cfg = QgsAuthMethodConfig()
        QgsApplication.authManager().loadAuthenticationConfig(authid, cfg, True)
        user, pwd = cfg.config("username"), cfg.config("password")
        if not user or not pwd:
            self.run.error(tr("dl.bad.auth"))
            return
        self._save()

        def work(log, progress, is_canceled):
            done = []
            for i, p in enumerate(todo):
                if is_canceled():
                    break
                log(tr("dl.getting", i + 1, len(todo), p["name"]))
                try:
                    token = cdse.get_token(user, pwd)  # they expire in minutes
                    path = cdse.download(p, out, token,
                                         progress=lambda f, i=i: progress(100 * (i + f) / len(todo)),
                                         is_canceled=is_canceled)
                except cdse.CDSEError as e:
                    log(str(e), True)
                    continue
                log(tr("dl.saved", path))
                done.append(path)
            return done

        self.run.start("GLUB! · download", work, self._downloaded, extra_buttons=[self.btn_search])

    def _downloaded(self, paths):
        if paths:
            self.downloaded.emit(paths)
