"""Supervised benthic classification on numpy arrays, independent of QGIS.

Training data: points or polygons with a class label. A polygon gives several
pixels, all from the same place, so the pixels of one polygon always stay
together in calibration or in validation (a "group"). A point is its own group.

Split: spatial blocks by class. For every class, whole blocks of its groups go
to validation until the wanted fraction of that class is reached. This keeps
every class in both sets and keeps neighbouring samples of the same class apart.
Samples of different classes that share a block can fall on different sides;
that leaks less than a random split but is not a full spatial separation.

Classifiers:
  rf  Random Forest (scikit-learn)
  ml  Gaussian maximum likelihood (numpy only)

Class balance (one switch for both): off by default. Off, the model follows the
class proportions of the training sample (RF without weights, ML with priors from
the sample counts). On, every class weighs the same (RF class_weight='balanced',
ML equal priors): rare classes are found more often (higher producer's accuracy)
but their mapped area grows. Neither choice is neutral: without balance the map
inherits the proportions of the sample, so a class sampled more than it occurs
also gets inflated. That is why the report gives error-corrected areas.
"""
import numpy as np
from .lang import L


METHODS = {"rf": "Random Forest", "ml": "Maximum likelihood (Gaussian)"}


# ---------------------------------------------------------------- sampling
def pixel_index(gt, xs, ys):
    cols = np.floor((np.asarray(xs, dtype=np.float64) - gt[0]) / gt[1]).astype(np.int64)
    rows = np.floor((np.asarray(ys, dtype=np.float64) - gt[3]) / gt[5]).astype(np.int64)
    return rows, cols


def points_to_samples(xs, ys, labels, gt, shape):
    """Pixels under points. Duplicates in one pixel with the same label are kept once;
    pixels with conflicting labels are dropped. Returns rows, cols, labels, groups, info."""
    h, w = shape
    rows, cols = pixel_index(gt, xs, ys)
    labels = np.asarray(labels, dtype=object)
    inside = (rows >= 0) & (cols >= 0) & (rows < h) & (cols < w)
    info = {"outside": int((~inside).sum()), "duplicates": 0, "conflicts": 0}
    rows, cols, labels = rows[inside], cols[inside], labels[inside]
    seen = {}
    for i, (r, c, lab) in enumerate(zip(rows, cols, labels)):
        seen.setdefault((int(r), int(c)), []).append((i, lab))
    keep = []
    for items in seen.values():
        labs = {lab for _, lab in items}
        if len(labs) > 1:
            info["conflicts"] += len(items)
            continue
        info["duplicates"] += len(items) - 1
        keep.append(items[0][0])
    keep = np.array(sorted(keep), dtype=np.int64)
    groups = np.arange(len(keep))
    return rows[keep], cols[keep], labels[keep], groups, info


def shrink(wkts, distance):
    """Negative buffer of each polygon (distance in CRS units). Polygons that vanish
    become None. Returns (list of WKT or None, number vanished)."""
    from osgeo import ogr
    out, gone = [], 0
    for wkt in wkts:
        g = ogr.CreateGeometryFromWkt(wkt)
        if g is None:
            out.append(wkt)
            continue
        s = g.Buffer(-abs(distance))
        if s is None or s.IsEmpty() or s.GetArea() <= 0:
            out.append(None)
            gone += 1
        else:
            out.append(s.ExportToWkt())
    return out, gone


def polygons_to_samples(wkts, labels, gt, shape, proj, max_per_polygon=200, seed=42):
    """Pixels whose centre falls inside each polygon (the later polygon wins on overlaps).
    At most max_per_polygon random pixels per polygon (0 = all). Each polygon is
    rasterized over its own window only, so memory does not grow with the raster.
    A None in wkts (a polygon that vanished when shrunk) gives no pixels."""
    from .blockio import Grid, rasterize_window, window_of
    h, w = shape
    grid = Grid(gt, proj, w, h)
    rng = np.random.default_rng(seed)
    per = []
    bad = 0
    for k, wkt in enumerate(wkts):
        if wkt is None:
            per.append(None)
            continue
        try:
            win = window_of(wkt, grid)
        except ValueError:
            bad += 1
            per.append(None)
            continue
        if win is None:
            per.append(None)
            continue
        m = rasterize_window(wkt, grid, win)
        r, cc = np.nonzero(m)
        per.append((r + win[0], cc + win[2]))
    # overlaps: a pixel belongs to the last polygon that contains it
    owner = {}
    for k, rc in enumerate(per):
        if rc is None:
            continue
        for key in (rc[0].astype(np.int64) * w + rc[1]).tolist():
            owner[key] = k
    rows, cols, labs, groups = [], [], [], []
    empty, capped = 0, 0
    for k, (rc, lab) in enumerate(zip(per, labels)):
        if rc is None:
            empty += 1
            continue
        keys = rc[0].astype(np.int64) * w + rc[1]
        own = np.array([owner[key] == k for key in keys.tolist()], dtype=bool)
        r, cc = rc[0][own], rc[1][own]
        if len(r) == 0:
            empty += 1
            continue
        if max_per_polygon and len(r) > max_per_polygon:
            sel = rng.choice(len(r), max_per_polygon, replace=False)
            r, cc = r[sel], cc[sel]
            capped += 1
        rows.append(r)
        cols.append(cc)
        labs += [lab] * len(r)
        groups.append(np.full(len(r), k))
    info = {"invalid": bad, "empty": empty - bad, "capped": capped}
    if not rows:
        return (np.array([], dtype=np.int64),) * 2 + (np.array([], dtype=object), np.array([], dtype=np.int64), info)
    return (np.concatenate(rows), np.concatenate(cols), np.array(labs, dtype=object),
            np.concatenate(groups), info)


# ---------------------------------------------------------------- split
def split_by_class_blocks(xs, ys, y, groups, block_size, val_fraction=0.3, seed=42, random=False):
    """Validation mask. Unit = group (a polygon or a point). With random=True the
    groups are shuffled without blocks. Returns (val mask, list of warnings)."""
    xs, ys, y, groups = map(np.asarray, (xs, ys, y, groups))
    rng = np.random.default_rng(seed)
    val = np.zeros(len(y), dtype=bool)
    warns = []
    for cls in np.unique(y):
        sel = np.nonzero(y == cls)[0]
        g_ids, g_inv = np.unique(groups[sel], return_inverse=True)
        g_n = np.bincount(g_inv)
        gx = np.bincount(g_inv, weights=xs[sel]) / g_n
        gy = np.bincount(g_inv, weights=ys[sel]) / g_n
        if random:
            unit = np.arange(len(g_ids))
        else:
            bx = np.floor(gx / block_size).astype(np.int64)
            by = np.floor(gy / block_size).astype(np.int64)
            _, unit = np.unique(bx * 10_000_019 + by, return_inverse=True)
        u_n = np.bincount(unit, weights=g_n)
        if len(u_n) < 2:
            warns.append(L(f"Class {cls}: all its samples fall in one {'group' if random else 'block'}; it cannot "
                           "be validated independently and is used only for calibration.",
                           f"Clase {cls}: todas sus muestras caen en un solo {'objeto' if random else 'bloque'}; "
                           "no se puede validar de forma independiente y solo se usa para calibrar."))
            continue
        target = val_fraction * len(sel)
        chosen, acc = [], 0.0
        for u in rng.permutation(len(u_n)):
            if acc >= target:
                break
            if acc + u_n[u] >= len(sel):  # never the whole class
                continue
            chosen.append(u)
            acc += u_n[u]
        if not chosen:
            warns.append(L(f"Class {cls}: could not set aside validation samples without taking the whole class.",
                           f"Clase {cls}: no se pudieron apartar muestras de validación sin llevarse la clase "
                           "entera."))
            continue
        val_groups = g_ids[np.isin(unit, chosen)]
        val[sel[np.isin(groups[sel], val_groups)]] = True
        frac = acc / len(sel)
        if abs(frac - val_fraction) > 0.2:
            warns.append(L(f"Class {cls}: validation got {100 * frac:.0f} % of its samples (asked "
                           f"{100 * val_fraction:.0f} %); blocks are too big for this class.",
                           f"Clase {cls}: la validación se quedó con el {100 * frac:.0f} % de sus muestras (se "
                           f"pidió el {100 * val_fraction:.0f} %); los bloques son demasiado grandes para esta clase."))
    return val, warns


def split_common_blocks(xs, ys, y, groups, block_size, val_fraction=0.3, seed=42, tries=200):
    """Full spatial separation: the same blocks for every class. A block goes whole to
    validation or to calibration, whatever the classes inside. Several random block
    orders are tried and the one that keeps every class on both sides, closest to
    val_fraction for every class, is kept. Returns (val mask, warnings)."""
    xs, ys, y, groups = map(np.asarray, (xs, ys, y, groups))
    g_ids, g_inv = np.unique(groups, return_inverse=True)
    g_n = np.bincount(g_inv)
    gx = np.bincount(g_inv, weights=xs) / g_n
    gy = np.bincount(g_inv, weights=ys) / g_n
    bx = np.floor(gx / block_size).astype(np.int64)
    by = np.floor(gy / block_size).astype(np.int64)
    _, g_block = np.unique(bx * 10_000_019 + by, return_inverse=True)
    s_block = g_block[g_inv]                       # block of each sample
    nb = int(s_block.max()) + 1
    classes = np.unique(y)
    per_cls = np.stack([np.bincount(s_block[y == c], minlength=nb) for c in classes])  # class x block
    tot_cls = per_cls.sum(1)
    warns = []
    if nb < 2:
        return np.zeros(len(y), bool), [L("All samples fall in one block: use a smaller block size.",
                                          "Todas las muestras caen en un bloque: usa bloques más pequeños.")]
    rng = np.random.default_rng(seed)
    target = val_fraction * len(y)
    best, best_key = None, None
    for _ in range(tries):
        chosen, acc = [], 0
        for b in rng.permutation(nb):
            if acc >= target:
                break
            nbk = per_cls[:, b].sum()
            if acc + nbk >= len(y):
                continue
            chosen.append(b)
            acc += nbk
        vc = per_cls[:, chosen].sum(1)
        both = int(((vc > 0) & (vc < tot_cls)).sum())
        dev = float(np.max(np.abs(vc / tot_cls - val_fraction)))
        key = (-both, dev)
        if best_key is None or key < best_key:
            best, best_key = list(chosen), key
    val = np.isin(s_block, best)
    vc = per_cls[:, best].sum(1)
    for c, v, t in zip(classes, vc, tot_cls):
        if v == 0:
            warns.append(L(f"Class {c}: no block with it went to validation (common blocks); it is not validated.",
                           f"Clase {c}: ningún bloque con ella fue a validación (bloques comunes); no se valida."))
        elif v == t:
            warns.append(L(f"Class {c}: all its blocks went to validation (common blocks); it cannot be calibrated.",
                           f"Clase {c}: todos sus bloques fueron a validación (bloques comunes); no se puede calibrar."))
        elif abs(v / t - val_fraction) > 0.2:
            warns.append(L(f"Class {c}: validation got {100 * v / t:.0f} % of its samples (asked "
                           f"{100 * val_fraction:.0f} %) with common blocks.",
                           f"Clase {c}: la validación se quedó con el {100 * v / t:.0f} % de sus muestras (se "
                           f"pidió el {100 * val_fraction:.0f} %) con bloques comunes."))
    return val, warns


# ---------------------------------------------------------------- models
class GaussianML:
    """Maximum likelihood with one multivariate normal per class.
    Priors: equal (balanced=True) or the class shares of the training sample."""

    def __init__(self, balanced=False):
        self.balanced = balanced

    def fit(self, X, y):
        self.classes_ = np.unique(y)
        counts = np.array([(y == c).sum() for c in self.classes_], dtype=np.float64)
        self.log_prior = (np.zeros(len(counts)) if self.balanced else np.log(counts / counts.sum()))
        d = X.shape[1]
        self.params = []
        for c in self.classes_:
            Xc = X[y == c]
            mu = Xc.mean(0)
            cov = np.cov(Xc, rowvar=False).reshape(d, d) if len(Xc) > 1 else np.eye(d)
            reg = 1e-6 * max(np.trace(cov) / d, 1e-12)
            cov = cov + reg * np.eye(d)
            sign, logdet = np.linalg.slogdet(cov)
            if sign <= 0:
                cov = np.diag(np.maximum(np.diag(cov), reg))
                sign, logdet = np.linalg.slogdet(cov)
            self.params.append((mu, np.linalg.inv(cov), logdet))
        return self

    def log_lik(self, X):
        out = np.empty((len(X), len(self.params)))
        for k, (mu, icov, logdet) in enumerate(self.params):
            D = X - mu
            out[:, k] = -0.5 * (np.einsum("ij,jk,ik->i", D, icov, D) + logdet) + self.log_prior[k]
        return out

    def predict_proba(self, X):
        ll = self.log_lik(X)
        ll -= ll.max(1, keepdims=True)
        p = np.exp(ll)
        return p / p.sum(1, keepdims=True)

    def predict(self, X):
        return self.classes_[np.argmax(self.log_lik(X), 1)]


def make_model(method, trees=300, balanced=False, seed=42):
    if method == "ml":
        return GaussianML(balanced)
    try:
        from sklearn.ensemble import RandomForestClassifier
    except ImportError:
        return None
    return RandomForestClassifier(n_estimators=trees, class_weight="balanced" if balanced else None,
                                  random_state=seed, n_jobs=-1)


def predict_chunks(model, X, chunk=100_000):
    """Class index and probabilities in chunks (memory friendly)."""
    k = len(model.classes_)
    proba = np.empty((len(X), k), dtype=np.float32)
    for s in range(0, len(X), chunk):
        proba[s:s + chunk] = model.predict_proba(X[s:s + chunk])
    return proba
