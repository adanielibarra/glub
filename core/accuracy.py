"""Classification accuracy. numpy only.

Confusion matrix convention: rows = map (predicted) class, columns = reference
class, as in Olofsson et al. (2014). User's accuracy (UA) is per row (how often
a map label is right), producer's accuracy (PA) per column (how much of the
reference class the map finds). Kappa is not reported: it adds nothing to
overall accuracy and is misleading (Pontius and Millones, 2011).

Area-adjusted estimates (Olofsson et al., 2014): the pixel count of each map
class weights the rows, which corrects the mapped areas for the errors seen in
the reference sample and gives a 95 % interval. They are strictly valid only
for a probability sample (e.g. stratified random by map class). Field points
collected where it was convenient are not one, so with them the estimates are
indicative. The report says so.
"""
import numpy as np


def confusion(ref, pred, k):
    """k x k integer matrix, rows = map (pred), columns = reference; labels are 0..k-1."""
    m = np.zeros((k, k), dtype=np.int64)
    np.add.at(m, (np.asarray(pred, dtype=np.int64), np.asarray(ref, dtype=np.int64)), 1)
    return m


def _div(a, b):
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(b > 0, a / np.where(b > 0, b, 1), np.nan)


def summary(m):
    m = np.asarray(m, dtype=np.float64)
    d = np.diag(m)
    rows, cols, n = m.sum(1), m.sum(0), m.sum()
    ua, pa = _div(d, rows), _div(d, cols)
    f1 = _div(2 * ua * pa, ua + pa)
    return {"n": int(n), "oa": float(d.sum() / n) if n else np.nan,
            "ua": ua, "pa": pa, "f1": f1, "n_ref": cols.astype(int), "n_map": rows.astype(int)}


def area_adjusted(m, map_pixels, pixel_area=1.0, z=1.96, k=None):
    """Olofsson et al. (2014) stratified estimators.

    m: confusion matrix of the reference sample, rows = map strata, columns =
       reference classes. The first k rows are the map classes (same order as the
       columns); extra rows are strata without a class of their own (e.g. the
       low-confidence zone), whose samples spread their area among the classes.
       Extra columns (after the first k) are reference classes that the map never
       gives (all of their area comes from errors).
    k: number of map classes (default: the smaller side of m).
    map_pixels: pixels of each map stratum (one per row).
    Returns dict with area (same units as pixel_area) and its half 95 % interval
    per reference class, plus adjusted OA, UA and PA (UA for the class rows only).
    """
    m = np.asarray(m, dtype=np.float64)
    npx = np.asarray(map_pixels, dtype=np.float64)
    total = npx.sum()
    kr, kc = m.shape
    k = min(kr, kc) if k is None else k
    W = npx / total if total else np.zeros(kr)
    ni = m.sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        pij = np.where(ni[:, None] > 0, W[:, None] * m / np.where(ni[:, None] > 0, ni[:, None], 1), 0.0)
    pj = pij.sum(0)  # estimated area proportion of each reference class
    se = np.zeros(kc)
    for j in range(kc):
        acc = 0.0
        for i in range(kr):
            if ni[i] > 1:
                f = m[i, j] / ni[i]
                acc += W[i] ** 2 * f * (1 - f) / (ni[i] - 1)
        se[j] = np.sqrt(acc)
    sq = pij[:k, :k]
    oa = float(np.trace(sq))
    ua = _div(np.diag(sq), pij[:k].sum(1))   # all reference columns, extra ones too
    pa = _div(np.concatenate([np.diag(sq), np.zeros(kc - k)]), pj)
    missing = [i for i in range(kr) if ni[i] == 0 and npx[i] > 0]
    return {"prop": pj, "area": pj * total * pixel_area, "ci": z * se * total * pixel_area,
            "mapped": npx[:k] * pixel_area, "oa": oa, "ua": ua, "pa": pa, "rows_without_sample": missing}


def by_bins(ref, pred, values, edges):
    """Overall accuracy of the sample split by ranges of values (e.g. depth)."""
    ref, pred, values = map(np.asarray, (ref, pred, values))
    rows = []
    edges = list(edges)
    bounds = list(zip(edges[:-1], edges[1:])) + [(edges[-1], np.inf)]
    with np.errstate(invalid="ignore"):
        if np.any(np.asarray(values, dtype=float) < edges[0]):   # e.g. negative depths (above datum)
            bounds = [(-np.inf, edges[0])] + bounds
    for lo, hi in bounds:
        with np.errstate(invalid="ignore"):
            sel = (values >= lo) & (values < hi)
        n = int(sel.sum())
        rng = f"{lo:g}-{hi:g}" if np.isfinite(lo) and np.isfinite(hi) else f">={lo:g}" if np.isfinite(lo) else f"<{hi:g}"
        rows.append({"range": rng, "n": n,
                     "oa": float((ref[sel] == pred[sel]).mean()) if n else np.nan})
    unknown = int((~np.isfinite(values.astype(float))).sum())
    if unknown:
        rows.append({"range": "no depth", "n": unknown,
                     "oa": float((ref[~np.isfinite(values.astype(float))] ==
                                  pred[~np.isfinite(values.astype(float))]).mean())})
    return rows


def by_groups(ref, pred, groups, k):
    """Accuracy with one vote per group (polygon): the majority class of its pixels.
    A tie between classes counts as an error (it is not a clear answer), and so does a
    polygon whose pixels are mostly 'unsure' (label k, below the minimum probability).
    Returns dict with n (groups), oa, ties, confusion matrix of the resolved groups and summary."""
    ref, pred, groups = map(np.asarray, (ref, pred, groups))
    g_ref, g_pred, ties, unsure = [], [], 0, 0
    for g in np.unique(groups):
        sel = groups == g
        counts = np.bincount(pred[sel], minlength=k)
        top = np.flatnonzero(counts == counts.max())
        r = np.bincount(ref[sel], minlength=k).argmax()
        g_ref.append(r)
        if len(top) > 1:
            ties += 1
            g_pred.append(-1)
        elif top[0] >= k:  # the majority of its pixels are 'unsure': not a clear answer
            unsure += 1
            g_pred.append(-1)
        else:
            g_pred.append(int(top[0]))
    g_ref, g_pred = np.array(g_ref), np.array(g_pred)
    ok = g_pred >= 0
    cm = confusion(g_ref[ok], g_pred[ok], k)
    s = summary(cm)
    n = len(g_ref)
    return {"n": n, "oa": float((g_ref == g_pred).sum() / n) if n else np.nan, "ties": ties, "unsure": unsure,
            "cm": cm,
            "summary": s, "n_ref": np.bincount(g_ref, minlength=k)}
