"""Water-column correction: Lyzenga (1981) depth-invariant bottom index. numpy only.

For a pair of bands i, j over ONE bottom type seen at several depths:
    X = ln(R - R_inf)
    a = (var(X_i) - var(X_j)) / (2 cov(X_i, X_j))
    k_i/k_j = a + sqrt(a^2 + 1)
    DII_ij = X_i - (k_i/k_j) X_j
If the attenuation model holds, DII_ij does not change with depth over that
bottom and changes between bottoms. It is a relative index, not a reflectance.

What it needs from the user: a polygon over a single, uniform bottom (usually
sand) that spans a good range of depths. If the sample has no depth range, the
covariance is small, the ratio is noise and the index is useless; the
correlation of X_i and X_j in the sample tells how good it is.

With Sentinel-2 only blue and green (and red in the first few metres) reach the
bottom, so in practice there is one useful pair (blue, green).

Holes: where R <= R_inf the logarithm does not exist. That happens for two
different reasons: the pixel is at the noise level of deep water, or the bottom
is darker than the water column itself (a very dark meadow can be), where the
Lyzenga model simply does not apply. Instead of leaving holes, R - R_inf is
floored at a small positive value (by default one standard deviation of the
deep-water sample). The index there is not a bottom measurement: the floored
pixels are counted and written as a mask, and the classifier should rely on the
reflectance bands there. The attenuation ratio is computed with unfloored
pixels only.
"""
import numpy as np
from .lang import L

# below this correlation of X_i and X_j over the uniform bottom, the ratio is unreliable
MIN_R = 0.7
MIN_PIXELS = 50


def log_minus(r, rinf, floor=None):
    """ln(R - R_inf). With floor, R - R_inf below floor becomes floor (finite R only).
    Returns x, or (x, floored mask) when floor is given."""
    r = np.asarray(r, dtype=np.float64)
    d = r - rinf
    floored = np.zeros(d.shape, bool)   # floor 0 (deep water with no spread): nothing is floored
    if floor is not None and floor > 0:
        with np.errstate(invalid="ignore"):
            floored = np.isfinite(d) & (d < floor)
        d = np.where(floored, floor, d)
    with np.errstate(invalid="ignore", divide="ignore"):
        x = np.log(d)
    x[~np.isfinite(x)] = np.nan
    return x if floor is None else (x, floored)


def attenuation_ratio(xi, xj):
    """k_i/k_j from two arrays of X over one bottom. Returns dict with ratio and diagnostics."""
    ok = np.isfinite(xi) & np.isfinite(xj)
    xi, xj = xi[ok], xj[ok]
    n = len(xi)
    if n < MIN_PIXELS:
        raise ValueError(L(f"Only {n} valid pixels in the uniform-bottom sample; need at least {MIN_PIXELS}.",
                           f"Solo hay {n} píxeles válidos en la muestra de fondo uniforme; hacen falta al menos "
                           f"{MIN_PIXELS}."))
    vi, vj = float(np.var(xi, ddof=1)), float(np.var(xj, ddof=1))
    cij = float(np.cov(xi, xj, ddof=1)[0, 1])
    r = cij / np.sqrt(vi * vj) if vi > 0 and vj > 0 else np.nan
    if not cij > 0:
        raise ValueError(L("The two bands do not covary positively over the uniform-bottom sample: "
                           "it probably has no depth range or is not a single bottom type.",
                           "Las dos bandas no varían juntas sobre la muestra de fondo uniforme: seguramente no "
                           "tiene rango de profundidades o mezcla fondos."))
    a = (vi - vj) / (2.0 * cij)
    ratio = a + np.sqrt(a * a + 1.0)
    return {"ratio": float(ratio), "a": float(a), "r": float(r), "n": int(n),
            "var_i": vi, "var_j": vj, "cov": cij}


def pairs_of(bands):
    """All ordered pairs (shorter wavelength first) of the given band names."""
    order = [b for b in ("coastal", "blue", "green", "red") if b in bands]
    return [(order[i], order[j]) for i in range(len(order)) for j in range(i + 1, len(order))]


def dii(bands, sand_mask, r_inf=None, pairs=None, floor=None):
    """Depth-invariant indices for every pair.

    bands: {name: array}; sand_mask: bool array (uniform bottom at varying depth);
    r_inf: {name: value} (deep water), 0 if not given;
    floor: {name: value} minimum of R - R_inf (see module notes), None = leave holes.
    Returns (list of (name, array), list of stats dicts, warnings, floored mask or None).
    """
    r_inf = r_inf or {}
    pairs = pairs or pairs_of(bands)
    if not pairs:
        raise ValueError(L("The water-column correction needs at least two bands.",
                           "La corrección de la columna de agua necesita al menos dos bandas."))
    names = {p for pr in pairs for p in pr}
    X, raw, any_floor = {}, {}, None
    for b in names:
        raw[b] = log_minus(bands[b], r_inf.get(b, 0.0))
        if floor and floor.get(b):
            X[b], fl = log_minus(bands[b], r_inf.get(b, 0.0), floor[b])
            raw[b] = np.where(fl, np.nan, raw[b])  # the ratio never sees floored pixels
            any_floor = fl if any_floor is None else (any_floor | fl)
        else:
            X[b] = raw[b]
    out, stats, warns = [], [], []
    for i, j in pairs:
        s = attenuation_ratio(raw[i][sand_mask], raw[j][sand_mask])  # unfloored pixels only
        s.update(pair=f"{i}_{j}")
        if not s["r"] >= MIN_R:
            warns.append(L(f"DII {i}/{j}: correlation over the uniform bottom is {s['r']:.2f} (< {MIN_R}); "
                           "the attenuation ratio is unreliable. Check that the polygon covers one bottom "
                           "type over a real range of depths, and that the red band still sees the bottom.",
                           f"DII {i}/{j}: la correlación sobre el fondo uniforme es {s['r']:.2f} (< {MIN_R}); "
                           "la relación de atenuación no es fiable. Comprueba que el polígono cubre un solo tipo "
                           "de fondo con un rango real de profundidades y que el rojo aún ve el fondo."))
        holes = int((np.isfinite(bands[i]) & np.isfinite(bands[j]) & ~(np.isfinite(X[i]) & np.isfinite(X[j]))).sum())
        if holes:
            s["holes"] = holes
            warns.append(L(f"DII {i}/{j}: {holes} water pixels have no value (R <= R_inf and no floor).",
                           f"DII {i}/{j}: {holes} píxeles de agua sin valor (R <= R∞ y sin suelo)."))
        out.append((f"DII_{i}_{j}", X[i] - s["ratio"] * X[j]))
        stats.append(s)
    return out, stats, warns, any_floor
