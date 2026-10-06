"""Enum names that changed across QGIS versions (3.28 to 3.40+, and QGIS 4 with Qt6).

The new scoped enums live in Qgis (LayerFilter since 3.34, GeometryType since
3.30, ProcessingSourceType and ProcessingNumberParameterType since 3.36). Older
QGIS only has the old ones, and QGIS 4 drops the old unscoped names. Every file
takes the constant from here, so one place decides.
"""
from qgis.core import (Qgis, QgsMapLayerProxyModel, QgsProcessing,
                       QgsProcessingParameterNumber, QgsWkbTypes)

_LF = getattr(Qgis, "LayerFilter", None) or QgsMapLayerProxyModel.Filter
POINT_LAYER = _LF.PointLayer
POLYGON_LAYER = _LF.PolygonLayer
RASTER_LAYER = _LF.RasterLayer

_GT = getattr(Qgis, "GeometryType", None)
POINT_GEOMETRY = _GT.Point if _GT is not None else QgsWkbTypes.GeometryType.PointGeometry

_PST = getattr(Qgis, "ProcessingSourceType", None)
if _PST is not None:
    SRC_POINT, SRC_POLYGON, SRC_RASTER = _PST.VectorPoint, _PST.VectorPolygon, _PST.Raster
else:
    SRC_POINT, SRC_POLYGON, SRC_RASTER = (QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorPolygon,
                                          QgsProcessing.TypeRaster)

_PNT = getattr(Qgis, "ProcessingNumberParameterType", None)
if _PNT is not None:
    NUM_DOUBLE, NUM_INTEGER = _PNT.Double, _PNT.Integer
else:
    NUM_DOUBLE, NUM_INTEGER = QgsProcessingParameterNumber.Double, QgsProcessingParameterNumber.Integer




def layer_filters(*filters):
    """Several layer filters combined as the flags type setFilters() expects."""
    flags_cls = getattr(Qgis, "LayerFilters", None) or getattr(QgsMapLayerProxyModel, "Filters", None)
    out = flags_cls(filters[0]) if flags_cls is not None else filters[0]
    for f in filters[1:]:
        out = out | f
    return out
