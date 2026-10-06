"""Read Sentinel-2 L2A SAFE zips and write a clipped, masked reflectance GeoTIFF.

Output bands: 1 = B02 (blue), 2 = B03 (green), 3 = B04 (red), 4 = B08 (NIR),
all as surface reflectance (0-1), float32, nodata = -9999.

Only numpy + GDAL, no QGIS imports.
"""
import math
import os
import re
import zipfile

import numpy as np
from osgeo import gdal, ogr, osr

gdal.UseExceptions()

NODATA = -9999.0
BANDS = ["B02", "B03", "B04", "B08"]
BAND_ID = {"B02": 1, "B03": 2, "B04": 3, "B08": 7}  # band_id in MTD xml
# SCL classes treated as invalid: no data, defective, cloud shadow,
# cloud medium, cloud high, thin cirrus, snow
SCL_INVALID_DEFAULT = (0, 1, 3, 8, 9, 10, 11)


class SafeError(Exception):
    pass


def inspect(zip_path):
    """Find band, SCL and metadata members inside the zip."""
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        if any(n.endswith("MTD_MSIL1C.xml") for n in names):
            raise SafeError(
                "This is an L1C (top of atmosphere) product. The standard path "
                "needs L2A; for L1C, run ACOLITE and choose the ACOLITE output option.")
        mtd = [n for n in names if n.endswith("MTD_MSIL2A.xml")]
        if not mtd:
            raise SafeError("MTD_MSIL2A.xml not found: is this a Sentinel-2 L2A zip?")
        xml = z.read(mtd[0]).decode(errors="replace")

    members = {}
    for b in BANDS:
        pat = re.compile(rf"IMG_DATA/R10m/[^/]*_{b}_10m\.jp2$")
        hits = [n for n in names if pat.search(n)]
        if not hits:
            raise SafeError(f"Band {b} at 10 m not found in the zip.")
        members[b] = hits[0]
    scl = [n for n in names if re.search(r"IMG_DATA/R20m/[^/]*_SCL_20m\.jp2$", n)]
    members["SCL"] = scl[0] if scl else None

    quant = re.search(r"<BOA_QUANTIFICATION_VALUE[^>]*>([\d.]+)<", xml)
    quant = float(quant.group(1)) if quant else 10000.0
    offsets = {int(i): float(v) for i, v in
               re.findall(r'<BOA_ADD_OFFSET band_id="(\d+)">\s*(-?[\d.]+)\s*<', xml)}
    return {"members": members, "quant": quant,
            "offsets": {b: offsets.get(BAND_ID[b], 0.0) for b in BANDS}}


def vsi(zip_path, member):
    return "/vsizip/" + os.path.abspath(zip_path).replace("\\", "/") + "/" + member


def crs_wkt(zip_path):
    info = inspect(zip_path)
    ds = gdal.Open(vsi(zip_path, info["members"]["B02"]))
    return ds.GetProjection()


def _window(gt, xsize, ysize, bounds):
    """Pixel window (even offsets and sizes) covering bounds, clamped to the tile."""
    if bounds is None:
        return 0, 0, xsize - xsize % 2, ysize - ysize % 2
    xmin, ymin, xmax, ymax = bounds
    c0 = math.floor((xmin - gt[0]) / gt[1])
    c1 = math.ceil((xmax - gt[0]) / gt[1])
    r0 = math.floor((ymax - gt[3]) / gt[5])
    r1 = math.ceil((ymin - gt[3]) / gt[5])
    c0, r0 = max(0, c0 - c0 % 2), max(0, r0 - r0 % 2)
    c1, r1 = min(xsize, c1 + c1 % 2), min(ysize, r1 + r1 % 2)
    if c1 <= c0 or r1 <= r0:
        raise SafeError("The extent does not overlap this Sentinel-2 tile.")
    w, h = c1 - c0, r1 - r0
    return c0, r0, w - w % 2, h - h % 2


def polygon_mask(wkt, gt, w, h, srs_wkt):
    """Boolean array, True inside the polygon (WKT in the raster CRS)."""
    geom = ogr.CreateGeometryFromWkt(wkt)
    if geom is None:
        raise SafeError("Could not read the area polygon.")
    srs = osr.SpatialReference()
    srs.ImportFromWkt(srs_wkt)
    mem = ogr.GetDriverByName("Memory").CreateDataSource("aoi")
    lyr = mem.CreateLayer("aoi", srs, ogr.wkbUnknown)
    feat = ogr.Feature(lyr.GetLayerDefn())
    feat.SetGeometry(geom)
    lyr.CreateFeature(feat)
    ras = gdal.GetDriverByName("MEM").Create("", w, h, 1, gdal.GDT_Byte)
    ras.SetGeoTransform(gt)
    ras.SetProjection(srs_wkt)
    gdal.RasterizeLayer(ras, [1], lyr, burn_values=[1])  # pixel centres inside
    return ras.GetRasterBand(1).ReadAsArray().astype(bool)


STRIP_PIXELS = 4_000_000  # pixels read at once per band (about 16 MB in float32)


def strip_rows(w, block_h=1, pixels=None):
    """Rows per strip: whole blocks of the source when possible, always even (for the 20 m SCL)."""
    pixels = STRIP_PIXELS if pixels is None else pixels
    rows = max(1, pixels // max(w, 1))
    if block_h > 1:
        rows = max(block_h, rows // block_h * block_h)
    return max(2, rows + rows % 2)


def prepare(zip_path, out_tif, bounds=None, use_scl=True, water_mask=True,
            ndwi_threshold=0.0, scl_invalid=SCL_INVALID_DEFAULT, log=print,
            aoi_wkt=None):
    """Write a masked reflectance GeoTIFF. bounds and aoi_wkt are in the tile CRS.

    If aoi_wkt is given, pixels whose centre is outside the polygon become nodata.
    Works strip by strip, so a whole tile does not need to fit in memory.

    Returns a dict with simple statistics of what was masked.
    """
    info = inspect(zip_path)
    m = info["members"]
    ref = gdal.Open(vsi(zip_path, m["B02"]))
    gt = ref.GetGeoTransform()
    proj = ref.GetProjection()
    c0, r0, w, h = _window(gt, ref.RasterXSize, ref.RasterYSize, bounds)
    out_gt = (gt[0] + c0 * gt[1], gt[1], 0.0, gt[3] + r0 * gt[5], 0.0, gt[5])
    dss = [gdal.Open(vsi(zip_path, m[b])) for b in BANDS]  # keep the datasets alive while reading
    bands = [d.GetRasterBand(1) for d in dss]
    scl_ds = scl_band = None
    if use_scl:
        if m["SCL"] is None:
            log("Warning: SCL layer not found, no cloud mask applied.")
        else:
            scl_ds = gdal.Open(vsi(zip_path, m["SCL"]))
            scl_band = scl_ds.GetRasterBand(1)
    rows = strip_rows(w, bands[0].GetBlockSize()[1])

    out = gdal.GetDriverByName("GTiff").Create(
        out_tif, w, h, len(BANDS), gdal.GDT_Float32,
        options=["COMPRESS=DEFLATE", "TILED=YES", "PREDICTOR=3", "BIGTIFF=IF_SAFER"])
    out.SetGeoTransform(out_gt)
    out.SetProjection(proj)
    for i, b in enumerate(BANDS, start=1):
        out.GetRasterBand(i).SetNoDataValue(NODATA)
        out.GetRasterBand(i).SetDescription(b)
    out.SetMetadataItem("SOURCE", os.path.basename(zip_path))

    n_total = n_outside = n_inside = n_cloud = n_land = n_valid = 0
    for rr in range(0, h, rows):
        nr = min(rows, h - rr)
        stack = []
        for b, band in zip(BANDS, bands):
            dn = band.ReadAsArray(c0, r0 + rr, w, nr).astype(np.float32)
            nodata = dn == 0
            refl = (dn + info["offsets"][b]) / info["quant"]
            refl[nodata] = np.nan
            stack.append(refl)
        stack = np.stack(stack)
        valid = np.all(np.isfinite(stack), axis=0)
        n_total += int(valid.sum())
        if aoi_wkt:
            sgt = (out_gt[0], out_gt[1], 0.0, out_gt[3] + rr * out_gt[5], 0.0, out_gt[5])
            inside = polygon_mask(aoi_wkt, sgt, w, nr, proj)
            n_outside += int((valid & ~inside).sum())
            valid &= inside
            n_inside += int(valid.sum())
        if scl_band is not None:
            scl = scl_band.ReadAsArray(c0 // 2, (r0 + rr) // 2, w // 2, nr // 2)
            scl = np.repeat(np.repeat(scl, 2, axis=0), 2, axis=1)
            bad = np.isin(scl, scl_invalid) & valid
            n_cloud += int(bad.sum())
            valid &= ~bad
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
        for i in range(len(BANDS)):
            out.GetRasterBand(i + 1).WriteArray(stack[i], 0, rr)
    out.FlushCache()
    out = None
    if aoi_wkt and n_inside == 0:
        gdal.GetDriverByName("GTiff").Delete(out_tif)
        raise SafeError("The area polygon does not cover any valid pixel of this tile.")

    return {"pixels": n_total, "outside_area": n_outside, "masked_cloud": n_cloud, "masked_land": n_land,
            "valid_water": n_valid, "offsets": info["offsets"],
            "quantification": info["quant"]}
