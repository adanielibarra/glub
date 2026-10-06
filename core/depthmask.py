"""Where the classifier is allowed to speak. numpy only.

Three states per pixel:
  VISIBLE    the satellite sees the bottom: the pixel is classified
  HIDDEN     the bottom is not visible, but seagrass could live there: no data
  TOO_DEEP   deeper than the ecological limit: no seagrass

The optical limit comes from a depth raster (StarShoal SDB, EMODnet, a chart...)
and, optionally, a StarShoal trust raster (0 = extrapolated = not seen). On top
of it, a per-pixel bottom-signal test against a deep-water sample (see
bottom_signal) makes the limit depend on the bottom: a dark meadow stops being
visible before sand does.
The ecological limit needs an INDEPENDENT bathymetry: an SDB cannot tell 25 m
from 40 m once it is past its optical limit, so with only an SDB everything past
the optical limit stays HIDDEN, never TOO_DEEP.
"""
import numpy as np
from .lang import L

VISIBLE, HIDDEN, TOO_DEEP = 1, 2, 3
CODE_HIDDEN, CODE_TOO_DEEP, CODE_NODATA = 250, 251, 255
# bottom visible but the classifier is not sure enough (optional minimum probability)
CODE_UNSURE = 252


def bottom_signal(bands, deep_mask, n_sigma=3.0, min_pixels=50):
    """Per-pixel test: is the pixel distinguishable from optically deep water?

    For each band, mean and standard deviation of the deep-water sample; a pixel
    has bottom signal if |R - mean| > n_sigma * sd in ANY band. The absolute value
    matters: a dark meadow can be darker than deep water in some band.
    This depends on the bottom type, unlike a single depth limit: over dark
    seagrass the signal fades at shallower depth than over sand.
    Returns (bool array, per-band stats).
    """
    ok = None
    stats = {}
    for name, a in bands.items():
        v = a[deep_mask & np.isfinite(a)]
        if len(v) < min_pixels:
            raise ValueError(L(f"Only {len(v)} valid pixels of {name} in the deep-water polygon; "
                               f"need at least {min_pixels}.",
                               f"Solo hay {len(v)} píxeles válidos de {name} en el polígono de agua profunda; "
                               f"hacen falta al menos {min_pixels}."))
        mu, sd = float(v.mean()), float(v.std(ddof=1))
        with np.errstate(invalid="ignore"):
            det = np.isfinite(a) & (np.abs(a - mu) > n_sigma * sd)
        stats[name] = {"mean": mu, "sd": sd, "n": int(len(v))}
        ok = det if ok is None else (ok | det)
    return ok, stats


def states(valid, depth_opt=None, opt_limit=None, trust=None, depth_eco=None, eco_limit=None,
           signal=None, quiet=False):
    """valid: bool array of pixels with usable reflectance.

    depth_opt / depth_eco: depth, positive down (NaN where unknown). Either can be
    None; if depth_opt is None and depth_eco is given, depth_eco is used for both.
    signal: optional bool array from bottom_signal(); a pixel is visible only if it
    also has bottom signal. Works on a whole raster or on one strip of it
    (quiet=True: no warnings; add up the stats and call summary_warnings once).
    Returns (state array uint8 with 0 outside valid, stats dict, warnings).
    """
    st = np.zeros(valid.shape, dtype=np.uint8)
    opt = depth_opt if depth_opt is not None else depth_eco
    if opt is None:
        seen = np.ones(valid.shape, dtype=bool)
    else:
        if opt_limit is None:
            raise ValueError(L("An optical depth limit is needed with a depth raster.",
                               "Con una capa de profundidad hace falta un límite óptico."))
        with np.errstate(invalid="ignore"):
            seen = np.isfinite(opt) & (opt <= opt_limit)
        if trust is not None:
            seen &= trust == 1
    no_signal = 0
    if signal is not None:
        no_signal = int((valid & seen & ~signal).sum())
        seen = seen & signal
    st[valid] = HIDDEN
    st[valid & seen] = VISIBLE
    conflicts = 0
    if depth_eco is not None and eco_limit is not None:
        with np.errstate(invalid="ignore"):
            deep = valid & np.isfinite(depth_eco) & (depth_eco > eco_limit)
        conflicts = int((deep & (st == VISIBLE)).sum())
        st[deep] = TOO_DEEP
    stats = {"valid": int(valid.sum()), "visible": int((st == VISIBLE).sum()),
             "hidden": int((st == HIDDEN).sum()), "too_deep": int((st == TOO_DEEP).sum()),
             "conflicts": conflicts, "no_signal": no_signal}
    warns = [] if quiet else summary_warnings(stats, depth_opt is not None, depth_eco is not None,
                                              signal is not None, eco_limit)
    return st, stats, warns


def add_stats(total, part):
    for k, v in part.items():
        total[k] = total.get(k, 0) + v
    return total


def summary_warnings(stats, has_opt, has_eco, has_signal, eco_limit=None):
    warns = []
    if not has_opt and not has_eco and not has_signal:
        warns.append(L("No depth raster and no bottom-signal test: every water pixel is classified. Deep "
                       "dark bottoms will be confused with seagrass and the map will be biased with depth.",
                       "Sin capa de profundidad ni prueba de señal: se clasifican todos los píxeles de agua. Los "
                       "fondos oscuros profundos se confundirán con pradera y el mapa saldrá sesgado con la "
                       "profundidad."))
    if not has_signal and (has_opt or has_eco):
        warns.append(L("No bottom-signal test (deep-water polygon): the optical limit is the same for every "
                       "bottom. Over dark seagrass the bottom fades at shallower depth than over sand, so near "
                       "the limit seagrass may be 'visible' when it is barely different from deep water.",
                       "Sin prueba de señal (polígono de agua profunda): el límite óptico es el mismo para todos "
                       "los fondos. Sobre pradera oscura el fondo deja de verse antes que sobre arena, así que "
                       "cerca del límite la pradera puede salir 'visible' cuando apenas se distingue del agua "
                       "profunda."))
    if stats.get("conflicts"):
        warns.append(L(f"{stats['conflicts']} pixels pass the visibility tests but are deeper than {eco_limit:g} m "
                       "in the ecological bathymetry. The independent bathymetry wins (they are marked too "
                       "deep). Check both rasters there.",
                       f"{stats['conflicts']} píxeles pasan las pruebas de visibilidad pero están a más de "
                       f"{eco_limit:g} m en la batimetría ecológica. Manda la batimetría independiente (se marcan "
                       "como demasiado hondos). Revisa las dos capas ahí."))
    if has_opt and not has_eco:
        warns.append(L("No independent bathymetry for the ecological limit: pixels past the optical limit are "
                       "'bottom not visible' (no data), not 'no seagrass'.",
                       "Sin batimetría independiente para el límite ecológico: lo que pasa del límite óptico es "
                       "'fondo no visible' (sin dato), no 'sin pradera'."))
    return warns
