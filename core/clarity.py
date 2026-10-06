"""Water clarity of each scene, to choose the dates to map or to composite. GDAL + numpy.

For every reflectance raster (same bands, same CRS) it measures, on two polygons
drawn once:

  deep water (needed)    an area where no bottom is seen. Mean and standard deviation
                         of blue and green, mean red and NIR. A high red or NIR mean
                         means suspended sediment or glint; a high sd means waves,
                         glint residue or patchy turbidity.
  bottom (optional)      one bright bottom type (usually sand) at moderate depth.
                         Bottom contrast = (median R - deep mean) / deep sd, in blue
                         and green; the larger of the two is kept. It is the same
                         quantity as the bottom-signal test of the classification:
                         the higher it is, the deeper the satellite sees the bottom
                         on that day.

Ranking: by bottom contrast when the bottom polygon is given, otherwise by the red
mean of deep water (lower = clearer). Scenes are only flagged, never removed:
contrast below half of the best scene, under half of the bottom polygon valid
(cloud), or a deep-water sd more than twice the median of the scenes.
These are rules of thumb for comparing dates of the same place, not absolute
thresholds of water quality.
"""
import csv
import os

import numpy as np
from osgeo import gdal, osr

from . import blockio
from .composite import scene_date
from .lang import L

gdal.UseExceptions()


def _same_crs(a, b):
    sa, sb = osr.SpatialReference(), osr.SpatialReference()
    sa.ImportFromWkt(a)
    sb.ImportFromWkt(b)
    return bool(sa.IsSame(sb))


def measure(path, idx, deep_wkt, bottom_wkt=None, min_pixels=30):
    """Clarity figures of one raster. idx: {'blue': b, 'green': b, 'red': b, 'nir': b} (nir optional)."""
    grid = blockio.Grid.of(path)
    layers = blockio.layers_of(path, idx, grid, "near")
    out = {"path": path, "name": os.path.basename(path), "date": scene_date(path)}
    d = blockio.sample_polygon(deep_wkt, layers, grid)
    total = len(d["blue"])
    ok = np.isfinite(d["blue"]) & np.isfinite(d["green"])
    out["deep_n"], out["deep_valid"] = int(ok.sum()), (ok.sum() / total if total else 0.0)
    for b in ("blue", "green"):
        v = d[b][ok]
        out[f"deep_{b}"] = float(v.mean()) if v.size else np.nan
        out[f"deep_{b}_sd"] = float(v.std(ddof=1)) if v.size > 1 else np.nan
    for b in ("red", "nir"):
        if b in d:
            v = d[b][ok & np.isfinite(d[b])]
            out[f"deep_{b}"] = float(v.mean()) if v.size else np.nan
        else:
            out[f"deep_{b}"] = np.nan
    out["contrast"] = np.nan
    out["bottom_valid"] = np.nan
    if bottom_wkt:
        s = blockio.sample_polygon(bottom_wkt, {k: layers[k] for k in ("blue", "green")}, grid)
        n = len(s["blue"])
        okb = np.isfinite(s["blue"]) & np.isfinite(s["green"])
        out["bottom_valid"] = okb.sum() / n if n else 0.0
        cs = []
        for b in ("blue", "green"):
            sd = out[f"deep_{b}_sd"]
            if okb.sum() >= min_pixels and np.isfinite(sd) and sd > 0:
                cs.append((float(np.median(s[b][okb])) - out[f"deep_{b}"]) / sd)
        if cs:
            out["contrast"] = max(cs)
    out["usable"] = out["deep_n"] >= min_pixels
    return out


def rank(paths, idx, deep_wkt, bottom_wkt=None, log=print, out_csv=None):
    """Measure and rank the scenes. Returns (rows sorted best first, warnings)."""
    warns = []

    def warn(m):
        warns.append(m)
        log(m, True)

    ref = gdal.Open(paths[0]).GetProjection()
    rows = []
    for p in paths:
        if not _same_crs(gdal.Open(p).GetProjection(), ref):
            warn(L(f"{os.path.basename(p)}: different CRS from the first raster; left out.",
                   f"{os.path.basename(p)}: SRC distinto del primer ráster; se deja fuera."))
            continue
        try:
            r = measure(p, idx, deep_wkt, bottom_wkt)
        except (RuntimeError, ValueError) as e:
            warn(f"{os.path.basename(p)}: {e}")
            continue
        if not r["usable"]:
            warn(L(f"{r['name']}: fewer than 30 valid deep-water pixels (cloud or outside); not ranked.",
                   f"{r['name']}: menos de 30 píxeles válidos de agua profunda (nube o fuera); no se ordena."))
        rows.append(r)
    good = [r for r in rows if r["usable"]]
    if not good:
        raise ValueError(L("No scene has enough valid deep-water pixels.",
                           "Ninguna escena tiene suficientes píxeles válidos de agua profunda."))
    by_contrast = bottom_wkt is not None and any(np.isfinite(r["contrast"]) for r in good)
    if by_contrast:
        good.sort(key=lambda r: -r["contrast"] if np.isfinite(r["contrast"]) else np.inf)
        best = good[0]["contrast"]
    else:
        good.sort(key=lambda r: (r["deep_red"] if np.isfinite(r["deep_red"]) else np.inf))
        best = None
    sds = np.array([np.nanmean([r["deep_blue_sd"], r["deep_green_sd"]]) for r in good])
    med_sd = float(np.nanmedian(sds)) if sds.size else np.nan
    for r, sd in zip(good, sds):
        flags = []
        if by_contrast and np.isfinite(r["contrast"]) and best > 0 and r["contrast"] < 0.5 * best:
            flags.append(L("low bottom contrast", "poco contraste del fondo"))
        if by_contrast and not np.isfinite(r["contrast"]):
            flags.append(L("bottom polygon not usable", "polígono de fondo sin datos"))
        if np.isfinite(r["bottom_valid"]) and r["bottom_valid"] < 0.5:
            flags.append(L("bottom polygon mostly cloud or no data", "polígono de fondo casi todo nube o sin dato"))
        if np.isfinite(med_sd) and med_sd > 0 and sd > 2 * med_sd:
            flags.append(L("noisy deep water (waves, glint or patchy turbidity)",
                           "agua profunda ruidosa (oleaje, brillo o turbidez a manchas)"))
        r["flags"] = flags
    for r in rows:
        r.setdefault("flags", [L("not ranked", "sin ordenar")])
    ordered = good + [r for r in rows if not r["usable"]]
    for i, r in enumerate(ordered, 1):
        r["rank"] = i if r["usable"] else None
    log(L("Ranking by ", "Orden por ") + (L("bottom contrast (higher = the bottom is seen deeper).",
                                            "contraste del fondo (más alto = el fondo se ve más hondo).")
                                          if by_contrast else
                                          L("red reflectance of deep water (lower = less sediment). Give a bottom "
                                            "polygon for a better ranking.",
                                            "reflectancia roja del agua profunda (más baja = menos sedimento). Da "
                                            "un polígono de fondo para un orden mejor.")))
    for r in ordered:
        log(f"{r['rank'] or '-'}. {r['name']} ({r['date'] or '?'}): "
            + (L(f"contrast {r['contrast']:.1f}, ", f"contraste {r['contrast']:.1f}, ")
               if np.isfinite(r["contrast"]) else "")
            + L(f"deep red {r['deep_red']:.4f}, deep sd blue/green {r['deep_blue_sd']:.4f}/{r['deep_green_sd']:.4f}",
                f"rojo profundo {r['deep_red']:.4f}, σ profunda azul/verde {r['deep_blue_sd']:.4f}/{r['deep_green_sd']:.4f}")
            + (" | " + "; ".join(r["flags"]) if r["flags"] else ""), bool(r["flags"]))
    if out_csv:
        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            wr = csv.writer(fh)
            wr.writerow(["rank", "file", "date", "bottom_contrast", "bottom_valid", "deep_valid", "deep_blue",
                         "deep_blue_sd", "deep_green", "deep_green_sd", "deep_red", "deep_nir", "flags"])
            for r in ordered:
                wr.writerow([r["rank"] or "", r["path"], r["date"] or "", _n(r["contrast"], 2),
                             _n(r["bottom_valid"], 3), _n(r["deep_valid"], 3), _n(r["deep_blue"], 5),
                             _n(r["deep_blue_sd"], 5), _n(r["deep_green"], 5), _n(r["deep_green_sd"], 5),
                             _n(r["deep_red"], 5), _n(r["deep_nir"], 5), "; ".join(r["flags"])])
    return ordered, warns


def _n(v, d):
    return "" if v is None or not np.isfinite(v) else f"{v:.{d}f}"
