"""Import ACOLITE outputs into the GLUB 4-band reflectance GeoTIFF.

ACOLITE (Vanhellemont, RBINS; GPL-3) writes its L2R and L2W products as NetCDF
with CF georeferencing (x/y variables and a grid_mapping), which GDAL reads as
subdatasets. Reflectance variables are named after the rounded band wavelength,
e.g. rhos_492, sometimes with the band or detector in front (rhos_B2_492).
Optionally ACOLITE also exports one GeoTIFF per variable: <name>_rhos_492.tif.

For each target band the variable with the nearest wavelength (within TOLERANCE)
is used, so the same code works for Sentinel-2A, 2B and 2C.

Output bands: 1 blue, 2 green, 3 red, 4 NIR (descriptions B02, B03, B04, B08 to
match the Sen2Cor path), float32, nodata -9999.
"""
import glob
import os
import re

import numpy as np
from osgeo import gdal

from .s2safe import NODATA, _window, polygon_mask, strip_rows

gdal.UseExceptions()

QUANTITIES = ("rhos", "rhow", "Rrs")
TARGETS = {"blue": 490, "green": 560, "red": 665, "nir": 842}
TOLERANCE = 30  # nm
DESC = {"blue": "B02", "green": "B03", "red": "B04", "nir": "B08"}
_VAR = re.compile(r"^(rhos|rhow|Rrs)_(?:[A-Za-z0-9]+_)?(\d{3,4})$")


class AcoliteError(Exception):
    pass


def list_variables(path, quantity="rhos"):
    """{variable name: (wavelength nm, GDAL path)} for one quantity."""
    out = {}
    low = path.lower()
    if low.endswith(".nc"):
        ds = gdal.Open(path)
        for sub, _desc in ds.GetSubDatasets():
            var = sub.split(":")[-1]
            m = _VAR.match(var)
            if m and m.group(1) == quantity:
                out[var] = (int(m.group(2)), sub)
        ds = None
    elif low.endswith((".tif", ".tiff")):
        m = re.search(r"^(.*)_(rhos|rhow|Rrs)_(?:[A-Za-z0-9]+_)?\d{3,4}\.tiff?$", os.path.basename(path))
        if not m:
            raise AcoliteError("The GeoTIFF name does not look like an ACOLITE export (..._rhos_492.tif).")
        prefix = os.path.join(os.path.dirname(path), m.group(1))
        for f in glob.glob(glob.escape(prefix) + f"_{quantity}_*.tif*"):
            var = os.path.splitext(os.path.basename(f))[0][len(m.group(1)) + 1:]
            mm = _VAR.match(var)
            if mm and mm.group(1) == quantity:
                out[var] = (int(mm.group(2)), f)
    else:
        raise AcoliteError("Give an ACOLITE NetCDF (.nc) or one of its exported GeoTIFFs (.tif).")
    return out


def pick(variables):
    """Nearest variable to each target wavelength. Returns {band: (var, wave, path)}."""
    chosen = {}
    for band, target in TARGETS.items():
        best = min(variables.items(), key=lambda kv: abs(kv[1][0] - target), default=None)
        if best is None or abs(best[1][0] - target) > TOLERANCE:
            waves = sorted(v[0] for v in variables.values())
            raise AcoliteError(f"No {band} band within {TOLERANCE} nm of {target} nm "
                               f"(available: {waves or 'none'}).")
        chosen[band] = (best[0], best[1][0], best[1][1])
    return chosen


def _open(path):
    ds = gdal.Open(path)
    gt = ds.GetGeoTransform(can_return_null=True)
    if gt is None or gt == (0.0, 1.0, 0.0, 0.0, 0.0, 1.0) or not ds.GetProjection():
        raise AcoliteError(
            "This ACOLITE output has no map georeferencing (it may be in swath geometry). Process it "
            "with a map projection (the default for Sentinel-2) or export GeoTIFFs with "
            "l2r_export_geotiff=True.")
    return ds, gt


def crs_wkt(path, quantity="rhos"):
    chosen = pick(list_variables(path, quantity))
    ds, _gt = _open(chosen["blue"][2])
    return ds.GetProjection()


def import_acolite(path, out_tif, quantity="rhos", bounds=None, aoi_wkt=None, water_mask=True,
                   ndwi_threshold=0.0, log=print):
    """Write the 4-band GeoTIFF. bounds and aoi_wkt in the raster CRS. Returns stats."""
    if quantity not in QUANTITIES:
        raise AcoliteError(f"Unknown quantity {quantity}; use one of {QUANTITIES}.")
    variables = list_variables(path, quantity)
    if not variables:
        others = [q for q in QUANTITIES if q != quantity and list_variables(path, q)]
        raise AcoliteError(f"No {quantity}_* variables in this file"
                           + (f"; it has {', '.join(others)}." if others else "."))
    chosen = pick(variables)
    for band in TARGETS:
        var, wave, _p = chosen[band]
        log(f"{band}: {var} ({wave} nm)")

    ref, gt = _open(chosen["blue"][2])
    size = (ref.RasterXSize, ref.RasterYSize)
    c0, r0, w, h = _window(gt, size[0], size[1], bounds)
    srcs = []
    for band in TARGETS:
        ds, g2 = _open(chosen[band][2])
        if (ds.RasterXSize, ds.RasterYSize) != size or any(abs(a - b) > 1e-6 for a, b in zip(g2, gt)):
            raise AcoliteError(f"The {band} variable is on a different grid from blue.")
        srcs.append(ds)
    rbands = [ds.GetRasterBand(1) for ds in srcs]
    out_gt = (gt[0] + c0 * gt[1], gt[1], 0.0, gt[3] + r0 * gt[5], 0.0, gt[5])
    proj = ref.GetProjection()
    o = gdal.GetDriverByName("GTiff").Create(out_tif, w, h, 4, gdal.GDT_Float32,
                                             options=["COMPRESS=DEFLATE", "TILED=YES", "PREDICTOR=3",
                                                      "BIGTIFF=IF_SAFER"])
    o.SetGeoTransform(out_gt)
    o.SetProjection(proj)
    o.SetMetadataItem("SOURCE", os.path.basename(path))
    o.SetMetadataItem("ATMOSPHERIC_CORRECTION", "ACOLITE")
    o.SetMetadataItem("ACOLITE_QUANTITY", quantity)
    o.SetMetadataItem("ACOLITE_VARIABLES", ",".join(chosen[b][0] for b in TARGETS))
    for i, band in enumerate(TARGETS, start=1):
        o.GetRasterBand(i).SetNoDataValue(NODATA)
        o.GetRasterBand(i).SetDescription(DESC[band])

    rows = strip_rows(w, rbands[0].GetBlockSize()[1])
    n_total = n_outside = n_land = n_valid = 0
    for rr in range(0, h, rows):
        nr = min(rows, h - rr)
        stack = []
        for b in rbands:
            a = b.ReadAsArray(c0, r0 + rr, w, nr).astype(np.float32)
            nd = b.GetNoDataValue()
            if nd is not None:
                a[a == nd] = np.nan
            a[(a < -1) | (a > 10)] = np.nan  # fill values that GDAL does not flag
            stack.append(a)
        stack = np.stack(stack)
        valid = np.all(np.isfinite(stack), axis=0)
        n_total += int(valid.sum())
        if aoi_wkt:
            sgt = (out_gt[0], out_gt[1], 0.0, out_gt[3] + rr * out_gt[5], 0.0, out_gt[5])
            inside = polygon_mask(aoi_wkt, sgt, w, nr, proj)
            n_outside += int((valid & ~inside).sum())
            valid &= inside
        if water_mask:
            g, nir = stack[1], stack[3]
            with np.errstate(invalid="ignore", divide="ignore"):
                ndwi = (g - nir) / (g + nir)
            land = ~(ndwi > ndwi_threshold) & valid
            n_land += int(land.sum())
            valid &= ~land
        n_valid += int(valid.sum())
        stack[:, ~valid] = NODATA
        for i in range(4):
            o.GetRasterBand(i + 1).WriteArray(stack[i], 0, rr)
    o.FlushCache()
    o = None
    if n_valid == 0:
        gdal.GetDriverByName("GTiff").Delete(out_tif)
        raise AcoliteError("No valid water pixel left in the area.")
    return {"pixels": n_total, "outside_area": n_outside, "masked_land": n_land,
            "valid_water": n_valid, "variables": {b: chosen[b][:2] for b in TARGETS}}
