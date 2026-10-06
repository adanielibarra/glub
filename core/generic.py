"""Any multiband reflectance raster (PlanetScope, drone, other sensors) to the GLUB 4-band GeoTIFF.

The user says which band is blue, green, red and NIR, and how to turn the stored
values into reflectance (reflectance = value x scale + offset; for example 0.0001
and 0 for PlanetScope surface reflectance stored as 0-10000). The raster is
clipped and masked like the Sentinel-2 path (area polygon, NDWI water mask), and
written as 1 blue, 2 green, 3 red, 4 NIR, float32, nodata -9999, at its own pixel
size. NIR is needed: the water mask and the sunglint correction use it.

Clouds are not masked (there is no standard cloud layer for an arbitrary raster):
remove them before, or draw the area polygon around them.
"""
import os

import numpy as np
from osgeo import gdal

from .lang import L
from .s2safe import NODATA, _window, polygon_mask, strip_rows

gdal.UseExceptions()
KEYS = ("blue", "green", "red", "nir")


class GenericError(Exception):
    pass


def crs_wkt(path):
    return gdal.Open(path).GetProjection()


def prepare(path, out_tif, bands, scale=1.0, offset=0.0, nodata=None, bounds=None, aoi_wkt=None,
            water_mask=True, ndwi_threshold=0.0, log=print):
    """bands: {'blue': b, 'green': b, 'red': b, 'nir': b} (1-based). nodata: value of the source that means
    no data (default: the one stored in the raster)."""
    src = gdal.Open(path)
    nb = src.RasterCount
    for k in KEYS:
        b = bands.get(k)
        if not b or b < 1 or b > nb:
            raise GenericError(L(f"Band for {k} missing or out of range (the raster has {nb} bands).",
                                 f"Falta la banda de {k} o no existe (el ráster tiene {nb} bandas)."))
    if not src.GetProjection():
        raise GenericError(L("The raster has no coordinate reference system.",
                             "El ráster no tiene sistema de referencia."))
    gt = src.GetGeoTransform()
    if gt[2] != 0 or gt[4] != 0:
        raise GenericError(L("Rotated rasters are not supported.", "No se admiten rásteres girados."))
    try:
        c0, r0, w, h = _window(gt, src.RasterXSize, src.RasterYSize, bounds)
    except Exception:
        raise GenericError(L("The extent does not overlap the raster.", "La extensión no se solapa con el ráster."))
    if bounds is None:   # _window drops an odd last row/column for Sentinel-2; keep the whole raster here
        w, h = src.RasterXSize, src.RasterYSize
    out_gt = (gt[0] + c0 * gt[1], gt[1], 0.0, gt[3] + r0 * gt[5], 0.0, gt[5])
    proj = src.GetProjection()
    rb = [src.GetRasterBand(bands[k]) for k in KEYS]
    nd = [nodata if nodata is not None else b.GetNoDataValue() for b in rb]
    out = gdal.GetDriverByName("GTiff").Create(
        out_tif, w, h, 4, gdal.GDT_Float32,
        options=["COMPRESS=DEFLATE", "TILED=YES", "PREDICTOR=3", "BIGTIFF=IF_SAFER"])
    out.SetGeoTransform(out_gt)
    out.SetProjection(proj)
    for i, k in enumerate(KEYS, start=1):
        out.GetRasterBand(i).SetNoDataValue(NODATA)
        out.GetRasterBand(i).SetDescription(f"{k} (band {bands[k]})")
    out.SetMetadataItem("SOURCE", os.path.basename(path))
    out.SetMetadataItem("GLUB_SENSOR", "generic")
    rows = strip_rows(w, rb[0].GetBlockSize()[1])
    n_total = n_outside = n_inside = n_land = n_valid = 0
    medians = []
    for rr in range(0, h, rows):
        nr = min(rows, h - rr)
        stack = []
        for band, ndv in zip(rb, nd):
            v = band.ReadAsArray(c0, r0 + rr, w, nr).astype(np.float64)
            bad = ~np.isfinite(v)
            if ndv is not None and np.isfinite(ndv):
                bad |= v == ndv
            refl = (v * scale + offset).astype(np.float32)
            refl[bad] = np.nan
            stack.append(refl)
        stack = np.stack(stack)
        valid = np.all(np.isfinite(stack), axis=0)
        n_total += int(valid.sum())
        if valid.any() and len(medians) < 20:
            medians.append(float(np.median(stack[1][valid])))
        if aoi_wkt:
            sgt = (out_gt[0], out_gt[1], 0.0, out_gt[3] + rr * out_gt[5], 0.0, out_gt[5])
            inside = polygon_mask(aoi_wkt, sgt, w, nr, proj)
            n_outside += int((valid & ~inside).sum())
            valid &= inside
            n_inside += int(valid.sum())
        if water_mask:
            g, nir = stack[1], stack[3]
            with np.errstate(invalid="ignore", divide="ignore"):
                ndwi = (g - nir) / (g + nir)
            land = ~(ndwi > ndwi_threshold) & valid
            n_land += int(land.sum())
            valid &= ~land
        n_valid += int(valid.sum())
        stack[:, ~valid] = NODATA
        stack[~np.isfinite(stack)] = NODATA
        for i in range(4):
            out.GetRasterBand(i + 1).WriteArray(stack[i], 0, rr)
    out.FlushCache()
    out = None
    if aoi_wkt and n_inside == 0:
        gdal.GetDriverByName("GTiff").Delete(out_tif)
        raise GenericError(L("The area polygon does not cover any valid pixel of the raster.",
                             "El polígono no cubre ningún píxel válido del ráster."))
    med = float(np.median(medians)) if medians else float("nan")
    if np.isfinite(med) and (med > 1.5 or med < -0.05):
        log(L(f"The green band has a median of {med:.3g} after scaling: that does not look like reflectance "
              "(0-1). Check the scale factor and offset.",
              f"La banda verde tiene una mediana de {med:.3g} tras escalar: no parece reflectancia (0-1). Revisa "
              "el factor de escala y el desplazamiento."), True)
    return {"pixels": n_total, "outside_area": n_outside, "masked_cloud": 0, "masked_land": n_land,
            "valid_water": n_valid, "green_median": med}
