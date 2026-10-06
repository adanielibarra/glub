"""File-level workflows shared by the GLUB window and the Processing tools.

No QGIS imports: points arrive as coordinates already in the raster CRS and
polygons as WKT in the raster CRS. log(msg, warn=False) reports progress.
"""
import csv
import os

import numpy as np
from osgeo import gdal, osr

from .lang import L
from . import accuracy, blockio, classify, composite, deglint, depthmask, postproc, report, watercol

gdal.UseExceptions()
NODATA = -9999.0


def _log(msg, warn=False):
    print(("WARNING: " if warn else "") + msg)


def read_bands(path, idx):
    """idx: {name: band number}. Returns (arrays, geotransform, projection, (w, h))."""
    ds = gdal.Open(path)
    gt = ds.GetGeoTransform()
    if gt[2] != 0 or gt[4] != 0:
        raise ValueError(L("Rotated rasters are not supported.", "No se admiten rásteres girados."))
    out = {}
    for name, i in idx.items():
        if i < 1 or i > ds.RasterCount:
            raise ValueError(L(f"Band {i} does not exist (the raster has {ds.RasterCount}).",
                               f"La banda {i} no existe (el ráster tiene {ds.RasterCount})."))
        b = ds.GetRasterBand(i)
        a = b.ReadAsArray().astype(np.float64)
        nd = b.GetNoDataValue()
        if nd is not None:
            a[a == nd] = np.nan
        out[name] = a
    return out, gt, ds.GetProjection(), (ds.RasterXSize, ds.RasterYSize)


def write_raster(path, arrays, names, gt, proj, dtype=gdal.GDT_Float32, nodata=NODATA, metadata=None):
    h, w = arrays[0].shape
    o = gdal.GetDriverByName("GTiff").Create(path, w, h, len(arrays), dtype,
                                             options=["COMPRESS=DEFLATE", "TILED=YES"])
    o.SetGeoTransform(gt)
    o.SetProjection(proj)
    for k, v in (metadata or {}).items():
        o.SetMetadataItem(str(k), str(v))
    for i, (a, n) in enumerate(zip(arrays, names), start=1):
        b = o.GetRasterBand(i)
        b.WriteArray(a)
        b.SetNoDataValue(nodata)
        b.SetDescription(n)
    o.FlushCache()
    o = None
    return path


def deglint_file(in_path, idx, deep_wkt, out_path, percentile=0.0, log=_log):
    """Hedley sunglint correction, strip by strip. idx needs blue, green, red, nir. Returns the fit."""
    grid = blockio.Grid.of(in_path)
    lay = blockio.layers_of(in_path, idx, grid)
    s = blockio.sample_polygon(deep_wkt, lay, grid)
    p = deglint.fit([s["blue"], s["green"], s["red"]], s["nir"], np.ones(len(s["nir"]), bool), percentile)
    log(L(f"Deep-water sample: {p['n']} pixels, NIR reference {p['nir_ref']:.5f}",
          f"Muestra de agua profunda: {p['n']} píxeles, NIR de referencia {p['nir_ref']:.5f}"))
    for name, bb in zip(("blue", "green", "red"), p["bands"]):
        log(L(f"  {name}: slope {bb['slope']:.3f}, R² {bb['r2']:.3f}",
              f"  {name}: pendiente {bb['slope']:.3f}, R² {bb['r2']:.3f}"))
        if bb["r2"] < 0.3:
            log(L(f"  {name}: low R², the glint model is weak for this band.",
                  f"  {name}: R² bajo, el modelo de brillo es débil en esta banda."), True)
    out = blockio.Writer(out_path, grid, ["B02", "B03", "B04", "B08"])
    n_neg = 0
    for r0, nr in grid.strips():
        b = {k: v.read(r0, nr) for k, v in lay.items()}
        vis = deglint.apply([b["blue"], b["green"], b["red"]], b["nir"], p)
        n_neg += sum(int((np.isfinite(v) & (v <= 0)).sum()) for v in vis)
        out.write(r0, [np.where(np.isfinite(a), a, NODATA).astype(np.float32) for a in vis + [b["nir"]]])
    out.close()
    if n_neg:
        log(L(f"{n_neg} band values became <= 0 after correction; they will be invalid "
              "for the log-based methods.",
              f"{n_neg} valores de banda quedaron <= 0 tras la corrección; no valdrán para los métodos con "
              "logaritmos."), True)
    return p


def deep_stats(layers, grid, deep_wkt, min_pixels=50):
    """Mean and standard deviation of each layer inside the deep-water polygon."""
    s = blockio.sample_polygon(deep_wkt, layers, grid)
    out = {}
    for k, v in s.items():
        v = v[np.isfinite(v)].astype(np.float64)
        if len(v) < min_pixels:
            raise ValueError(L(f"Only {len(v)} valid pixels of {k} in the deep-water polygon; need at least {min_pixels}.",
                               f"Solo hay {len(v)} píxeles válidos de {k} en el polígono de agua profunda; hacen "
                               f"falta al menos {min_pixels}."))
        out[k] = {"mean": float(v.mean()), "sd": float(v.std(ddof=1)), "sd0": float(v.std()), "n": int(len(v))}
    return out


def rinf_from(stats, k_sigma=2.0, log=_log):
    """R_inf per band = mean - k_sigma * standard deviation inside the deep-water polygon.

    With k_sigma = 0 it is the plain mean; subtracting k standard deviations keeps
    fewer pixels below R_inf (which would be lost for Lyzenga).
    """
    r_inf = {}
    for k, s in stats.items():
        r_inf[k] = s["mean"] - k_sigma * s["sd0"]
        if r_inf[k] <= 0:
            log(L(f"R_inf of {k} is {r_inf[k]:.5f} (<= 0) with k = {k_sigma:g}; ln(R - R_inf) still works, "
                  "but the deep-water sample is very noisy or very dark.",
                  f"R∞ de {k} es {r_inf[k]:.5f} (<= 0) con k = {k_sigma:g}; ln(R − R∞) sigue funcionando, pero "
                  "la muestra de agua profunda es muy ruidosa o muy oscura."), True)
    return r_inf


# ---------------------------------------------------------------- helpers
def read_aligned(path, band, gt, size, proj, resample="bilinear"):
    """One band of any raster resampled onto the grid (gt, size, proj). NaN = no data."""
    w, h = size
    bounds = (gt[0], gt[3] + gt[5] * h, gt[0] + gt[1] * w, gt[3])
    src = gdal.Open(path)
    if band < 1 or band > src.RasterCount:
        raise ValueError(L(f"{os.path.basename(path)}: band {band} does not exist.",
                           f"{os.path.basename(path)}: la banda {band} no existe."))
    same = (src.GetGeoTransform() == tuple(gt) and src.RasterXSize == w and src.RasterYSize == h)
    if same:
        b = src.GetRasterBand(band)
        a = b.ReadAsArray().astype(np.float64)
        nd = b.GetNoDataValue()
    else:
        ds = gdal.Warp("", src, format="MEM", outputBounds=bounds, width=w, height=h, dstSRS=proj,
                       resampleAlg=resample, bandList=[band], dstNodata=NODATA,
                       outputType=gdal.GDT_Float64)
        b = ds.GetRasterBand(1)
        a = b.ReadAsArray().astype(np.float64)
        nd = NODATA
    if nd is not None:
        a[a == nd] = np.nan
    return a, src.GetMetadata() or {}


def depth_sign(sign, metadata):
    """'auto' reads the StarShoal metadata (elevation, negative down -> -1); default depth."""
    if sign in (1, -1, 1.0, -1.0):
        return float(sign)
    s = (metadata.get("STARSHOAL_SIGN") or "").lower()
    return -1.0 if s.startswith("elevation") else 1.0


def guess_sign(layer, sign, what, log=_log):
    """Like depth_sign, but 'auto' on a raster without StarShoal metadata looks at the values:
    mostly negative means elevation (negative down), as in EMODnet or GEBCO."""
    s_ = depth_sign(sign, layer.metadata)
    if sign in (1, -1, 1.0, -1.0) or "STARSHOAL_SIGN" in layer.metadata:
        return s_
    ds = layer.ds
    bw, bh = min(ds.RasterXSize, 512), min(ds.RasterYSize, 512)
    a = layer.b.ReadAsArray(0, 0, ds.RasterXSize, ds.RasterYSize, buf_xsize=bw, buf_ysize=bh).astype(np.float64)
    if layer.nodata is not None and np.isfinite(layer.nodata):
        a[a == layer.nodata] = np.nan
    a = a[np.isfinite(a)]
    if a.size and np.median(a) < 0:
        log(L(f"{what}: the values are mostly negative, read as elevation (negative down). Choose the sign by "
              "hand if this is wrong.",
              f"{what}: los valores son casi todos negativos, se leen como cota (negativa hacia abajo). Elige el "
              "signo a mano si no es así."))
        return -1.0
    return s_


def _metres(xs, ys, proj, warn=None):
    """Sample coordinates in metres for the spatial blocks (block size is given in metres).
    Projected CRS: map units x linear units. Geographic CRS: local approximation around the mean latitude."""
    srs = osr.SpatialReference()
    srs.ImportFromWkt(proj)
    if srs.IsProjected():
        u = srs.GetLinearUnits() or 1.0
        return xs * u, ys * u
    if srs.IsGeographic() and len(ys):
        lat0 = float(np.nanmean(ys))
        if warn is not None:
            warn(L("The image is in a geographic CRS (degrees): block sizes are converted to degrees around the "
                   "mean latitude, and areas are not given in hectares. A projected CRS (UTM) is better.",
                   "La imagen está en un SRC geográfico (grados): el tamaño de bloque se pasa a grados en torno a "
                   "la latitud media, y las superficies no salen en hectáreas. Mejor un SRC proyectado (UTM)."))
        return xs * 111320.0 * np.cos(np.radians(lat0)), ys * 110574.0
    return xs, ys


def _pixel_m(gt, proj):
    srs = osr.SpatialReference()
    srs.ImportFromWkt(proj)
    return abs(gt[1]) * srs.GetLinearUnits() if srs.IsProjected() else None


def pixel_area_ha(gt, proj):
    srs = osr.SpatialReference()
    srs.ImportFromWkt(proj)
    if not srs.IsProjected():
        return None
    return abs(gt[1] * gt[5]) * srs.GetLinearUnits() / 1e4 * srs.GetLinearUnits()


# ---------------------------------------------------------------- composite
def composite_file(paths, out_path, min_scenes=1, log=_log, max_days=45):
    base, _ = os.path.splitext(out_path)
    st = composite.median(paths, out_path, base + "_count.tif", min_scenes, log, max_days)
    st["count"] = base + "_count.tif"
    return st


# ---------------------------------------------------------------- water column
def watercolumn_file(in_path, idx, sand_wkt, out_path, deep_wkt=None, k_sigma=2.0, log=_log, floor_sigma=1.0):
    """Lyzenga depth-invariant indices for every pair of the bands in idx, strip by strip.

    With a deep-water polygon, R - R_inf is floored at floor_sigma standard deviations
    of the deep-water sample (0 = no floor, holes stay). Floored pixels are written to
    <out>_floored.tif. Returns the list of per-pair statistics.
    """
    grid = blockio.Grid.of(in_path)
    lay = blockio.layers_of(in_path, idx, grid)
    r_inf, floor = None, None
    if deep_wkt:
        ds_ = deep_stats(lay, grid, deep_wkt)
        r_inf = rinf_from(ds_, k_sigma, log)
        log(L(f"R_inf (deep-water mean - {k_sigma:g} sd): ", f"R∞ (media del agua profunda − {k_sigma:g} σ): ")
            + ", ".join(f"{k} {v:.5f}" for k, v in r_inf.items()))
        if floor_sigma > 0:
            floor = {k: floor_sigma * v["sd0"] for k, v in ds_.items()}
            log(L(f"Floor of R - R_inf ({floor_sigma:g} sd of deep water): ",
                  f"Suelo de R − R∞ ({floor_sigma:g} σ del agua profunda): ")
                + ", ".join(f"{k} {v:.5f}" for k, v in floor.items()))
    else:
        log(L("No deep-water polygon: R_inf = 0 (ln R), no floor. Fine for a first look; with a deep-water sample "
              "the index follows the Lyzenga model more closely and has no holes.",
              "Sin polígono de agua profunda: R∞ = 0 (ln R), sin suelo. Vale para un primer vistazo; con una "
              "muestra de agua profunda el índice sigue mejor el modelo de Lyzenga y no tiene huecos."), True)
    # attenuation ratios from the uniform-bottom polygon only
    sand = blockio.sample_polygon(sand_wkt, lay, grid)
    sand = {k: v[None, :].astype(np.float64) for k, v in sand.items()}
    sand_mask = np.ones(next(iter(sand.values())).shape, bool)
    _o, stats, warns, _f = watercol.dii(sand, sand_mask, r_inf, floor=floor)
    ratios = {s["pair"]: s["ratio"] for s in stats}
    for s in stats:
        log(L(f"DII {s['pair'].replace('_', '/')}: k ratio {s['ratio']:.3f}, correlation over the uniform bottom "
              f"{s['r']:.2f}, {s['n']} pixels",
              f"DII {s['pair'].replace('_', '/')}: relación k {s['ratio']:.3f}, correlación sobre el fondo "
              f"uniforme {s['r']:.2f}, {s['n']} píxeles"))
    for wmsg in warns:
        if "have no value" not in wmsg and "sin valor" not in wmsg:  # holes are counted over the whole raster below
            log(wmsg, True)
    names = [f"DII_{s['pair']}" for s in stats]
    meta = {"GLUB_PRODUCT": "Lyzenga depth-invariant bottom index (relative, no units)",
            "GLUB_SOURCE": os.path.basename(in_path),
            "GLUB_R_INF": ("deep-water mean - %g sd: " % k_sigma + ", ".join(f"{k}={v:.5f}" for k, v in r_inf.items()))
            if r_inf else "0",
            "GLUB_FLOOR": (f"R - R_inf floored at {floor_sigma:g} sd of deep water: "
                              + ", ".join(f"{k}={v:.5f}" for k, v in floor.items())) if floor else "none"}
    for s in stats:
        meta[f"GLUB_K_RATIO_{s['pair'].upper()}"] = f"{s['ratio']:.5f} (r={s['r']:.3f}, n={s['n']})"
    base, _ = os.path.splitext(out_path)
    out = blockio.Writer(out_path, grid, names, metadata=meta)
    fl_out = blockio.Writer(base + "_floored.tif", grid, ["floored"], gdal.GDT_Byte, 255,
                            metadata={"GLUB_FLOORED": "1 = R - R_inf floored in some band (like deep water), 0 = not"}
                            ) if floor else None
    n_floor, n_water, holes = 0, 0, 0
    for r0, nr in grid.strips():
        b = {k: v.read(r0, nr).astype(np.float64) for k, v in lay.items()}
        water = np.isfinite(b[next(iter(b))])
        X = {}
        fl_any = np.zeros(water.shape, bool)
        for k, a in b.items():
            if floor:
                X[k], fl = watercol.log_minus(a, r_inf.get(k, 0.0), floor[k])
                fl_any |= fl
            else:
                X[k] = watercol.log_minus(a, (r_inf or {}).get(k, 0.0))
        arrays = []
        for s in stats:
            i_, j_ = s["pair"].split("_")
            d = X[i_] - ratios[s["pair"]] * X[j_]
            holes += int((water & ~np.isfinite(d)).sum())
            arrays.append(np.where(np.isfinite(d), d, NODATA).astype(np.float32))
        out.write(r0, arrays)
        n_water += int(water.sum())
        if fl_out:
            n_floor += int((fl_any & water).sum())
            fl_out.write(r0, [np.where(water, fl_any.astype(np.uint8), 255).astype(np.uint8)])
    if fl_out:
        fl_out.close()
        out.ds.SetMetadataItem("GLUB_FLOORED_PIXELS", str(n_floor))
        log(L(f"{n_floor} water pixels ({100 * n_floor / max(n_water, 1):.1f} %) were floored (R - R_inf below the "
              "floor): deep-water noise, or a bottom darker than the water column where the Lyzenga model does not "
              "apply. Their index is not a bottom measurement; see the _floored.tif mask.",
              f"{n_floor} píxeles de agua ({100 * n_floor / max(n_water, 1):.1f} %) quedaron en el suelo (R − R∞ "
              "por debajo del suelo): ruido del agua profunda o un fondo más oscuro que el agua, donde el modelo "
              "de Lyzenga no vale. Su índice no mide el fondo; mira la máscara _floored.tif."))
    elif os.path.exists(base + "_floored.tif"):
        os.remove(base + "_floored.tif")  # a stale mask from an earlier run would mislead the classification
    out.close()
    if holes:
        log(L(f"{holes} index values have no value (R <= R_inf and no floor).",
              f"{holes} valores del índice sin valor (R <= R∞ y sin suelo)."), True)
    return stats


# ---------------------------------------------------------------- classification
PALETTE = ["#e41a1c", "#377eb8", "#984ea3", "#ff7f00", "#a65628", "#f781bf", "#999999", "#66c2a5"]
KEYWORDS = (
    (("posidonia",), "#1b7837"), (("cymodocea",), "#5aae61"), (("zostera", "nanozostera"), "#a6dba0"),
    (("pradera", "seagrass", "fanerog", "thalassia", "halodule", "syringodium"), "#2ca25f"),
    (("mata", "matte", "tanatocen"), "#6b4c2a"), (("caulerpa", "alga", "macroalg"), "#b8860b"),
    (("arena", "sand", "sediment"), "#f2d98d"), (("fango", "mud", "limo"), "#bfa37c"),
    (("roca", "rock", "reef", "arrecife"), "#7f7f7f"),
)
STATE_STYLE = {depthmask.CODE_HIDDEN: ("bottom not visible / fondo no visible", "#c9d3dd"),
               depthmask.CODE_TOO_DEEP: ("too deep for seagrass / demasiado hondo", "#23395d")}
UNSURE_STYLE = ("low confidence / sin clasificar (baja confianza)", "#f4a3c0")


def class_color(name, k):
    n = str(name).lower()
    for keys, col in KEYWORDS:
        if any(key in n for key in keys):
            return col
    return PALETTE[k % len(PALETTE)]


def sort_labels(labels):
    labs = sorted({str(v) for v in labels})
    try:
        return sorted(labs, key=float)
    except ValueError:
        return labs


def write_qml(path, legend):
    """Paletted style next to the class raster, so QGIS styles it when loaded by hand."""
    items = "\n".join(f'        <paletteEntry value="{c}" label="{_xml(l)}" color="{col}" alpha="255"/>'
                      for c, l, col in legend)
    qml = f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28">
  <pipe>
    <rasterrenderer type="paletted" band="1" opacity="1" nodataColor="">
      <colorPalette>
{items}
      </colorPalette>
    </rasterrenderer>
  </pipe>
</qgis>
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(qml)


def _xml(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def classify_file(refl_path, band_idx, training, options, out_dir, dii_path=None, extra=(),
                  mask=None, settings=(), credit="", log=_log, progress=None):
    """Supervised benthic classification of a reflectance raster, strip by strip.

    band_idx: {name: band} reflectance bands used as features.
    training: {"kind": "points", "xs", "ys", "labels"} or {"kind": "polygons", "wkts", "labels"},
              coordinates / WKT in the raster CRS.
    options: method ('rf' or 'ml'), trees, balanced, split ('blocks' or 'random'), block_size,
             val_fraction, seed, max_per_polygon, depth_bins, refl_features, shrink,
             filter_window, mmu, min_prob (0 = off: below it a visible pixel is left
             'unsure', code 252, instead of forcing a class), texture_window (0, 3 or 5:
             local sd of the water-column indices, else of blue and green, as features).
    dii_path: optional raster whose bands are all added as features (water-column indices).
    extra: [(path, band, name)] extra feature rasters (e.g. depth; not recommended).
    mask: {opt_path, opt_band, opt_sign, opt_limit, trust_path, eco_path, eco_band, eco_sign, eco_limit,
           deep_wkt, sig_bands, n_sigma}.
    Memory: two passes over strips of rows; only one byte per pixel (the mask state)
    is kept for the whole raster.
    Returns (summary, warnings, written).
    """
    prog = progress or (lambda p: None)
    mask = mask or {}
    warns = []

    def warn(msg):
        warns.append(msg)
        log(msg, True)

    grid = blockio.Grid.of(refl_path)
    gt, proj, w, h = grid.gt, grid.proj, grid.w, grid.h
    refl = blockio.layers_of(refl_path, band_idx, grid)
    feat_layers, fnames = [], []
    if options.get("refl_features", True):
        for name in band_idx:
            feat_layers.append(refl[name])
            fnames.append(name)
    floored_layer = None
    dii_layers = []
    if dii_path:
        fpath = os.path.splitext(dii_path)[0] + "_floored.tif"
        if os.path.exists(fpath):
            floored_layer = blockio.Layer(fpath, 1, grid, "near")
        ds = gdal.Open(dii_path)
        nb = ds.RasterCount
        ds = None
        for b in range(1, nb + 1):
            lyr = blockio.Layer(dii_path, b, grid)
            feat_layers.append(lyr)
            fnames.append(lyr.description or f"DII_{b}")
            dii_layers.append((lyr, fnames[-1]))
    for path, band, name in extra:
        feat_layers.append(blockio.Layer(path, band, grid))
        fnames.append(name)
    tex = int(options.get("texture_window", 0) or 0)
    if tex in (3, 5):
        # texture of the bottom: local sd of the depth-invariant indices, else of blue and green
        if dii_layers:
            srcs = list(dii_layers)
        else:
            srcs = [(refl[b], b) for b in ("blue", "green") if b in refl]
        for lyr, name in srcs:
            feat_layers.append(blockio.TextureLayer(lyr, tex, f"sd{tex}_{name}"))
            fnames.append(f"sd{tex}_{name}")
        log(L(f"Texture: local standard deviation in {tex}x{tex} windows of ", f"Textura: desviación típica local en "
              f"ventanas de {tex}x{tex} de ") + ", ".join(n for _l, n in srcs) + ".")
    if not feat_layers:
        raise ValueError(L("No features: choose reflectance bands or water-column indices.",
                           "Sin variables: elige bandas de reflectancia o índices de columna de agua."))
    first = refl[next(iter(band_idx))]

    # ---- depth layers
    opt_l = eco_l = trust_l = None
    opt_sign = eco_sign = 1.0
    opt_is_sdb = False
    opt_limit = mask.get("opt_limit")
    if mask.get("opt_path"):
        opt_l = blockio.Layer(mask["opt_path"], mask.get("opt_band", 1), grid)
        opt_is_sdb = "STARSHOAL_SIGN" in opt_l.metadata
        opt_sign = guess_sign(opt_l, mask.get("opt_sign", "auto"), L("Optical depth raster", "Capa de profundidad óptica"), log)
        if opt_limit is None:
            try:
                opt_limit = float(opt_l.metadata.get("STARSHOAL_DEPTH_LIMIT_M"))
                log(L(f"Optical depth limit read from the StarShoal raster: {opt_limit:.2f} m",
                      f"Límite óptico leído del ráster de StarShoal: {opt_limit:.2f} m"))
            except (TypeError, ValueError):
                raise ValueError(L("Give the optical depth limit (the depth raster has no StarShoal limit in its "
                                   "metadata).",
                                   "Da el límite óptico (la capa de profundidad no trae el límite de StarShoal en "
                                   "sus metadatos)."))
    if mask.get("trust_path"):
        trust_l = blockio.Layer(mask["trust_path"], 1, grid, "near")
    if mask.get("eco_path"):
        eco_l = blockio.Layer(mask["eco_path"], mask.get("eco_band", 1), grid)
        eco_sign = guess_sign(eco_l, mask.get("eco_sign", "auto"), L("Independent bathymetry", "Batimetría independiente"), log)
        if "STARSHOAL_SIGN" in eco_l.metadata:
            warn(L("The ecological bathymetry is a StarShoal SDB raster. Past its optical limit an SDB is "
                   "extrapolated and cannot place the ecological limit; use an independent bathymetry.",
                   "La batimetría ecológica es un SDB de StarShoal. Pasado su límite óptico un SDB está "
                   "extrapolado y no puede situar el límite ecológico; usa una batimetría independiente."))
    if opt_l is None and eco_l is not None and opt_limit is None:
        raise ValueError(L("Give the optical depth limit to use the ecological bathymetry as the optical depth too.",
                           "Da el límite óptico para usar la batimetría ecológica también como profundidad óptica."))
    eco_limit = mask.get("eco_limit") if eco_l is not None else None
    sig_layers, sig_stats = None, None
    n_sigma = mask.get("n_sigma", 3.0)
    if mask.get("deep_wkt"):
        sig_idx = mask.get("sig_bands") or {"blue": band_idx.get("blue", 1), "green": band_idx.get("green", 2)}
        sig_layers = blockio.layers_of(refl_path, sig_idx, grid)
        sig_stats = {k: {"mean": v["mean"], "sd": v["sd"], "n": v["n"]}
                     for k, v in deep_stats(sig_layers, grid, mask["deep_wkt"]).items()}
        log(L("Bottom-signal test, deep-water sample: ", "Prueba de señal, muestra de agua profunda: ") + "; ".join(
            L(f"{b} mean {v['mean']:.5f} sd {v['sd']:.5f} (n={v['n']})",
              f"{b} media {v['mean']:.5f} σ {v['sd']:.5f} (n={v['n']})") for b, v in sig_stats.items())
            + L(f"; visible needs |R - mean| > {n_sigma:g} sd in some band.",
                f"; visible exige |R − media| > {n_sigma:g} σ en alguna banda."))
    if eco_l is not None:
        bins_layer, bins_source = eco_l, "eco"
    elif opt_l is not None:
        bins_layer = opt_l
        bins_source = "sdb" if opt_is_sdb else "opt"
    else:
        bins_layer, bins_source = None, None

    # ---- training sample locations (no raster reading yet)
    if training["kind"] == "points":
        rows, cols, labels, groups, tinfo = classify.points_to_samples(
            training["xs"], training["ys"], training["labels"], gt, (h, w))
        if tinfo["outside"]:
            warn(L(f"{tinfo['outside']} training points fall outside the raster.",
                   f"{tinfo['outside']} puntos de verdad de campo caen fuera del ráster."))
        if tinfo["conflicts"]:
            warn(L(f"{tinfo['conflicts']} training points share a pixel with a point of another class; dropped.",
                   f"{tinfo['conflicts']} puntos comparten píxel con un punto de otra clase; se descartan."))
        if tinfo["duplicates"]:
            log(L(f"{tinfo['duplicates']} duplicated training points in the same pixel were merged.",
                  f"{tinfo['duplicates']} puntos repetidos en el mismo píxel se han unido."))
    else:
        wkts_t = training["wkts"]
        shrink_m = options.get("shrink", 0) or 0
        if shrink_m > 0:
            wkts_t, gone = classify.shrink(wkts_t, shrink_m)
            log(L(f"Reference polygons shrunk by {shrink_m:g} (CRS units) to leave out mixed edge pixels.",
                  f"Polígonos encogidos {shrink_m:g} (unidades del SRC) para dejar fuera los píxeles mezclados "
                  "del borde."))
            if gone:
                warn(L(f"{gone} reference polygons vanished when shrunk by {shrink_m:g}: they are narrower than "
                       f"{2 * shrink_m:g}. Use a smaller value or draw larger polygons.",
                       f"{gone} polígonos desaparecieron al encoger {shrink_m:g}: son más estrechos que "
                       f"{2 * shrink_m:g}. Usa un valor menor o dibuja polígonos más grandes."))
        rows, cols, labels, groups, tinfo = classify.polygons_to_samples(
            wkts_t, training["labels"], gt, (h, w), proj,
            options.get("max_per_polygon", 200), options.get("seed", 42))
        if tinfo["empty"]:
            warn(L(f"{tinfo['empty']} training polygons contain no pixel centre of the raster.",
                   f"{tinfo['empty']} polígonos no contienen ningún centro de píxel del ráster."))
        if tinfo["invalid"]:
            warn(L(f"{tinfo['invalid']} training polygons could not be read.",
                   f"{tinfo['invalid']} polígonos no se pudieron leer."))
        if tinfo["capped"]:
            log(L(f"{tinfo['capped']} polygons had more than {options.get('max_per_polygon')} pixels and were "
                  "subsampled at random.",
                  f"{tinfo['capped']} polígonos tenían más de {options.get('max_per_polygon')} píxeles y se "
                  "submuestrearon al azar."))
    labels = np.array([str(v) for v in labels], dtype=object)
    ns = len(rows)
    X_all = np.full((ns, len(feat_layers)), np.nan, dtype=np.float32)
    st_s = np.zeros(ns, dtype=np.uint8)
    d_s = np.full(ns, np.nan, dtype=np.float32)
    fl_s = np.zeros(ns, dtype=bool)
    prog(5)

    # ---- pass 1: mask state for every pixel, sample values
    state = np.zeros((h, w), dtype=np.uint8)   # 0 outside, 1 visible, 2 hidden, 3 too deep; +10 = no feature
    mstats = {}
    n_vis_usable, n_unusable_vis, n_floored_vis = 0, 0, 0
    strips = list(grid.strips())
    for si, (r0, nr) in enumerate(strips):
        valid = np.isfinite(first.read(r0, nr))
        F = np.stack([l.read(r0, nr) for l in feat_layers], -1)
        usable = np.all(np.isfinite(F), -1)
        dopt = opt_l.read(r0, nr) * opt_sign if opt_l is not None else None
        deco = eco_l.read(r0, nr) * eco_sign if eco_l is not None else None
        tr_ = trust_l.read(r0, nr) if trust_l is not None else None
        signal = None
        if sig_layers is not None:
            signal = np.zeros(valid.shape, bool)
            for k, lyr in sig_layers.items():
                a = lyr.read(r0, nr)
                with np.errstate(invalid="ignore"):
                    signal |= np.isfinite(a) & (np.abs(a - sig_stats[k]["mean"]) > n_sigma * sig_stats[k]["sd"])
        st, part, _w = depthmask.states(valid, dopt, opt_limit, tr_, deco, eco_limit, signal, quiet=True)
        depthmask.add_stats(mstats, part)
        vis = (st == depthmask.VISIBLE) & usable
        n_vis_usable += int(vis.sum())
        n_unusable_vis += int(((st == depthmask.VISIBLE) & ~usable).sum())
        fl = None
        if floored_layer is not None:
            fl = floored_layer.read(r0, nr) == 1
            n_floored_vis += int((fl & vis).sum())
        st_store = st.copy()
        st_store[(st == depthmask.VISIBLE) & ~usable] = 11
        state[r0:r0 + nr] = st_store
        sel = np.nonzero((rows >= r0) & (rows < r0 + nr))[0]
        if len(sel):
            rr, cc = rows[sel] - r0, cols[sel]
            X_all[sel] = F[rr, cc]
            st_s[sel] = st_store[rr, cc]
            if bins_layer is not None:
                dd = deco if bins_layer is eco_l else dopt
                d_s[sel] = dd[rr, cc]
            if fl is not None:
                fl_s[sel] = fl[rr, cc]
        prog(5 + 25 * (si + 1) / len(strips))
    for m in depthmask.summary_warnings(mstats, opt_l is not None, eco_l is not None, sig_layers is not None,
                                        eco_limit):
        warn(m)
    log(L(f"Water pixels: {mstats['valid']}. Bottom visible (classified): {mstats['visible']}. "
          f"Bottom not visible: {mstats['hidden']}. Too deep: {mstats['too_deep']}.",
          f"Píxeles de agua: {mstats['valid']}. Fondo visible (se clasifica): {mstats['visible']}. "
          f"Fondo no visible: {mstats['hidden']}. Demasiado hondo: {mstats['too_deep']}."))
    if sig_layers is not None:
        log(L(f"{mstats['no_signal']} pixels within the optical depth limit were left out because they do not "
              "differ from deep water (no bottom signal).",
              f"{mstats['no_signal']} píxeles dentro del límite óptico se quedan fuera porque no se distinguen del "
              "agua profunda (sin señal del fondo)."))

    # ---- samples usable for training
    classes = sort_labels(labels)
    n_by_class = {c: int((labels == c).sum()) for c in classes}
    ok_feat = st_s != 11
    for c in classes:
        sel = labels == c
        hidden = int((sel & (st_s == depthmask.HIDDEN)).sum())
        deep = int((sel & (st_s == depthmask.TOO_DEEP)).sum())
        nodata = int((sel & (st_s == 11)).sum())
        if nodata or hidden or deep:
            warn(L(f"Class {c}: {n_by_class[c]} samples; left out {hidden} where the bottom is not visible, {deep} "
                   f"deeper than the ecological limit and {nodata} on pixels without a value in some feature. Only "
                   "samples where the bottom is seen can train the classifier.",
                   f"Clase {c}: {n_by_class[c]} muestras; se quedan fuera {hidden} donde no se ve el fondo, {deep} "
                   f"por debajo del límite ecológico y {nodata} en píxeles sin valor en alguna variable. Solo las "
                   "muestras donde se ve el fondo pueden entrenar el clasificador."))
    keep = ok_feat & (st_s == depthmask.VISIBLE)
    rows, cols, labels, groups = rows[keep], cols[keep], labels[keep], groups[keep]
    X, d_s, fl_s = X_all[keep], d_s[keep], fl_s[keep]
    classes = [c for c in classes if (labels == c).any()]
    if len(classes) < 2:
        raise ValueError(L("Fewer than two classes have usable samples where the bottom is visible.",
                           "Menos de dos clases tienen muestras útiles donde se ve el fondo."))
    y = np.array([classes.index(v) for v in labels], dtype=np.int64)
    for k, c in enumerate(classes):
        if (y == k).sum() < 10:
            warn(L(f"Class {c} has only {(y == k).sum()} usable samples; its accuracy will be very uncertain.",
                   f"La clase {c} solo tiene {(y == k).sum()} muestras útiles; su exactitud será muy incierta."))
    xs = gt[0] + (cols + 0.5) * gt[1]
    ys = gt[3] + (rows + 0.5) * gt[5]
    mx, my = _metres(xs, ys, proj, warn)   # for the blocks only; the CSV keeps map coordinates
    prog(32)

    # ---- split, fit, validate
    if options.get("split") == "blocks_all":
        val, swarns = classify.split_common_blocks(
            mx, my, y, groups, options.get("block_size", 500), options.get("val_fraction", 0.3),
            options.get("seed", 42))
    else:
        val, swarns = classify.split_by_class_blocks(
            mx, my, y, groups, options.get("block_size", 500), options.get("val_fraction", 0.3),
            options.get("seed", 42), random=options.get("split", "blocks") == "random")
    for m in swarns:
        warn(m)
    cal = ~val
    method = options.get("method", "rf")
    model = classify.make_model(method, options.get("trees", 300), options.get("balanced", False),
                                options.get("seed", 42))
    if model is None:
        warn(L("scikit-learn is not installed: Random Forest is not available, using maximum likelihood.",
               "scikit-learn no está instalado: no hay Random Forest, se usa máxima verosimilitud."))
        method = "ml"
        model = classify.make_model("ml", balanced=options.get("balanced", False))
    if len(np.unique(y[cal])) < len(classes):
        raise ValueError(L("Some class has no calibration samples after the split. Use smaller blocks, a lower "
                           "validation fraction or the split by class.",
                           "Alguna clase se quedó sin muestras de calibración tras la separación. Usa bloques más "
                           "pequeños, menos fracción de validación o la separación por clase."))
    model.fit(X[cal], y[cal])
    k = len(classes)
    min_prob = float(options.get("min_prob", 0) or 0)
    if val.any():
        pv_proba = classify.predict_chunks(model, X[val])
        pred_val = pv_proba.argmax(1).astype(np.int64)
        unsure_val = pv_proba.max(1) < min_prob if min_prob > 0 else np.zeros(int(val.sum()), bool)
    else:
        pred_val = np.array([], dtype=np.int64)
        unsure_val = np.array([], dtype=bool)
    sure_val = ~unsure_val
    # pred_u: the predicted class, or k where the classifier is not sure enough
    pred_u = np.where(unsure_val, k, pred_val)
    cm = accuracy.confusion(y[val][sure_val], pred_val[sure_val], k)
    summ = accuracy.summary(cm)
    summ["n_unsure"] = int(unsure_val.sum())
    summ["unsure_by_ref"] = np.bincount(y[val][unsure_val], minlength=k)
    if val.any():
        log(L(f"Validation: {summ['n']} samples, overall accuracy {100 * summ['oa']:.1f} %",
              f"Validación: {summ['n']} muestras, exactitud global {100 * summ['oa']:.1f} %")
            + (L(f" ({summ['n_unsure']} more samples, {100 * summ['n_unsure'] / max(int(val.sum()), 1):.1f} %, "
                 f"below the minimum probability {min_prob:g} are left out)",
                 f" (otras {summ['n_unsure']} muestras, {100 * summ['n_unsure'] / max(int(val.sum()), 1):.1f} %, "
                 f"por debajo de la probabilidad mínima {min_prob:g}, quedan fuera)") if min_prob > 0 else ""))
    else:
        warn(L("No validation samples: accuracy cannot be estimated.",
               "Sin muestras de validación: no se puede estimar la exactitud."))
    prog(40)

    # ---- pass 2: map, strip by strip
    os.makedirs(out_dir, exist_ok=True)
    legend = [(i + 1, c, class_color(c, i)) for i, c in enumerate(classes)]
    legend += [(code, lab, col) for code, (lab, col) in STATE_STYLE.items()]
    if min_prob > 0:
        legend.append((depthmask.CODE_UNSURE,) + UNSURE_STYLE)
    meta = {"GLUB_SOURCE": os.path.basename(refl_path), "GLUB_METHOD": classify.METHODS[method],
            "GLUB_FEATURES": ",".join(fnames),
            "GLUB_CLASSES": "; ".join(f"{c}={l}" for c, l, _ in legend),
            "GLUB_OPTICAL_LIMIT_M": f"{opt_limit:.2f}" if opt_limit is not None else "none",
            "GLUB_ECOLOGICAL_LIMIT_M": f"{eco_limit:g}" if eco_limit is not None else "none",
            "GLUB_MIN_PROBABILITY": f"{min_prob:g}" if min_prob > 0 else "off",
            "GLUB_VALIDATION_OA": f"{summ['oa']:.4f}" if summ["n"] else "none"}
    cls_path = os.path.join(out_dir, "classes.tif")
    prob_path = os.path.join(out_dir, "probability.tif")
    cw = blockio.Writer(cls_path, grid, ["class"], gdal.GDT_Byte, depthmask.CODE_NODATA, meta)
    pw = blockio.Writer(prob_path, grid, ["max_probability"] + [f"p_{c}" for c in classes],
                        metadata=dict(meta, GLUB_PROBABILITY="class probability from the classifier; relative, "
                                                                "not a calibrated confidence"))
    ct = gdal.ColorTable()
    for code, _lab, col in legend:
        ct.SetColorEntry(code, tuple(int(col[i:i + 2], 16) for i in (1, 3, 5)) + (255,))
    band = cw.ds.GetRasterBand(1)
    band.SetRasterColorTable(ct)
    names = [""] * 256
    for code, lab, _ in legend:
        names[code] = lab
    band.SetRasterCategoryNames(names)
    map_px = np.zeros(k, dtype=np.int64)
    n_unsure_px = 0
    for si, (r0, nr) in enumerate(strips):
        st = state[r0:r0 + nr]
        cls = np.full(st.shape, depthmask.CODE_NODATA, dtype=np.uint8)
        cls[st == depthmask.HIDDEN] = depthmask.CODE_HIDDEN
        cls[st == depthmask.TOO_DEEP] = depthmask.CODE_TOO_DEEP
        probs = np.full((k + 1,) + st.shape, NODATA, dtype=np.float32)
        vis = st == depthmask.VISIBLE
        if vis.any():
            F = np.stack([l.read(r0, nr) for l in feat_layers], -1)
            proba = classify.predict_chunks(model, F[vis])
            lab = np.argmax(proba, 1)
            code = (lab + 1).astype(np.uint8)
            if min_prob > 0:
                low = proba.max(1) < min_prob
                code[low] = depthmask.CODE_UNSURE
                n_unsure_px += int(low.sum())
                lab = lab[~low]
            cls[vis] = code
            map_px += np.bincount(lab, minlength=k)
            probs[0][vis] = proba.max(1)
            for i in range(k):
                probs[i + 1][vis] = proba[:, i]
        cw.write(r0, [cls])
        pw.write(r0, list(probs))
        prog(40 + 50 * (si + 1) / len(strips))
    cw.close()
    pw.close()
    del state
    write_qml(os.path.join(out_dir, "classes.qml"), legend)

    if n_floored_vis:
        warn(L(f"{n_floored_vis} classified pixels ({100 * n_floored_vis / max(n_vis_usable, 1):.1f} % of the visible "
               f"zone) have a floored water-column index (R below the deep-water level; {int(fl_s.sum())} training "
               "samples among them). There the index carries no bottom information and the reflectance bands decide. "
               "If many of them are seagrass, the bottom may be darker than the water column and the Lyzenga index "
               "does not suit it.",
               f"{n_floored_vis} píxeles clasificados ({100 * n_floored_vis / max(n_vis_usable, 1):.1f} % de la zona "
               f"visible) tienen el índice de columna de agua en el suelo (R por debajo del agua profunda; "
               f"{int(fl_s.sum())} muestras entre ellos). Ahí el índice no dice nada del fondo y deciden las bandas "
               "de reflectancia. Si muchos son pradera, ese fondo puede ser más oscuro que el agua y el índice de "
               "Lyzenga no le va bien."))
    if n_unusable_vis:
        log(L(f"{n_unusable_vis} pixels where the bottom is visible have no value in some feature; left as no data.",
              f"{n_unusable_vis} píxeles con fondo visible no tienen valor en alguna variable; quedan sin dato."))
    ha = pixel_area_ha(gt, proj)
    if ha is None:
        warn(L("The raster CRS is not projected: areas are given in pixels, not hectares.",
               "El SRC del ráster no es proyectado: las superficies van en píxeles, no en hectáreas."))
    if min_prob > 0:
        log(L(f"Minimum probability {min_prob:g}: {n_unsure_px} pixels "
              f"({100 * n_unsure_px / max(n_vis_usable, 1):.1f} % of the visible zone) left unclassified.",
              f"Probabilidad mínima {min_prob:g}: {n_unsure_px} píxeles "
              f"({100 * n_unsure_px / max(n_vis_usable, 1):.1f} % de la zona visible) quedan sin clasificar."))
    adj = None
    if val.any():
        if min_prob > 0:
            # the low-confidence zone is one more map stratum: its validation samples spread its area
            cm_strata = np.vstack([cm, summ["unsure_by_ref"][None, :]])
            adj = accuracy.area_adjusted(cm_strata, np.append(map_px, n_unsure_px), ha or 1.0)
        else:
            adj = accuracy.area_adjusted(cm, map_px, ha or 1.0)
    if adj and adj["rows_without_sample"]:
        names_r = classes + [L("low confidence", "baja confianza")]
        warn(L("Map strata without validation samples: ", "Estratos del mapa sin muestras de validación: ") +
             ", ".join(names_r[i] for i in adj["rows_without_sample"])
             + L(". Their area cannot be corrected (it is left out of the corrected areas).",
                 ". Su superficie no se puede corregir (queda fuera de las superficies corregidas)."))
    bins = None
    if bins_layer is not None and val.any():
        bins = accuracy.by_bins(y[val][sure_val], pred_val[sure_val], d_s[val][sure_val].astype(np.float64),
                                options.get("depth_bins", [0, 2, 5, 10, 15, 20]))
        if bins_source == "sdb":
            warn(L("Accuracy by depth uses the StarShoal SDB, which reads dark bottoms as deeper; the depth of "
                   "seagrass samples is overestimated. Give an independent bathymetry for a fair table.",
                   "La exactitud por profundidad usa el SDB de StarShoal, que lee más hondos los fondos oscuros; "
                   "la profundidad de las muestras de pradera sale exagerada. Da una batimetría independiente "
                   "para una tabla justa."))
    grp = None
    if training["kind"] == "polygons" and val.any():
        grp = accuracy.by_groups(y[val], pred_u, groups[val], k)
        log(L(f"Validation by polygon (majority of its pixels): {grp['n']} polygons, overall accuracy "
              f"{100 * grp['oa']:.1f} %", f"Validación por polígono (mayoría de sus píxeles): {grp['n']} polígonos, "
              f"exactitud global {100 * grp['oa']:.1f} %")
            + (L(f", {grp['ties']} ties counted as errors", f", {grp['ties']} empates contados como error")
               if grp["ties"] else "")
            + (L(f", {grp['unsure']} mostly low-confidence polygons counted as errors",
                 f", {grp['unsure']} polígonos mayoritariamente de baja confianza contados como error")
               if grp["unsure"] else ""))
    # ---- optional clean-up of the map, checked again on the same validation samples
    filt = None
    fw, mmu = options.get("filter_window", 0) or 0, options.get("mmu", 0) or 0
    if fw > 1 or mmu > 1:
        fpath = os.path.join(out_dir, "classes_filtered.tif")
        postproc.clean(cls_path, fpath, k, fw, mmu, log)
        write_qml(os.path.join(out_dir, "classes_filtered.qml"), legend)
        fpx = postproc.class_counts(fpath, k)
        filt = {"path": fpath, "window": fw, "mmu": mmu, "map_px": fpx}
        if val.any():
            pv = postproc.values_at(fpath, rows[val], cols[val]) - 1
            pv = np.where((pv >= 0) & (pv < k), pv, -1)
            ok = pv >= 0
            cmf = accuracy.confusion(y[val][ok], pv[ok], k)
            filt["acc"] = accuracy.summary(cmf)
            filt["cm"] = cmf
            if training["kind"] == "polygons":
                filt["groups_acc"] = accuracy.by_groups(y[val][ok], pv[ok], groups[val][ok], k)
            log(L(f"Filtered map, validation by pixel: overall accuracy {100 * filt['acc']['oa']:.1f} %",
                  f"Mapa filtrado, validación por píxel: exactitud global {100 * filt['acc']['oa']:.1f} %")
                + (L(f"; by polygon {100 * filt['groups_acc']['oa']:.1f} %",
                     f"; por polígono {100 * filt['groups_acc']['oa']:.1f} %") if "groups_acc" in filt else ""))
    importances = None
    if method == "rf" and hasattr(model, "feature_importances_"):
        importances = dict(zip(fnames, map(float, model.feature_importances_)))

    written = {"classes": cls_path, "probability": prob_path, "legend": legend}
    if filt:
        written["classes_filtered"] = filt["path"]
    with open(os.path.join(out_dir, "legend.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["code", "class", "color", "pixels", "hectares" if ha else "pixels_area"])
        for code, lab, col in legend:
            npx = int(map_px[code - 1]) if code <= k else int(
                mstats["hidden"] if code == depthmask.CODE_HIDDEN else
                mstats["too_deep"] if code == depthmask.CODE_TOO_DEEP else n_unsure_px)
            wr.writerow([code, lab, col, npx, f"{npx * (ha or 1):.2f}"])
    written["legend_csv"] = os.path.join(out_dir, "legend.csv")
    pts_path = os.path.join(out_dir, "samples.csv")
    pa_all = classify.predict_chunks(model, X)
    pred_all = pa_all.argmax(1)
    low_all = pa_all.max(1) < min_prob if min_prob > 0 else np.zeros(len(X), bool)
    with open(pts_path, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["x", "y", "class", "set", "predicted", "depth"] + fnames)
        for i in range(len(rows)):
            wr.writerow([f"{xs[i]:.2f}", f"{ys[i]:.2f}", classes[y[i]], "validation" if val[i] else "calibration",
                         "unsure" if low_all[i] else classes[pred_all[i]],
                         "" if not np.isfinite(d_s[i]) else f"{d_s[i]:.2f}"]
                        + [f"{v:.6g}" for v in X[i]])
    written["samples"] = pts_path

    summary = {"classes": classes, "method": method, "features": fnames, "cm": cm, "acc": summ,
               "adj": adj, "bins": bins, "bins_source": bins_source, "groups_acc": grp, "signal": sig_stats,
               "n_sigma": n_sigma if sig_stats else None, "importances": importances, "mask": mstats,
               "opt_limit": opt_limit, "eco_limit": eco_limit,
               "map_px": map_px, "ha": ha, "pixel_m": _pixel_m(gt, proj),
               "n_cal": int(cal.sum()), "n_val": int(val.sum()),
               "n_cal_class": [int(((y == i) & cal).sum()) for i in range(k)],
               "n_val_class": [int(((y == i) & val).sum()) for i in range(k)],
               "groups_val": int(len(np.unique(groups[val]))), "groups_cal": int(len(np.unique(groups[cal]))),
               "split": options.get("split", "blocks"), "training_kind": training["kind"], "filtered": filt,
               "shrink": options.get("shrink", 0) or 0, "min_prob": min_prob, "n_unsure_px": n_unsure_px}
    settings = list(settings) + [
        (L("Features", "Variables"), ", ".join(fnames)),
        (L("Optical depth limit", "Límite óptico"),
         f"{opt_limit:.2f} m" if opt_limit is not None else L("none (no depth raster)", "ninguno (sin capa de profundidad)")),
        (L("Ecological depth limit", "Límite ecológico"), f"{eco_limit:g} m" if eco_limit is not None else L("none", "ninguno")),
        (L("Class balance", "Equilibrio de clases"),
         L("on: every class weighs the same (rare classes found more often, their area grows)",
           "encendido: todas las clases pesan igual (las raras se detectan más y su superficie crece)")
         if options.get("balanced", False) else
         L("off: the model follows the class shares of the training sample",
           "apagado: el modelo sigue las proporciones de clases de la muestra")),
        (L("Reference polygons shrunk by", "Polígonos encogidos"),
         L(f"{options.get('shrink'):g} (CRS units)", f"{options.get('shrink'):g} (unidades del SRC)")
         if options.get("shrink") else "0"),
        (L("Texture", "Textura"),
         L(f"local sd in {tex}x{tex} windows", f"desviación típica local en ventanas de {tex}x{tex}")
         if tex in (3, 5) else L("off", "no")),
        (L("Map clean-up", "Limpieza del mapa"),
         (L(f"majority {fw}x{fw}", f"mayoría {fw}x{fw}") if fw > 1 else L("no majority filter", "sin filtro de mayoría"))
         + ", " + (L(f"minimum mapping unit {mmu} px", f"unidad mínima {mmu} px") if mmu > 1
                   else L("no minimum mapping unit", "sin unidad mínima"))),
        (L("Minimum probability", "Probabilidad mínima"),
         L(f"{min_prob:g}: below it a visible pixel is left unclassified (code 252)",
           f"{min_prob:g}: por debajo, el píxel visible queda sin clasificar (código 252)")
         if min_prob > 0 else L("off: every visible pixel gets a class", "apagada: todo píxel visible recibe una clase")),
        (L("Bottom-signal test", "Prueba de señal"),
         L(f"|R - deep mean| > {n_sigma:g} sd in ", f"|R − media profunda| > {n_sigma:g} σ en ") + ", ".join(sig_stats)
         if sig_stats else L("none (no deep-water polygon)", "no (sin polígono de agua profunda)")),
    ]
    rep = os.path.join(out_dir, "report.html")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write(report.build(settings, summary, warns, credit))
    written["report"] = rep
    prog(100)
    return summary, warns, written
