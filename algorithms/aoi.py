"""Area of interest and point helpers shared by the algorithms and the window."""
from qgis.core import (QgsCoordinateTransform, QgsGeometry,
                       QgsProcessingException, QgsRectangle)


def union_features(features, src_crs, dest_crs, transform_context):
    """Dissolve polygon features into one geometry in dest_crs (or None if empty)."""
    xform = QgsCoordinateTransform(src_crs, dest_crs, transform_context)
    geoms = []
    for f in features:
        g = f.geometry()
        if g.isNull() or g.isEmpty():
            continue
        g = QgsGeometry(g)
        g.transform(xform)
        if not g.isGeosValid():
            g = g.makeValid()
        geoms.append(g)
    if not geoms:
        return None, 0
    u = QgsGeometry.unaryUnion(geoms)
    return (None if u.isNull() or u.isEmpty() else u), len(geoms)


def union_geometry(source, dest_crs, context, feedback=None):
    """Processing wrapper: dissolve all (or the selected) polygons of a source."""
    u, n = union_features(source.getFeatures(), source.sourceCrs(), dest_crs,
                          context.transformContext())
    if u is None:
        raise QgsProcessingException("The area layer has no usable polygons.")
    if feedback:
        feedback.pushInfo(f"Area: {n} polygon(s) dissolved into one.")
    return u


def combine(extent, geom):
    """Final bounding box from an optional extent and an optional geometry."""
    box = None
    if extent is not None and not extent.isNull() and not extent.isEmpty():
        box = QgsRectangle(extent)
    if geom is not None:
        gb = geom.boundingBox()
        box = gb if box is None else box.intersect(gb)
        if box.isEmpty():
            raise QgsProcessingException("The extent and the area polygon do not overlap.")
    return box


def read_points(features, src_crs, dest_crs, transform_context, field, sign=1.0, tide=0.0,
                tide_field=None):
    """Point coordinates in dest_crs and depths (sign applied, plus water level).

    The water level comes from tide_field for each point when given and valid,
    otherwise from the constant tide. Returns (xs, ys, depths, skipped, tide_fallback).
    """
    xform = QgsCoordinateTransform(src_crs, dest_crs, transform_context)
    xs, ys, depths, skipped, fallback = [], [], [], 0, 0
    for f in features:
        g = f.geometry()
        if g.isNull() or g.isEmpty():
            skipped += 1
            continue
        pt = g.asMultiPoint()[0] if g.isMultipart() else g.asPoint()
        try:
            v = float(f[field])
        except (TypeError, ValueError, KeyError):
            skipped += 1
            continue
        level = tide
        if tide_field:
            try:
                level = float(f[tide_field])
                if level != level:  # NaN
                    raise ValueError
            except (TypeError, ValueError, KeyError):
                level = tide
                fallback += 1
        p = xform.transform(pt)
        xs.append(p.x())
        ys.append(p.y())
        depths.append(sign * v + level)
    return xs, ys, depths, skipped, fallback


def read_training(features, src_crs, is_point, dest_crs, transform_context, field):
    """Reference data in dest_crs: {'kind': 'points', xs, ys, labels} or
    {'kind': 'polygons', wkts, labels}. Class values become text (12.0 -> '12').
    Returns (training dict, skipped count)."""
    xform = QgsCoordinateTransform(src_crs, dest_crs, transform_context)
    xs, ys, wkts, labels, skipped = [], [], [], [], 0
    for f in features:
        g = f.geometry()
        try:
            val = f[field]
        except KeyError:
            val = None
        if g is None or g.isNull() or g.isEmpty() or val is None or str(val).strip() in ("", "NULL"):
            skipped += 1
            continue
        g = QgsGeometry(g)
        g.transform(xform)
        lab = str(int(val)) if isinstance(val, float) and val.is_integer() else str(val).strip()
        if is_point:
            pts = g.asMultiPoint() if g.isMultipart() else [g.asPoint()]
            for p in pts:
                xs.append(p.x())
                ys.append(p.y())
                labels.append(lab)
        else:
            if not g.isGeosValid():
                g = g.makeValid()
            wkts.append(g.asWkt())
            labels.append(lab)
    if is_point:
        return {"kind": "points", "xs": xs, "ys": ys, "labels": labels}, skipped
    return {"kind": "polygons", "wkts": wkts, "labels": labels}, skipped


def set_core_lang():
    """Processing tools write their log and report in the language chosen in the GLUB window."""
    from ..core import lang
    try:
        from qgis.core import QgsSettings
        lang.set_lang(QgsSettings().value("GLUB/lang", "es"))
    except Exception:
        lang.set_lang("es")
