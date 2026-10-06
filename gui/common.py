"""Pieces shared by the GLUB tabs."""
import os
import traceback

from qgis.core import (Qgis, QgsApplication, QgsColorRampShader,
                       QgsContrastEnhancement, QgsMessageLog,
                       QgsMultiBandColorRenderer, QgsPalettedRasterRenderer,
                       QgsProject, QgsRasterLayer,
                       QgsRasterShader, QgsSingleBandPseudoColorRenderer,
                       QgsStyle, QgsTask)
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit,
                                 QProgressBar, QPushButton, QVBoxLayout,
                                 QWidget)

from .i18n import tr

TAG = "GLUB"
GROUP = "GLUB"


class Translatable:
    """Remembers which widget texts come from which key, to switch language live."""

    def _t(self, setter, key, *args):
        if not hasattr(self, "_tr_items"):
            self._tr_items = []
        setter(tr(key, *args))
        self._tr_items.append((setter, key, args))

    def _lbl(self, key):
        lab = QLabel()
        self._t(lab.setText, key)
        return lab

    def retranslate(self):
        for setter, key, args in getattr(self, "_tr_items", []):
            setter(tr(key, *args))
        self._retranslate_extra()

    def _retranslate_extra(self):
        """Override for things that are not a single setter (combo items, headers...)."""

    # ---- simple / advanced mode
    def advanced(self):
        """Widgets (or row layouts, or whole boxes) hidden in simple mode. Override in each tab."""
        return []

    def set_simple(self, simple):
        for w in self.advanced():
            show_row(w, not simple)


def show_row(w, visible):
    """Show or hide a widget (or a row layout) together with its label in a form layout."""
    from qgis.PyQt.QtWidgets import QFormLayout, QLayout
    if isinstance(w, QLayout):
        for i in range(w.count()):
            item = w.itemAt(i).widget()
            if item is not None:
                item.setVisible(visible)
        parent = w.parentWidget()
    else:
        w.setVisible(visible)
        parent = w.parentWidget()
    form = parent.layout() if parent is not None else None
    if isinstance(form, QFormLayout):
        lab = form.labelForField(w)
        if lab is not None:
            lab.setVisible(visible)


def manual_path():
    import os as _os
    from . import i18n
    return _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "docs", "html", f"manual_{i18n.lang()}.html")


def open_manual(anchor=""):
    """Open the HTML manual at a section. Through a tiny redirect page, because some systems drop the
    '#section' part of a file link."""
    import tempfile
    from qgis.PyQt.QtCore import QUrl
    from qgis.PyQt.QtGui import QDesktopServices
    target = QUrl.fromLocalFile(manual_path())
    if anchor:
        target.setFragment(anchor)
    page = os.path.join(tempfile.gettempdir(), "glub_help.html")
    try:
        with open(page, "w", encoding="utf-8") as fh:
            fh.write(f"<!doctype html><meta charset='utf-8'><meta http-equiv='refresh' content='0; url="
                     f"{target.toString()}'><a href='{target.toString()}'>GLUB</a>")
        QDesktopServices.openUrl(QUrl.fromLocalFile(page))
    except OSError:
        QDesktopServices.openUrl(target)


def help_button(anchor):
    """Small '?' button that opens the manual at the given section."""
    from qgis.PyQt.QtWidgets import QToolButton
    b = QToolButton()
    b.setText("?")
    b.setToolTip(tr("c.help.tip"))
    b.clicked.connect(lambda: open_manual(anchor))
    return b


def help_row(anchor):
    """A row with the '?' button on the right, for the top of a group box."""
    row = QHBoxLayout()
    row.addStretch()
    row.addWidget(help_button(anchor))
    return row


class FunctionTask(QgsTask):
    """Runs fn(log=, progress=, is_canceled=) in the background; result in .result."""
    message = pyqtSignal(str, bool)

    def __init__(self, title, fn):
        super().__init__(title, QgsTask.Flag.CanCancel)
        self.fn = fn
        self.result = None
        self.error = None

    def _log(self, msg, warn=False):
        self.message.emit(str(msg), bool(warn))

    def run(self):
        try:
            self.result = self.fn(log=self._log, progress=self.setProgress,
                                  is_canceled=self.isCanceled)
            return not self.isCanceled()
        except Exception as e:  # reported in the panel and the QGIS log
            self.error = str(e) or e.__class__.__name__
            QgsMessageLog.logMessage(traceback.format_exc(), TAG, Qgis.MessageLevel.Warning)
            return False


class RunPanel(QWidget, Translatable):
    """Run and Cancel buttons, a progress bar and a log box."""

    def __init__(self, run_key="c.run", parent=None):
        super().__init__(parent)
        self.task = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.btn_run = QPushButton()
        self._t(self.btn_run.setText, run_key)
        self.btn_cancel = QPushButton()
        self._t(self.btn_cancel.setText, "c.cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        row.addWidget(self.bar, 1)
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_run)
        lay.addLayout(row)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setMinimumHeight(90)
        self.log.setMaximumHeight(150)
        lay.addWidget(self.log)

    def set_owner(self, tab):
        """Add 'Save settings' and 'Load settings' buttons for the tab that holds this panel."""
        self.owner = tab
        row = self.layout().itemAt(0).layout()
        anchor = getattr(tab, "HELP", None)
        off = 0
        if anchor:
            row.insertWidget(0, help_button(anchor))
            off = 1
        for i, (key, fn) in enumerate((("c.save", self._save_settings), ("c.load", self._load_settings))):
            b = QPushButton()
            self._t(b.setText, key)
            b.clicked.connect(fn)
            row.insertWidget(i + off, b)
        return self

    def _save_settings(self):
        from qgis.PyQt.QtWidgets import QFileDialog
        from . import settings_io
        path, _ = QFileDialog.getSaveFileName(self, tr("c.save"), "", "JSON (*.json)")
        if path:
            if not path.lower().endswith(".json"):
                path += ".json"
            settings_io.save(self.owner, path)
            self.append(tr("c.saved", path))

    def _load_settings(self):
        from qgis.PyQt.QtWidgets import QFileDialog
        from . import settings_io
        path, _ = QFileDialog.getOpenFileName(self, tr("c.load"), "", "JSON (*.json)")
        if path:
            try:
                missing = settings_io.load(self.owner, path)
            except Exception as e:   # broken or hand-edited file
                self.error(tr("c.failed", e))
                return
            self.append(tr("c.loaded", path))
            for m in missing:
                self.append(tr("c.load.missing", m), True)

    def autosave(self, folder):
        """Write the settings of the run next to its outputs (glub_settings_<tab>.json)."""
        if not folder or getattr(self, "owner", None) is None:
            return None
        from . import settings_io
        try:
            os.makedirs(folder, exist_ok=True)
            p = os.path.join(folder, f"glub_settings_{type(self.owner).__name__}.json")
            settings_io.save(self.owner, p)
            self.append(tr("c.saved", p))
            return p
        except OSError as e:
            self.append(tr("c.failed", e), True)
            return None

    def busy(self):
        return self.task is not None

    def append(self, msg, warn=False):
        if warn:
            self.log.appendHtml(f"<span style='color:#b35c00'>{_esc(msg)}</span>")
        else:
            self.log.appendPlainText(msg)

    def error(self, msg):
        self.log.appendHtml(f"<span style='color:#c0392b'><b>{_esc(msg)}</b></span>")

    def start(self, title, fn, on_done=None, extra_buttons=()):
        """Launch fn in a QgsTask. on_done(result) runs in the main thread if it succeeds."""
        if self.task is not None:
            self.error(tr("c.busy"))
            return
        self.bar.setValue(0)
        self._extra = list(extra_buttons)
        for b in [self.btn_run] + self._extra:
            b.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        task = FunctionTask(title, fn)
        task.message.connect(self.append)
        task.progressChanged.connect(lambda p: self.bar.setValue(int(p)))
        task.taskCompleted.connect(lambda: self._finish(True, on_done))
        task.taskTerminated.connect(lambda: self._finish(False, on_done))
        self.task = task
        QgsApplication.taskManager().addTask(task)

    def _finish(self, ok, on_done):
        task, self.task = self.task, None
        for b in [self.btn_run] + getattr(self, "_extra", []):
            b.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        if task is None:
            return
        if ok:
            self.bar.setValue(100)
            try:
                if on_done:
                    on_done(task.result)
                self.append(tr("c.done"))
            except Exception as e:
                self.error(tr("c.failed", e))
                QgsMessageLog.logMessage(traceback.format_exc(), TAG, Qgis.MessageLevel.Warning)
        elif task.error:
            self.error(tr("c.failed", task.error))
        else:
            self.append(tr("c.canceled"), True)

    def cancel(self):
        if self.task is not None:
            self.task.cancel()

    def detach(self):
        """Plugin unload: cancel the task and cut its signals, so a task that ends later does not
        touch widgets that no longer exist."""
        task, self.task = self.task, None
        if task is None:
            return
        for sig in (task.message, task.progressChanged, task.taskCompleted, task.taskTerminated):
            try:
                sig.disconnect()
            except (TypeError, RuntimeError):
                pass
        task.cancel()


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def add_raster(path, name, style=None, inverted=False, legend=None):
    """Add a raster to the GLUB group.

    style: 'rgb' (bands 3,2,1), 'depth', 'sd', 'prob' (0-1 ramp on band 1),
    'index' (grey stretch on band 1) or 'classes' (paletted, legend = [(code, label, '#rrggbb')]).
    """
    lyr = QgsRasterLayer(path, name)
    if not lyr.isValid():
        return None
    try:
        if style == "classes" and legend:
            classes = [QgsPalettedRasterRenderer.Class(int(c), QColor(col), str(lab)) for c, lab, col in legend]
            lyr.setRenderer(QgsPalettedRasterRenderer(lyr.dataProvider(), 1, classes))
        elif style in ("prob", "index"):
            if style == "prob":
                lo, hi = 0.0, 1.0
            else:
                st = lyr.dataProvider().bandStatistics(1)
                lo, hi = st.minimumValue, st.maximumValue
            ramp = QgsStyle.defaultStyle().colorRamp("Viridis" if style == "prob" else "Greys")
            if ramp is not None:
                fn = QgsColorRampShader(lo, hi, ramp)
                fn.classifyColorRamp(5, -1)
                shader = QgsRasterShader()
                shader.setRasterShaderFunction(fn)
                lyr.setRenderer(QgsSingleBandPseudoColorRenderer(lyr.dataProvider(), 1, shader))
        elif style == "rgb" and lyr.bandCount() >= 3:
            r = QgsMultiBandColorRenderer(lyr.dataProvider(), 3, 2, 1)
            lyr.setRenderer(r)
            lyr.setContrastEnhancement(QgsContrastEnhancement.ContrastEnhancementAlgorithm.StretchToMinimumMaximum)
        elif style in ("depth", "sd"):
            st = lyr.dataProvider().bandStatistics(1)
            ramp = QgsStyle.defaultStyle().colorRamp("Blues" if style == "depth" else "Reds")
            if ramp is not None:
                if inverted:
                    ramp.invert()
                fn = QgsColorRampShader(st.minimumValue, st.maximumValue, ramp)
                fn.classifyColorRamp(5, -1)
                shader = QgsRasterShader()
                shader.setRasterShaderFunction(fn)
                lyr.setRenderer(QgsSingleBandPseudoColorRenderer(lyr.dataProvider(), 1, shader))
    except Exception as e:  # styling is a nicety, never a reason to fail
        QgsMessageLog.logMessage(f"Style for {name}: {e}", TAG, Qgis.MessageLevel.Info)
    root = QgsProject.instance().layerTreeRoot()
    g = root.findGroup(GROUP) or root.insertGroup(0, GROUP)
    QgsProject.instance().addMapLayer(lyr, False)
    g.insertLayer(0, lyr)
    return lyr


def add_vector(path, layer_name, name):
    """Add a vector layer (GeoPackage layer) to the GLUB group, styled by its 'class' field when it has one."""
    from qgis.core import QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsSymbol, QgsVectorLayer
    lyr = QgsVectorLayer(f"{path}|layername={layer_name}", name, "ogr")
    if not lyr.isValid():
        return None
    try:
        idx = lyr.fields().indexOf("class")
        if idx >= 0:
            from ..core.pipeline import class_color
            cats = []
            for i, v in enumerate(sorted(lyr.uniqueValues(idx))):
                sym = QgsSymbol.defaultSymbol(lyr.geometryType())
                sym.setColor(QColor(class_color(v, i)))
                cats.append(QgsRendererCategory(v, sym, str(v)))
            lyr.setRenderer(QgsCategorizedSymbolRenderer("class", cats))
    except Exception as e:  # styling is a nicety
        QgsMessageLog.logMessage(f"Style for {name}: {e}", TAG, Qgis.MessageLevel.Info)
    root = QgsProject.instance().layerTreeRoot()
    g = root.findGroup(GROUP) or root.insertGroup(0, GROUP)
    QgsProject.instance().addMapLayer(lyr, False)
    g.insertLayer(0, lyr)
    return lyr


def features_of(layer, selected_only):
    return layer.getSelectedFeatures() if selected_only else layer.getFeatures()
