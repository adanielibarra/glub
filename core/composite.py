"""Median composite of several prepared reflectance rasters, strip by strip. numpy + GDAL.

Every input is resampled (nearest neighbour, so no-data never bleeds) onto the
grid of the first one, through a lazy in-memory VRT. Each output band is the
per-pixel median of the valid values; a second file counts how many scenes were
valid in each pixel. Memory: one strip of rows of every scene at a time.

Apply the sunglint correction to each scene before compositing: glint changes
from one date to the next and a median does not remove it reliably.
"""
import datetime
import os
import re
import warnings

import numpy as np
from osgeo import gdal

from . import blockio
from .lang import L

gdal.UseExceptions()


SEASONS_ES = {"winter": "invierno", "spring": "primavera", "summer": "verano", "autumn": "otoño"}
SEASONS = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
           6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}


_DATE_PATTERNS = (
    re.compile(r"L[CTEO]0[4-9]_L2S[PR]_\d{6}_((?:19|20)\d{2})(\d{2})(\d{2})_"),   # Landsat Collection 2
    re.compile(r"(20\d{2})(\d{2})(\d{2})T\d{6}"),                                   # Sentinel-2
    re.compile(r"(20\d{2})_(\d{2})_(\d{2})"),                                         # ACOLITE
)


def date_in_text(text):
    """Acquisition date in a product name or metadata text (Landsat, Sentinel-2 or ACOLITE naming)."""
    for pat in _DATE_PATTERNS:
        m = pat.search(text or "")
        if m:
            try:
                return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
    return None


def scene_date(path):
    """Acquisition date from the SOURCE metadata or the file name."""
    texts = []
    try:
        texts.append(gdal.Open(path).GetMetadataItem("SOURCE") or "")
    except RuntimeError:
        pass
    texts.append(os.path.basename(path))
    for t in texts:
        d = date_in_text(t)
        if d:
            return d
    return None


def check_dates(paths, max_days=45):
    """Dates of the scenes and warnings when they span too long or several seasons
    (seagrass such as Cymodocea changes over the year; water clarity too).
    Seasons are the northern-hemisphere meteorological ones."""
    dates = [scene_date(p) for p in paths]
    warns = []
    known = sorted(d for d in dates if d)
    if len(known) < len(paths):
        warns.append(L(f"No date found for {len(paths) - len(known)} of {len(paths)} rasters; the date span "
                       "cannot be checked for them.",
                       f"No se encontró la fecha de {len(paths) - len(known)} de {len(paths)} rásteres; para "
                       "ellos no se puede comprobar el intervalo de fechas."))
    if len(known) >= 2:
        span = (known[-1] - known[0]).days
        seasons = sorted({SEASONS[d.month] for d in known})
        years = sorted({d.year for d in known})
        if span > max_days:
            warns.append(L(f"The dates span {span} days ({known[0]} to {known[-1]}). Seagrass (Cymodocea above all) "
                           "and water clarity change over the year; a median over a long span mixes those states.",
                           f"Las fechas abarcan {span} días ({known[0]} a {known[-1]}). Las praderas (sobre todo "
                           "Cymodocea) y la transparencia del agua cambian a lo largo del año; una mediana sobre "
                           "tanto tiempo mezcla esos estados."))
        if len(seasons) > 1:
            warns.append(L("The dates fall in several seasons (" + ", ".join(seasons) + "; northern hemisphere).",
                           "Las fechas caen en varias estaciones (" + ", ".join(SEASONS_ES[x] for x in seasons)
                           + "; hemisferio norte)."))
        if len(years) > 1:
            warns.append(L("The dates come from different years (" + ", ".join(map(str, years)) + "): the meadows "
                           "themselves may have changed.",
                           "Las fechas son de años distintos (" + ", ".join(map(str, years)) + "): las propias "
                           "praderas pueden haber cambiado."))
    return dates, warns


def median(paths, out_path, out_count=None, min_scenes=1, log=print, max_days=45):
    if len(paths) < 2:
        raise ValueError(L("A composite needs at least two rasters.", "Un compuesto necesita al menos dos rásteres."))
    ref = gdal.Open(paths[0])
    nb = ref.RasterCount
    for p in paths[1:]:
        n = gdal.Open(p).RasterCount
        if n != nb:
            raise ValueError(L(f"{p} has {n} bands; the first raster has {nb}.",
                               f"{p} tiene {n} bandas; el primer ráster tiene {nb}."))
    dates, dwarns = check_dates(paths, max_days)
    log(L("Dates: ", "Fechas: ") + ", ".join(str(d) if d else L("unknown", "desconocida") for d in dates))
    for w_ in dwarns:
        try:
            log(w_, True)
        except TypeError:  # a plain print-like logger
            log("WARNING: " + w_)
    grid = blockio.Grid.of(paths[0])
    names = [ref.GetRasterBand(b).GetDescription() or f"band_{b}" for b in range(1, nb + 1)]
    layers = [[blockio.Layer(p, b, grid, "near") for b in range(1, nb + 1)] for p in paths]
    out = blockio.Writer(out_path, grid, names, metadata={
        "GLUB_COMPOSITE": f"median of {len(paths)} rasters",
        "GLUB_DATES": ",".join(str(d) if d else "unknown" for d in dates)})
    cw = blockio.Writer(out_count, grid, ["valid scenes"], gdal.GDT_Int16, -1) if out_count else None
    # a strip holds n_scenes x bands layers at once: shrink it accordingly
    strip_px = max(blockio.STRIP_PIXELS // max(len(paths), 1), grid.w)
    hist = np.zeros(len(paths) + 1, dtype=np.int64)
    n_ok = 0
    for r0, nr in grid.strips(strip_px):
        arrays, cnt0 = [], None
        for b in range(nb):
            stack = np.stack([layers[s][b].read(r0, nr) for s in range(len(paths))])
            cnt = np.isfinite(stack).sum(0)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN pixels
                med = np.nanmedian(stack, axis=0)
            med[cnt < min_scenes] = np.nan
            if b == 0:
                cnt0 = cnt
            arrays.append(np.where(np.isfinite(med), med, blockio.NODATA).astype(np.float32))
        out.write(r0, arrays)
        if cw:
            cw.write(r0, [cnt0.astype(np.int16)])
        hist += np.bincount(cnt0.ravel(), minlength=len(paths) + 1)
        n_ok += int((cnt0 >= min_scenes).sum())
    out.close()
    if cw:
        cw.close()
    valid = hist[1:]
    if valid.sum():
        cum = np.cumsum(valid)
        med_n = int(np.searchsorted(cum, cum[-1] / 2) + 1)
        min_n = int(np.flatnonzero(valid)[0] + 1)
    else:
        med_n = min_n = 0
    log(L(f"Composite of {len(paths)} rasters: valid scenes per pixel, median {med_n}, min {min_n}.",
          f"Compuesto de {len(paths)} rásteres: fechas válidas por píxel, mediana {med_n}, mínimo {min_n}."))
    return {"n": len(paths), "pixels": n_ok, "dates": dates, "warnings": dwarns}
