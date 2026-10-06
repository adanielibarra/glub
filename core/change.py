"""Change between two class maps of the same place (date 1 -> date 2). GDAL + numpy.

  comparison     only where the bottom is classified on both dates. A pixel that is
                 'bottom not visible', 'too deep' or 'low confidence' on either date
                 is 'not comparable' (code 250): an apparent loss there may only be
                 turbid water on one of the days.
  classes        matched by name (case and spaces ignored), so the two maps need the
                 same class names, not the same codes. The second map is put on the
                 grid of the first (nearest neighbour).
  output         change.tif: one code per transition, (i - 1) * k + j for class i on
                 date 1 and class j on date 2 (so 'no change' codes are on the
                 diagonal), 250 not comparable, 255 no data. The names go in the
                 metadata, so the validation tab can draw stratified points on the
                 change map and estimate change areas with their intervals.
  minimum unit   optional: change patches smaller than N pixels are merged into the
                 neighbouring patch (GDAL sieve, comparable pixels only), written to
                 change_filtered.tif.

Mapped change is indicative. Subtracting two maps adds up the errors of both:
if each map is right in a share OA of the pixels and the errors are independent,
about 1 - OA1 * OA2 of the pixels can disagree by error alone, which can be as
large as the real change. The report says so, with the validation accuracies of
the two maps when they are stored in them.
"""
import csv
import os

import numpy as np
from osgeo import gdal

from . import blockio, depthmask, sampling
from .composite import date_in_text
from .lang import L
from .pipeline import KEYWORDS, class_color, pixel_area_ha, write_qml

gdal.UseExceptions()
NOT_COMPARABLE, NODATA = 250, 255
SEAGRASS_WORDS = KEYWORDS[0][0] + KEYWORDS[1][0] + KEYWORDS[2][0] + KEYWORDS[3][0]


def _norm(s):
    return " ".join(str(s).strip().lower().split())


def _date_of(ds):
    d = date_in_text(ds.GetMetadataItem("GLUB_SOURCE") or "")
    return d.isoformat() if d else None


def _oa_of(ds):
    try:
        return float(ds.GetMetadataItem("GLUB_VALIDATION_OA"))
    except (TypeError, ValueError):
        return None


def _is_seagrass(name):
    n = _norm(name)
    return any(w in n for w in SEAGRASS_WORDS)


def _lighten(col, f=0.6):
    r, g, b = (int(col[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(c + (255 - c) * f) for c in (r, g, b))


def compare(path1, path2, out_dir, mmu=0, log=print):
    """Write change.tif (+ .qml, change_matrix.csv, optional change_filtered.tif).
    Returns (summary, warnings)."""
    warns = []

    def warn(m):
        warns.append(m)
        log(m, True)

    grid, _c1, names1 = sampling.read_strata(path1)
    _g2, _c2, names2 = sampling.read_strata(path2)
    cls1 = {c: n for c, n in names1.items() if c <= sampling.MAX_CLASS}
    cls2 = {c: n for c, n in names2.items() if c <= sampling.MAX_CLASS}
    # one list of class names: map 1 order, then names only in map 2
    classes, index = [], {}
    for c in sorted(cls1):
        if _norm(cls1[c]) not in index:
            index[_norm(cls1[c])] = len(classes)
            classes.append(cls1[c])
    only2 = []
    for c in sorted(cls2):
        if _norm(cls2[c]) not in index:
            index[_norm(cls2[c])] = len(classes)
            classes.append(cls2[c])
            only2.append(cls2[c])
    only1 = [cls1[c] for c in sorted(cls1) if _norm(cls1[c]) not in {_norm(v) for v in cls2.values()}]
    if only1 or only2:
        warn(L("The two maps do not have the same classes (", "Los dos mapas no tienen las mismas clases (")
             + L("only in date 1: ", "solo en la fecha 1: ") + (", ".join(only1) or "-") + "; "
             + L("only in date 2: ", "solo en la fecha 2: ") + (", ".join(only2) or "-")
             + L("). A class missing on one date shows up as change; check the class names.",
                 "). Una clase que falta en una fecha aparece como cambio; revisa los nombres de clase."))
    k = len(classes)
    if k * k > sampling.MAX_CLASS:
        raise ValueError(L(f"Too many classes for a change map ({k}; at most 15).",
                           f"Demasiadas clases para un mapa de cambios ({k}; como mucho 15)."))
    # code -> class index (0..k-1) for each map; -1 = not comparable, -2 = no data
    lut1 = np.full(256, -2, np.int64)
    lut2 = np.full(256, -2, np.int64)
    for c, n in cls1.items():
        lut1[c] = index[_norm(n)]
    for c, n in cls2.items():
        lut2[c] = index[_norm(n)]
    for lut in (lut1, lut2):
        lut[[depthmask.CODE_HIDDEN, depthmask.CODE_TOO_DEEP, depthmask.CODE_UNSURE]] = -1
    ds1, ds2 = gdal.Open(path1), gdal.Open(path2)
    l1 = blockio.Layer(path1, 1, grid, "near")
    l2 = blockio.Layer(path2, 1, grid, "near")

    trans = np.zeros((k, k), dtype=np.int64)
    n_nc = n_nd = 0
    legend = []
    for i in range(k):
        for j in range(k):
            code = i * k + j + 1
            if i == j:
                nm = classes[i] + L(" (no change)", " (sin cambio)")
                col = _lighten(class_color(classes[i], i))
            else:
                nm = f"{classes[i]} → {classes[j]}"
                if _is_seagrass(classes[i]) and not _is_seagrass(classes[j]):
                    col = "#d7301f"      # seagrass lost
                elif _is_seagrass(classes[j]) and not _is_seagrass(classes[i]):
                    col = "#1a9850"      # seagrass gained
                else:
                    col = "#fdae61"
            legend.append((code, nm, col))
    legend.append((NOT_COMPARABLE, L("not comparable", "no comparable"), "#c9d3dd"))
    os.makedirs(out_dir, exist_ok=True)
    meta = {"GLUB_MAP_TYPE": "change", "GLUB_DATE1_MAP": os.path.basename(path1),
            "GLUB_DATE2_MAP": os.path.basename(path2),
            "GLUB_CLASSES": "; ".join(f"{c}={n}" for c, n, _ in legend)}
    out = os.path.join(out_dir, "change.tif")
    w = blockio.Writer(out, grid, ["change"], gdal.GDT_Byte, NODATA, meta)
    ct = gdal.ColorTable()
    for code, _n, col in legend:
        ct.SetColorEntry(code, tuple(int(col[i:i + 2], 16) for i in (1, 3, 5)) + (255,))
    w.ds.GetRasterBand(1).SetRasterColorTable(ct)
    for r0, nr in grid.strips():
        a1 = l1.read(r0, nr)
        a2 = l2.read(r0, nr)
        c1 = np.where(np.isfinite(a1), a1, 255).astype(np.int64)
        c2 = np.where(np.isfinite(a2), a2, 255).astype(np.int64)
        i1, i2 = lut1[c1], lut2[c2]
        res = np.full(c1.shape, NODATA, np.uint8)
        both = (i1 >= 0) & (i2 >= 0)
        nc = ((i1 == -1) | (i2 == -1)) & (i1 != -2) & (i2 != -2)
        res[both] = (i1[both] * k + i2[both] + 1).astype(np.uint8)
        res[nc] = NOT_COMPARABLE
        np.add.at(trans, (i1[both], i2[both]), 1)
        n_nc += int(nc.sum())
        n_nd += int((~both & ~nc).sum())
        w.write(r0, [res])
    w.close()
    write_qml(os.path.join(out_dir, "change.qml"), legend)
    filt = None
    if mmu and mmu > 1:
        fpath = os.path.join(out_dir, "change_filtered.tif")
        src = gdal.Open(out)
        drv = gdal.GetDriverByName("GTiff")
        dst = drv.CreateCopy(fpath, src, options=["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"])
        mds = drv.Create(fpath + ".mask.tif", grid.w, grid.h, 1, gdal.GDT_Byte, options=["COMPRESS=DEFLATE"])
        sb = src.GetRasterBand(1)
        for r0, nr in grid.strips():
            a = sb.ReadAsArray(0, r0, grid.w, nr)
            mds.GetRasterBand(1).WriteArray(((a >= 1) & (a <= k * k)).astype(np.uint8), 0, r0)
        mds.FlushCache()
        gdal.SieveFilter(dst.GetRasterBand(1), mds.GetRasterBand(1), dst.GetRasterBand(1), int(mmu), 4)
        dst.FlushCache()
        ft = np.zeros((k, k), dtype=np.int64)
        db = dst.GetRasterBand(1)
        for r0, nr in grid.strips():
            a = db.ReadAsArray(0, r0, grid.w, nr).astype(np.int64)
            a = a[(a >= 1) & (a <= k * k)] - 1
            ft += np.bincount(a, minlength=k * k).reshape(k, k)
        dst = mds = None
        drv.Delete(fpath + ".mask.tif")
        write_qml(os.path.join(out_dir, "change_filtered.qml"), legend)
        filt = {"path": fpath, "mmu": int(mmu), "trans": ft}
        log(L(f"Minimum change unit {mmu} pixels: change_filtered.tif written.",
              f"Unidad mínima de cambio {mmu} píxeles: escrito change_filtered.tif."))
    ha = pixel_area_ha(grid.gt, grid.proj)
    unit = ha or 1.0
    with open(os.path.join(out_dir, "change_matrix.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow([L("date 1 \\ date 2", "fecha 1 \\ fecha 2")] + classes)
        for i in range(k):
            wr.writerow([classes[i]] + [f"{trans[i, j] * unit:.2f}" for j in range(k)])
    t1, t2 = trans.sum(1) * unit, trans.sum(0) * unit
    stay = np.diag(trans) * unit
    per_class = [{"class": classes[i], "date1": t1[i], "date2": t2[i], "loss": t1[i] - stay[i],
                  "gain": t2[i] - stay[i], "net": t2[i] - t1[i]} for i in range(k)]
    comparable = int(trans.sum())
    changed = comparable - int(np.trace(trans))
    oa1, oa2 = _oa_of(ds1), _oa_of(ds2)
    noise = 1 - oa1 * oa2 if (oa1 is not None and oa2 is not None) else None
    log(L(f"Comparable pixels: {comparable}; changed: {changed} ({100 * changed / max(comparable, 1):.1f} %). "
          f"Not comparable: {n_nc}.",
          f"Píxeles comparables: {comparable}; con cambio: {changed} ({100 * changed / max(comparable, 1):.1f} %). "
          f"No comparables: {n_nc}."))
    if noise is not None:
        msg = L(f"With validation accuracies of {100 * oa1:.0f} % and {100 * oa2:.0f} %, about {100 * noise:.0f} % of "
                "the pixels could disagree by error alone (if the errors are independent).",
                f"Con exactitudes de validación del {100 * oa1:.0f} % y del {100 * oa2:.0f} %, cerca del "
                f"{100 * noise:.0f} % de los píxeles podrían no coincidir solo por error (si los errores son "
                "independientes).")
        if changed / max(comparable, 1) < noise:
            warn(msg + L(" The mapped change is smaller than that: it cannot be told apart from map error without "
                         "validating the change map.",
                         " El cambio cartografiado es menor que eso: no se distingue del error de los mapas sin "
                         "validar el mapa de cambios."))
        else:
            log(msg)
    summary = {"classes": classes, "trans": trans, "ha": ha, "per_class": per_class, "comparable": comparable,
               "changed": changed, "not_comparable": n_nc, "nodata": n_nd, "oa1": oa1, "oa2": oa2, "noise": noise,
               "date1": _date_of(ds1), "date2": _date_of(ds2), "map1": path1, "map2": path2, "filtered": filt,
               "path": out, "legend": legend}
    return summary, warns
