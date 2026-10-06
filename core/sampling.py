"""Validation points for a class map and the assessment of the map with them. GDAL + numpy.

Design (Olofsson et al., 2014): stratified random sampling, the strata being the
map classes. Every pixel of a stratum has the same chance of being drawn, so the
reference labels collected at the points give unbiased estimates of accuracy and
of the area of each class, with confidence intervals.

  sample size   n = (sum_i W_i S_i / S(OA))^2, with W_i the area share of map
                class i, S_i = sqrt(U_i (1 - U_i)) for an expected user's accuracy
                U_i and S(OA) the target standard error of overall accuracy
                (Olofsson et al., 2014, eq. 13). Or a total chosen by hand.
  allocation    proportional to area, but at least a minimum per class (rare
                classes need enough points for their user's accuracy), or equal.
  strata        the map classes and, if the map has it, the low-confidence zone
                (code 252), which is one more stratum of the estimate. Optionally,
                points in the 'bottom not visible' and 'too deep' zones to check
                the mask; they do not enter the area estimate.
  spacing       points of the same stratum are kept at least a minimum distance
                apart, drawn in random order. Points of different strata are not
                kept apart: map errors gather at class boundaries, and pushing
                points away from them would under-sample the errors (it biased the
                corrected areas in tests).

The points must be labelled in the field (or on better imagery) without looking
at the map: the reference label is what is really there.
"""
import csv
import math
import os

import numpy as np
from osgeo import gdal, ogr, osr

from . import accuracy, blockio, depthmask
from .lang import L

gdal.UseExceptions()
MAX_CLASS = 249
EXTRA_STRATA = (depthmask.CODE_UNSURE, depthmask.CODE_HIDDEN, depthmask.CODE_TOO_DEEP)
EXTRA_NAMES = {depthmask.CODE_UNSURE: ("low confidence", "baja confianza"),
               depthmask.CODE_HIDDEN: ("bottom not visible", "fondo no visible"),
               depthmask.CODE_TOO_DEEP: ("too deep", "demasiado hondo")}


def stratum_name(code, names):
    if code > MAX_CLASS and code in names:   # e.g. 'not comparable' in a change map
        return names[code]
    if code in EXTRA_NAMES:
        return L(*EXTRA_NAMES[code])
    return names.get(code, str(code))


def read_strata(path):
    """Pixel count of every code and the class names stored in the raster (category names).
    Returns (grid, counts[256], names {code: name} for class codes 1..249)."""
    grid = blockio.Grid.of(path)
    ds = gdal.Open(path)
    b = ds.GetRasterBand(1)
    if b.DataType != gdal.GDT_Byte:
        raise ValueError(L("The class map must be a byte raster (like classes.tif).",
                           "El mapa de clases debe ser un ráster de tipo byte (como classes.tif)."))
    counts = np.zeros(256, dtype=np.int64)
    for r0, nr in grid.strips():
        counts += np.bincount(b.ReadAsArray(0, r0, grid.w, nr).ravel(), minlength=256)
    # class names: from the GLUB_CLASSES metadata of classes.tif, else the category names
    meta = {}
    for part in (ds.GetMetadataItem("GLUB_CLASSES") or "").split("; "):
        code, sep, nm = part.partition("=")
        if sep and code.strip().isdigit():
            meta[int(code)] = nm.strip()
    cats = b.GetRasterCategoryNames() or []
    names = {}
    for code in range(1, MAX_CLASS + 1):
        nm = meta.get(code) or (cats[code].strip() if code < len(cats) and cats[code] else "")
        if nm or counts[code]:
            names[code] = nm or str(code)
    if (ds.GetMetadataItem("GLUB_MAP_TYPE") or "") == "change":
        for code in range(MAX_CLASS + 1, 255):
            if code in meta:
                names[code] = meta[code]
    return grid, counts, names


def sample_size(W, U, target_se):
    """Olofsson et al. (2014), eq. 13. W: area shares, U: expected user's accuracies."""
    W, U = np.asarray(W, float), np.asarray(U, float)
    S = np.sqrt(U * (1 - U))
    return int(math.ceil((np.sum(W * S) / target_se) ** 2))


def allocate(pixels, n_total, min_per=50, mode="proportional"):
    """Points per stratum. pixels: array of stratum sizes. Never more points than pixels."""
    N = np.asarray(pixels, dtype=np.float64)
    m = len(N)
    if m == 0:
        return np.zeros(0, dtype=np.int64)
    # share n_total out; a stratum that hits its minimum or its size (no more points than pixels) is
    # fixed there and the rest is shared again among the others, so small strata do not lose points
    total = max(float(n_total), 0.0)
    W = N / N.sum() if N.sum() > 0 else np.full(m, 1.0 / m)
    floor_ = np.minimum(min_per, N) if mode != "equal" else np.zeros(m)
    n = np.zeros(m)
    fixed = np.zeros(m, bool)
    for _ in range(2 * m + 2):
        free = ~fixed
        if not free.any():
            break
        rest = max(total - n[fixed].sum(), 0.0)
        share = np.full(free.sum(), 1.0 / free.sum()) if mode == "equal" or W[free].sum() == 0 \
            else W[free] / W[free].sum()
        n[free] = rest * share
        over = free & (n > N)
        if over.any():
            n[over] = N[over]
            fixed |= over
            continue
        low = free & (n < floor_)
        if low.any():
            n[low] = floor_[low]
            fixed |= low
            continue
        break
    n = np.minimum(n, N)
    base = np.floor(n + 1e-9).astype(np.int64)
    short = int(round(total - base.sum()))
    if short > 0:
        room = base < N.astype(np.int64)
        order = [i for i in np.argsort(-(n - base)) if room[i]]
        for i in order[:short]:
            base[i] += 1
    return np.minimum(base, N.astype(np.int64))


def draw(path, alloc, min_dist_px=3.0, seed=42, counts=None):
    """Random pixels of each stratum. alloc: {code: n}. Returns (rows, cols, codes, warnings).
    The class raster is read once into memory (one byte per pixel)."""
    rng = np.random.default_rng(seed)
    grid = blockio.Grid.of(path)
    ds = gdal.Open(path)
    arr = np.empty((grid.h, grid.w), dtype=np.uint8)
    b = ds.GetRasterBand(1)
    for r0, nr in grid.strips():
        arr[r0:r0 + nr] = b.ReadAsArray(0, r0, grid.w, nr)
    flat = arr.ravel()
    if counts is None:
        counts = np.bincount(flat, minlength=256)
    d = float(min_dist_px or 0)
    cell = max(d, 1.0)
    out_r, out_c, out_code, warns = [], [], [], []
    taken = {}

    def free(r, c):
        if d <= 0:
            return (r, c) not in taken
        gr, gc = int(r // cell), int(c // cell)
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for (rr, cc) in taken.get((gr + i, gc + j), ()):
                    if (rr - r) ** 2 + (cc - c) ** 2 < d * d:
                        return False
        return True

    def take(r, c, code):
        key = (int(r // cell), int(c // cell)) if d > 0 else (r, c)
        taken.setdefault(key, []).append((r, c))
        out_r.append(r)
        out_c.append(c)
        out_code.append(code)

    for code in sorted(alloc, key=lambda c_: counts[c_]):
        want = int(alloc[code])
        if want <= 0:
            continue
        taken = {}   # spacing within the stratum only
        got = 0
        if counts[code] <= 2_000_000:
            cand = np.flatnonzero(flat == code)
            rng.shuffle(cand)
            for idx in cand:
                r, c = divmod(int(idx), grid.w)
                if free(r, c):
                    take(r, c, code)
                    got += 1
                    if got == want:
                        break
        else:  # large stratum: uniform positions over the raster, kept if they fall in the stratum
            tries = 0
            while got < want and tries < 200:
                tries += 1
                idx = rng.integers(0, flat.size, size=max(20 * want, 20000))
                idx = idx[flat[idx] == code]
                for i in idx:
                    r, c = divmod(int(i), grid.w)
                    if free(r, c):
                        take(r, c, code)
                        got += 1
                        if got == want:
                            break
        if got < want:
            warns.append((code, want, got))
    return np.array(out_r, np.int64), np.array(out_c, np.int64), np.array(out_code, np.int64), warns


def generate(class_path, out_path, n_total=0, target_se=0.02, expected_ua=0.8, min_per=50,
             mode="proportional", n_hidden=0, n_deep=0, min_dist_m=30.0, seed=42, log=print):
    """Write a GeoPackage of stratified random validation points (and a CSV of the strata).
    n_total = 0: computed from target_se and expected_ua (Olofsson et al., 2014).
    Returns a dict with the strata table and the paths."""
    grid, counts, names = read_strata(class_path)
    class_codes = [c for c in sorted(names) if c <= MAX_CLASS and counts[c] > 0]
    if not class_codes:
        raise ValueError(L("The map has no class pixels.", "El mapa no tiene píxeles de clase."))
    strata = class_codes + ([depthmask.CODE_UNSURE] if counts[depthmask.CODE_UNSURE] > 0 else [])
    N = counts[strata].astype(np.float64)
    W = N / N.sum()
    if not n_total:
        n_total = sample_size(W, np.full(len(strata), expected_ua), target_se)
        log(L(f"Sample size from a target standard error of overall accuracy of {target_se:g} and an expected "
              f"user's accuracy of {expected_ua:g}: {n_total} points (Olofsson et al., 2014).",
              f"Tamaño de muestra para un error típico objetivo de la exactitud global de {target_se:g} y una "
              f"exactitud de usuario esperada de {expected_ua:g}: {n_total} puntos (Olofsson et al., 2014)."))
    n = allocate(N, n_total, min_per, mode)
    if n.sum() > n_total:
        log(L(f"The minimum of {min_per} per stratum raises the total to {int(n.sum())} points.",
              f"El mínimo de {min_per} por estrato sube el total a {int(n.sum())} puntos."), True)
    alloc = dict(zip(strata, n.tolist()))
    for code, extra in ((depthmask.CODE_HIDDEN, n_hidden), (depthmask.CODE_TOO_DEEP, n_deep)):
        if extra and counts[code] > 0:
            alloc[code] = int(min(extra, counts[code]))
    srs = osr.SpatialReference()
    srs.ImportFromWkt(grid.proj)
    unit = srs.GetLinearUnits() if srs.IsProjected() else None
    px_size = abs(grid.gt[1]) * (unit or 1.0)
    min_dist_px = (min_dist_m / px_size) if (unit and min_dist_m) else 0.0
    if min_dist_m and not unit:
        log(L("The raster CRS is not projected: the minimum distance between points is not applied.",
              "El SRC del ráster no es proyectado: no se aplica la distancia mínima entre puntos."), True)
    rows, cols, codes, short = draw(class_path, alloc, min_dist_px, seed, counts)
    for code, want, got in short:
        log(L(f"Stratum {stratum_name(code, names)}: only {got} of {want} points fit (small stratum or minimum "
              "distance too large).",
              f"Estrato {stratum_name(code, names)}: solo caben {got} de {want} puntos (estrato pequeño o "
              "distancia mínima demasiado grande)."), True)
    order = rng_order(len(rows), seed)
    rows, cols, codes = rows[order], cols[order], codes[order]
    gt = grid.gt
    xs = gt[0] + (cols + 0.5) * gt[1]
    ys = gt[3] + (rows + 0.5) * gt[5]
    _write_points(out_path, grid.proj, xs, ys, codes, names)
    ha = abs(gt[1] * gt[5]) * (unit or 1) ** 2 / 1e4 if unit else None
    table = []
    for code in list(alloc):
        got = int((codes == code).sum())
        table.append({"code": code, "name": stratum_name(code, names), "pixels": int(counts[code]),
                      "area": counts[code] * (ha or 1.0), "share": (counts[code] / N.sum()) if code in strata else None,
                      "planned": int(alloc[code]), "points": got,
                      "in_estimate": code in strata})
    csv_path = os.path.splitext(out_path)[0] + "_strata.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["code", "stratum", "pixels", "hectares" if ha else "pixels_area", "area_share", "points",
                     "in_area_estimate"])
        for t in table:
            wr.writerow([t["code"], t["name"], t["pixels"], f"{t['area']:.2f}",
                         "" if t["share"] is None else f"{t['share']:.6f}", t["points"],
                         "yes" if t["in_estimate"] else "no (mask check)"])
    log(L(f"{len(rows)} points written: ", f"{len(rows)} puntos escritos: ")
        + ", ".join(f"{t['name']} {t['points']}" for t in table) + ".")
    return {"table": table, "points": out_path, "strata_csv": csv_path, "n": int(len(rows)), "ha": ha}


def rng_order(n, seed):
    """A random order for the output rows, so the file does not list the strata in blocks."""
    return np.random.default_rng(seed + 1).permutation(n)


def _write_points(path, proj, xs, ys, codes, names):
    drv = ogr.GetDriverByName("GPKG")
    if os.path.exists(path):
        drv.DeleteDataSource(path)
    ds = drv.CreateDataSource(path)
    srs = osr.SpatialReference()
    srs.ImportFromWkt(proj)
    lyr = ds.CreateLayer("validation_points", srs, ogr.wkbPoint)
    for name, typ in (("point_id", ogr.OFTInteger), ("stratum", ogr.OFTInteger), ("map_class", ogr.OFTString),
                      ("x", ogr.OFTReal), ("y", ogr.OFTReal), ("lon", ogr.OFTReal), ("lat", ogr.OFTReal),
                      ("ref_class", ogr.OFTString), ("notes", ogr.OFTString)):
        lyr.CreateField(ogr.FieldDefn(name, typ))
    wgs = osr.SpatialReference()
    wgs.ImportFromEPSG(4326)
    wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    try:
        tr = osr.CoordinateTransformation(srs, wgs)
    except Exception:
        tr = None
    defn = lyr.GetLayerDefn()
    ds.StartTransaction()
    for i, (x, y, code) in enumerate(zip(xs, ys, codes), start=1):
        f = ogr.Feature(defn)
        f.SetField("point_id", i)
        f.SetField("stratum", int(code))
        f.SetField("map_class", stratum_name(int(code), names))
        f.SetField("x", float(x))
        f.SetField("y", float(y))
        if tr is not None:
            lon, lat, _ = tr.TransformPoint(float(x), float(y))
            f.SetField("lon", round(lon, 7))
            f.SetField("lat", round(lat, 7))
        g = ogr.Geometry(ogr.wkbPoint)
        g.AddPoint_2D(float(x), float(y))
        f.SetGeometry(g)
        lyr.CreateFeature(f)
    ds.CommitTransaction()
    ds = None


# ---------------------------------------------------------------- assessment
def _norm(s):
    """Case and spaces ignored; '->' counts as the arrow of change classes ('seagrass -> sand')."""
    s = str(s).replace("->", "→").replace("→", " → ")
    return " ".join(s.strip().lower().split())


def assess(class_path, xs, ys, refs, out_dir=None, log=print):
    """Accuracy and error-corrected areas of a class map from labelled validation points.

    xs, ys: point coordinates in the raster CRS. refs: reference class of each point
    (text; empty = not visited, left out). The stratum of each point is read from the map.
    Reference labels are matched to the map class names (case and spaces ignored);
    labels the map does not have become extra reference classes.
    Returns (summary, warnings)."""
    warns = []

    def warn(m):
        warns.append(m)
        log(m, True)

    grid, counts, names = read_strata(class_path)
    class_codes = [c for c in sorted(names) if c <= MAX_CLASS]
    k = len(class_codes)
    strata = [c for c in class_codes] + ([depthmask.CODE_UNSURE] if counts[depthmask.CODE_UNSURE] > 0 else [])
    gt = grid.gt
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    cols = np.floor((xs - gt[0]) / gt[1]).astype(np.int64)
    rows = np.floor((ys - gt[3]) / gt[5]).astype(np.int64)
    inside = (rows >= 0) & (rows < grid.h) & (cols >= 0) & (cols < grid.w)
    if (~inside).any():
        warn(L(f"{int((~inside).sum())} points fall outside the map and are left out.",
               f"{int((~inside).sum())} puntos caen fuera del mapa y se dejan fuera."))
    refs = np.array(["" if r is None else str(r).strip() for r in refs], dtype=object)
    blank = np.array([r in ("", "NULL") for r in refs])
    if blank.any():
        warn(L(f"{int(blank.sum())} points have no reference class (not visited?) and are left out. If the ones "
               "left out are not a random subset (e.g. the deep or far ones), the estimates are biased.",
               f"{int(blank.sum())} puntos no tienen clase de referencia (¿sin visitar?) y se dejan fuera. Si los "
               "que faltan no son un subconjunto al azar (por ejemplo los hondos o los lejanos), las estimaciones "
               "quedan sesgadas."))
    use = inside & ~blank
    from . import postproc
    codes = np.full(len(xs), -1, dtype=np.int64)
    if use.any():
        codes[use] = postproc.values_at(class_path, rows[use], cols[use])
    # reference classes: the map classes first (same order), then labels the map does not have
    by_name = {_norm(names[c]): i for i, c in enumerate(class_codes)}
    ref_names = [names[c] for c in class_codes]
    extra = sorted({r for r in refs[use] if _norm(r) not in by_name}, key=_norm)
    if extra:
        warn(L("Reference classes not in the map (kept as extra columns; all of their area comes from map "
               "errors): ", "Clases de referencia que el mapa no tiene (columnas aparte; toda su superficie sale "
               "de errores del mapa): ") + ", ".join(extra)
             + L(". If they are spelling variants of a map class, fix the labels.",
                 ". Si son variantes de nombre de una clase del mapa, corrige las etiquetas."))
        for e in extra:
            by_name[_norm(e)] = len(ref_names)
            ref_names.append(e)
    kc = len(ref_names)
    ref_idx = np.array([by_name.get(_norm(r), -1) for r in refs])
    m = np.zeros((len(strata), kc), dtype=np.int64)
    mask_check = {}
    nodata_pts = 0
    for i in np.flatnonzero(use):
        code = int(codes[i])
        if code in strata:
            m[strata.index(code), ref_idx[i]] += 1
        elif code in (depthmask.CODE_HIDDEN, depthmask.CODE_TOO_DEEP):
            mask_check.setdefault(code, np.zeros(kc, np.int64))
            mask_check[code][ref_idx[i]] += 1
        else:
            nodata_pts += 1
    if nodata_pts:
        warn(L(f"{nodata_pts} points fall on map pixels without data (land, cloud, edge) and are left out.",
               f"{nodata_pts} puntos caen en píxeles sin dato del mapa (tierra, nube, borde) y se dejan fuera."))
    srs = osr.SpatialReference()
    srs.ImportFromWkt(grid.proj)
    ha = abs(gt[1] * gt[5]) * srs.GetLinearUnits() ** 2 / 1e4 if srs.IsProjected() else None
    npx = counts[strata].astype(np.int64)
    n_st = m.sum(1)
    for s_i, code in enumerate(strata):
        if npx[s_i] > 0 and n_st[s_i] < 2:
            warn(L(f"Stratum {stratum_name(code, names)} has {n_st[s_i]} labelled points: its area cannot be "
                   "corrected and its accuracy is unknown.",
                   f"El estrato {stratum_name(code, names)} tiene {n_st[s_i]} puntos etiquetados: su superficie no "
                   "se puede corregir y su exactitud es desconocida."))
        elif npx[s_i] > 0 and n_st[s_i] < 20:
            warn(L(f"Stratum {stratum_name(code, names)} has only {n_st[s_i]} labelled points: its user's accuracy "
                   "is very uncertain.",
                   f"El estrato {stratum_name(code, names)} solo tiene {n_st[s_i]} puntos etiquetados: su exactitud "
                   "de usuario es muy incierta."))
    adj = accuracy.area_adjusted(m, npx, ha or 1.0, k=k) if m.sum() else None
    # 95 % intervals of the stratified estimators of OA and UA (Olofsson et al., 2014, eqs. 5 and 6)
    ci_oa, ci_ua = None, np.full(k, np.nan)
    if adj is not None:
        W = npx / npx.sum()
        var = 0.0
        for s_i in range(len(strata)):
            if n_st[s_i] > 1:
                u = m[s_i, s_i] / n_st[s_i] if s_i < k else 0.0
                var += W[s_i] ** 2 * u * (1 - u) / (n_st[s_i] - 1)
                if s_i < k:
                    ci_ua[s_i] = 1.96 * math.sqrt(u * (1 - u) / (n_st[s_i] - 1))
        ci_oa = 1.96 * math.sqrt(var)
    summary = {"strata": [stratum_name(c, names) for c in strata], "codes": strata, "classes": ref_names, "k": k,
               "cm": m, "pixels": npx, "n_strata": n_st, "adj": adj, "ci_oa": ci_oa, "ci_ua": ci_ua, "ha": ha,
               "mask_check": {stratum_name(c, names): v for c, v in mask_check.items()},
               "n_used": int(m.sum()), "n_points": int(len(xs))}
    if adj is not None:
        log(L(f"Overall accuracy (area-weighted): {100 * adj['oa']:.1f} % ± {100 * ci_oa:.1f} (95 %), "
              f"{int(m.sum())} points.",
              f"Exactitud global (ponderada por superficie): {100 * adj['oa']:.1f} % ± {100 * ci_oa:.1f} (95 %), "
              f"{int(m.sum())} puntos."))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "assessment_points.csv"), "w", newline="", encoding="utf-8") as fh:
            wr = csv.writer(fh)
            wr.writerow(["x", "y", "map_code", "map_stratum", "reference", "used"])
            for i in range(len(xs)):
                c = int(codes[i])
                wr.writerow([f"{xs[i]:.2f}", f"{ys[i]:.2f}", c if c >= 0 else "",
                             stratum_name(c, names) if c >= 0 else "", refs[i],
                             "yes" if (use[i] and c in strata) else "no"])
    return summary, warns
