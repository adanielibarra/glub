"""Class map (or change map) to polygons with class name and area. GDAL/OGR + numpy.

Each patch of 4-connected pixels of one code becomes a polygon (GDAL Polygonize),
so the outlines follow the pixel edges: they are the map as it is, not smoothed.
Fields: code, class, area_ha (or area in map units if the CRS is not projected),
perimeter_m. By default only class codes (1..249) are exported; the mask zones
(bottom not visible, too deep, low confidence, not comparable) can be added.
Use the filtered map (minimum mapping unit) if you do not want one polygon per
stray pixel.
"""
import os

import numpy as np
from osgeo import gdal, ogr, osr

from . import sampling
from .lang import L

gdal.UseExceptions()


def polygonize(class_path, out_gpkg, include_mask=False, log=print):
    """Write a GeoPackage layer 'classes'. Returns a dict with the number of polygons and the area by class."""
    _grid, counts, names = sampling.read_strata(class_path)
    src = gdal.Open(class_path)
    band = src.GetRasterBand(1)
    srs = osr.SpatialReference()
    srs.ImportFromWkt(src.GetProjection())
    projected = bool(srs.IsProjected())
    unit = srs.GetLinearUnits() if projected else 1.0
    # mask: which codes become polygons
    keep = [c for c in range(1, sampling.MAX_CLASS + 1) if counts[c] > 0]
    if include_mask:
        keep += [c for c in range(sampling.MAX_CLASS + 1, 255) if counts[c] > 0]
    mem = gdal.GetDriverByName("MEM").Create("", src.RasterXSize, src.RasterYSize, 1, gdal.GDT_Byte)
    mem.SetGeoTransform(src.GetGeoTransform())
    mem.SetProjection(src.GetProjection())
    mb = mem.GetRasterBand(1)
    lut = np.zeros(256, np.uint8)
    lut[keep] = 1
    rows = max(1, 4_000_000 // max(src.RasterXSize, 1))
    for r0 in range(0, src.RasterYSize, rows):
        nr = min(rows, src.RasterYSize - r0)
        mb.WriteArray(lut[band.ReadAsArray(0, r0, src.RasterXSize, nr)], 0, r0)
    drv = ogr.GetDriverByName("GPKG")
    if os.path.exists(out_gpkg):
        drv.DeleteDataSource(out_gpkg)
    ds = drv.CreateDataSource(out_gpkg)
    lyr = ds.CreateLayer("classes", srs, ogr.wkbPolygon)
    lyr.CreateField(ogr.FieldDefn("code", ogr.OFTInteger))
    gdal.Polygonize(band, mb, lyr, 0, [], callback=None)
    for name, typ in (("class", ogr.OFTString), ("area_ha" if projected else "area", ogr.OFTReal),
                      ("perimeter_m" if projected else "perimeter", ogr.OFTReal)):
        lyr.CreateField(ogr.FieldDefn(name, typ))
    area_by = {}
    n = 0
    ds.StartTransaction()
    for f in lyr:
        code = f.GetField("code")
        g = f.GetGeometryRef()
        nm = sampling.stratum_name(code, names)
        a = g.GetArea() * unit * unit
        p = g.Boundary().Length() * unit
        f.SetField("class", nm)
        if projected:
            f.SetField("area_ha", round(a / 1e4, 4))
            f.SetField("perimeter_m", round(p, 2))
        else:
            f.SetField("area", a)
            f.SetField("perimeter", p)
        lyr.SetFeature(f)
        area_by[nm] = area_by.get(nm, 0.0) + (a / 1e4 if projected else a)
        n += 1
    ds.CommitTransaction()
    ds = None
    log(L(f"{n} polygons written to {os.path.basename(out_gpkg)}.", f"{n} polígonos escritos en {os.path.basename(out_gpkg)}."))
    return {"path": out_gpkg, "n": n, "area_by_class": area_by, "projected": projected}
