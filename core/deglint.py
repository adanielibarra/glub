"""Hedley et al. (2005) sunglint correction. numpy only.

For each visible band i, over a sample of optically deep water with varying glint:
    b_i = slope of the regression of R_i against R_NIR
    R'_i = R_i - b_i * (R_NIR - min_NIR)
min_NIR is the minimum NIR in the sample (as in Hedley et al.); a low
percentile can be used instead to be less sensitive to noisy pixels.
"""
import numpy as np
from .lang import L


def fit(vis, nir, sample, nir_percentile=0.0):
    """Returns dict with slope, intercept, r2 per visible band and the NIR reference."""
    nir_s = nir[sample]
    ok_nir = np.isfinite(nir_s)
    if ok_nir.sum() < 50:
        raise ValueError(L(f"Only {int(ok_nir.sum())} valid pixels in the deep-water sample; need at least 50.",
                           f"Solo hay {int(ok_nir.sum())} píxeles válidos en la muestra de agua profunda; hacen "
                           "falta al menos 50."))
    nir_ref = float(np.nanmin(nir_s) if nir_percentile <= 0 else np.nanpercentile(nir_s, nir_percentile))
    out = {"nir_ref": nir_ref, "n": int(ok_nir.sum()), "bands": []}
    for v in vis:
        vs = v[sample]
        ok = np.isfinite(vs) & np.isfinite(nir_s)
        x, y = nir_s[ok], vs[ok]
        if np.ptp(x) == 0:
            raise ValueError(L("NIR is constant in the sample: no glint to model.",
                               "El NIR es constante en la muestra: no hay brillo que modelar."))
        b, a = np.polyfit(x, y, 1)
        r = np.corrcoef(x, y)[0, 1]
        out["bands"].append({"slope": float(b), "intercept": float(a), "r2": float(r * r)})
    return out


def apply(vis, nir, params):
    """Corrected visible bands (list of arrays). NIR itself is not changed."""
    ref = params["nir_ref"]
    return [v - p["slope"] * (nir - ref) for v, p in zip(vis, params["bands"])]
