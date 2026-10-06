"""Save and load the settings of a tab as a JSON file, to repeat a run exactly.

Every input widget held by the tab (and by its boxes: image, area...) is written
under its attribute name. Layers are stored by their source path; on loading,
a layer already in the project is reused, otherwise the file is added to the
project if it still exists.
"""
import datetime
import json
import os

from qgis.core import (QgsCoordinateReferenceSystem, QgsProject, QgsRasterLayer,
                       QgsRectangle, QgsVectorLayer)
from qgis.gui import (QgsExtentWidget, QgsFieldComboBox, QgsFileWidget,
                      QgsMapLayerComboBox, QgsRasterBandComboBox)
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                                 QGroupBox, QLineEdit, QListWidget,
                                 QRadioButton, QSpinBox, QWidget)

FORMAT = "GLUB settings 1"
SKIP = ("run", "log", "table", "text", "lbl_res", "lbl_oa")


def _version():
    import configparser
    cp = configparser.ConfigParser()
    try:
        cp.read(os.path.join(os.path.dirname(os.path.dirname(__file__)), "metadata.txt"), encoding="utf-8")
        return cp.get("general", "version")
    except Exception:
        return "?"


def _ours(obj):
    """Our own boxes (image, area...), never other tabs or the window."""
    return isinstance(obj, QGroupBox) and type(obj).__module__.startswith(__package__)


def _items(tab, prefix=""):
    """(key, widget) for every input widget of the tab, depth first through our own boxes."""
    for name, obj in vars(tab).items():
        if name.startswith("_") or name in SKIP:
            continue
        key = prefix + name
        if isinstance(obj, dict):
            for k, v in obj.items():
                w = v[0] if isinstance(v, tuple) and v else v
                if isinstance(w, QWidget):
                    yield f"{key}.{k}", w
        elif _ours(obj):
            yield from _items(obj, key + ".")
        elif isinstance(obj, QWidget):
            yield key, obj


def _layer_value(lyr):
    return None if lyr is None else {"source": lyr.source(), "name": lyr.name(),
                                     "type": "raster" if isinstance(lyr, QgsRasterLayer) else "vector"}


def state(tab):
    out = {}
    for key, w in _items(tab):
        if isinstance(w, QgsMapLayerComboBox):
            out[key] = {"layer": _layer_value(w.currentLayer())}
        elif isinstance(w, QgsFieldComboBox):
            out[key] = {"field": w.currentField()}
        elif isinstance(w, QgsRasterBandComboBox):
            out[key] = {"band": w.currentBand()}
        elif isinstance(w, QgsFileWidget):
            out[key] = {"path": w.filePath()}
        elif isinstance(w, QgsExtentWidget):
            r = w.outputExtent()
            ok = w.isValid() and not r.isNull() and not r.isEmpty()
            out[key] = {"extent": [r.xMinimum(), r.yMinimum(), r.xMaximum(), r.yMaximum()] if ok else None,
                        "crs": w.outputCrs().toWkt() if ok else None}
        elif isinstance(w, (QCheckBox, QRadioButton)):
            out[key] = {"checked": w.isChecked()}
        elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
            out[key] = {"value": w.value()}
        elif isinstance(w, QComboBox):
            out[key] = {"index": w.currentIndex()}
        elif isinstance(w, QLineEdit):
            out[key] = {"text": w.text()}
        elif isinstance(w, QListWidget):
            out[key] = {"items": [(w.item(i).data(256) or w.item(i).text()) for i in range(w.count())]}
    return out


def save(tab, path):
    data = {"format": FORMAT, "glub_version": _version(), "tab": type(tab).__name__,
            "saved": datetime.datetime.now().isoformat(timespec="seconds"), "widgets": state(tab)}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    return path


def _find_or_add(info):
    if not info:
        return None
    for lyr in QgsProject.instance().mapLayers().values():
        if lyr.source() == info["source"]:
            return lyr
    src = info["source"]
    if not os.path.exists(src.split("|")[0]):
        return None
    lyr = QgsRasterLayer(src, info["name"]) if info.get("type") == "raster" else QgsVectorLayer(src, info["name"], "ogr")
    if not lyr.isValid():
        return None
    QgsProject.instance().addMapLayer(lyr)
    return lyr


def _set(w, v, missing):
    if "layer" in v:
        lyr = _find_or_add(v["layer"])
        if v["layer"] and lyr is None:
            missing.append(v["layer"]["source"])
        w.setLayer(lyr)
    elif "field" in v:
        w.setField(v["field"])
        if v["field"] and w.currentField() != v["field"]:
            missing.append(f"field {v['field']}")
    elif "band" in v:
        w.setBand(int(v["band"]))
        if w.currentBand() != int(v["band"]):
            missing.append(f"band {v['band']}")
    elif "path" in v:
        w.setFilePath(str(v["path"]))
    elif "extent" in v:
        if v["extent"]:
            w.setOutputExtentFromUser(QgsRectangle(*[float(x) for x in v["extent"]]),
                                      QgsCoordinateReferenceSystem.fromWkt(v["crs"]))
        else:
            w.clear()
    elif "checked" in v:
        w.setChecked(bool(v["checked"]))
    elif "value" in v:
        w.setValue(int(v["value"]) if isinstance(w, QSpinBox) else float(v["value"]))
    elif "index" in v:
        if 0 <= int(v["index"]) < w.count():
            w.setCurrentIndex(int(v["index"]))
    elif "text" in v:
        w.setText(str(v["text"]))
    elif "items" in v:
        w.clear()
        for p in v["items"]:
            w.addItem(str(p))


def load(tab, path):
    """Fill the tab from a settings file. Returns the list of things that could not be restored."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("not a GLUB settings file")
    if data.get("tab") != type(tab).__name__:
        raise ValueError(f"these settings belong to another tab ({data.get('tab')})")
    vals = {k: v for k, v in (data.get("widgets") or {}).items() if isinstance(v, dict)}
    widgets = dict(_items(tab))
    missing = []
    # layers first: field and band lists depend on them
    order = sorted(vals, key=lambda k: 0 if "layer" in vals[k] else 2 if ("field" in vals[k] or "band" in vals[k]) else 1)
    for key in order:
        w, v = widgets.get(key), vals[key]
        if w is None or not isinstance(v, dict):
            continue
        try:
            _set(w, v, missing)
        except Exception as e:   # one bad value must not stop the rest
            missing.append(f"{key}: {e}")
    return missing
