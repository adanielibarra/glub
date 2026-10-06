"""Read Landsat 4-9 Collection 2 Level-2 products and write the GLUB 4-band reflectance GeoTIFF.

Input: the .tar bundle as downloaded from USGS (EarthExplorer), the folder where it
was unpacked, or any file of it (the MTL text or one band). Files are named
<product id>_SR_B<n>.TIF, <product id>_QA_PIXEL.TIF and <product id>_MTL.txt.

  bands        Landsat 8 and 9 (OLI): blue SR_B2, green SR_B3, red SR_B4, NIR SR_B5.
               Landsat 4, 5 (TM) and 7 (ETM+): blue SR_B1, green SR_B2, red SR_B3,
               NIR SR_B4. 30 m.
  scaling      surface reflectance = DN x 2.75e-05 - 0.2 (USGS Collection 2 Level-2;
               read from the MTL file when it is there); DN 0 is fill.
  cloud mask   QA_PIXEL bits 0 fill, 1 dilated cloud, 2 cirrus (8/9 only), 3 cloud,
               4 cloud shadow, 5 snow (USGS Collection 2 quality bands).
  water mask   NDWI (green, NIR), as for Sentinel-2.

Output bands: 1 blue, 2 green, 3 red, 4 NIR, float32, nodata -9999, the same layout
as the Sentinel-2 path, so every later step works the same way (with 30 m pixels).
Landsat 7 after 31 May 2003 has data gaps in stripes (SLC failure): a warning is given.
"""
import glob
import os
import re
import tarfile

import numpy as np
from osgeo import gdal

from .lang import L
from .s2safe import NODATA, _window, polygon_mask, strip_rows

gdal.UseExceptions()

BANDS_OLI = {"blue": "SR_B2", "green": "SR_B3", "red": "SR_B4", "nir": "SR_B5"}
BANDS_TM = {"blue": "SR_B1", "green": "SR_B2", "red": "SR_B3", "nir": "SR_B4"}
QA_BAD_BITS = (0, 1, 2, 3, 4, 5)
MULT, ADD = 2.75e-05, -0.2
_ID = re.compile(r"(L[CTEO]0[4-9])_L2S[PR]_(\d{6})_(\d{8})_\d{8}_\d{2}_(T1|T2|RT)")


class LandsatError(Exception):
    pass


def _members(path):
    """{suffix: GDAL path} of the product files, plus the product id and the MTL text (if any)."""
    files = {}
    mtl_text = None
    if os.path.isfile(path) and path.lower().endswith(".tar"):
        with tarfile.open(path) as t:
            names = t.getnames()
            mtl = [n for n in names if n.endswith("_MTL.txt")]
            if mtl:
                mtl_text = t.extractfile(mtl[0]).read().decode(errors="replace")
        prefix = "/vsitar/" + os.path.abspath(path).replace("\\", "/") + "/"
        cand = [(n, prefix + n) for n in names]
    else:
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        cand = [(os.path.basename(f), f) for f in glob.glob(os.path.join(folder, "*"))]
        if os.path.isfile(path):
            m = _ID.search(os.path.basename(path))
            if m:   # keep only the files of this product if the folder holds several
                cand = [(n, f) for n, f in cand if m.group(0) in n]
        mtl = [f for n, f in cand if n.endswith("_MTL.txt")]
        if mtl:
            with open(mtl[0], encoding="utf-8", errors="replace") as fh:
                mtl_text = fh.read()
    pids = []
    for n, _f in cand:
        m = _ID.search(n)
        if m and re.search(r"_(SR_B\d|QA_PIXEL)\.TIF$", n, re.I) and m.group(0) not in pids:
            pids.append(m.group(0))
    if len(pids) > 1:
        raise LandsatError(L(f"{len(pids)} Landsat products in the same place ({', '.join(pids[:3])}...): choose one "
                             "of its band files, or put each product in its own folder.",
                             f"Hay {len(pids)} productos Landsat en el mismo sitio ({', '.join(pids[:3])}...): elige "
                             "uno de sus ficheros de banda, o pon cada producto en su carpeta."))
    pid = pids[0] if pids else None
    for n, f in cand:
        mm = re.search(r"_(SR_B\d|QA_PIXEL)\.TIF$", n, re.I)
        if mm and pid and pid in n:
            files[mm.group(1).upper()] = f
    if pid is None:
        raise LandsatError(L("No Landsat Collection 2 product found (files like LC08_L2SP_..._SR_B2.TIF).",
                             "No se encuentra un producto Landsat Collection 2 (ficheros tipo "
                             "LC08_L2SP_..._SR_B2.TIF)."))
    return files, pid, mtl_text


def inspect(path):
    files, pid, mtl = _members(path)
    m = _ID.search(pid)
    sensor = m.group(1)
    names = BANDS_OLI if sensor in ("LC08", "LC09", "LO08", "LO09") else BANDS_TM
    missing = [b for b in names.values() if b not in files]
    if missing:
        raise LandsatError(L(f"{pid}: missing bands {', '.join(missing)} (is it a Level-2 surface reflectance "
                             "product?).",
                             f"{pid}: faltan las bandas {', '.join(missing)} (¿es un producto Level-2 de "
                             "reflectancia de superficie?)."))
    scale = {}
    for key, band in names.items():
        n = band[-1]
        mult = re.search(rf"REFLECTANCE_MULT_BAND_{n}\s*=\s*([-\d.Ee+]+)", mtl or "")
        add = re.search(rf"REFLECTANCE_ADD_BAND_{n}\s*=\s*([-\d.Ee+]+)", mtl or "")
        scale[key] = (float(mult.group(1)) if mult else MULT, float(add.group(1)) if add else ADD)
    date = m.group(3)
    return {"files": files, "id": pid, "sensor": sensor, "bands": names, "scale": scale,
            "date": f"{date[:4]}-{date[4:6]}-{date[6:]}", "has_qa": "QA_PIXEL" in files}


def crs_wkt(path):
    info = inspect(path)
    return gdal.Open(info["files"][info["bands"]["blue"]]).GetProjection()


def prepare(path, out_tif, bounds=None, use_qa=True, water_mask=True, ndwi_threshold=0.0, log=print,
            aoi_wkt=None):
    """Write the masked reflectance GeoTIFF (strip by strip). bounds and aoi_wkt in the product CRS."""
    info = inspect(path)
    keys = ("blue", "green", "red", "nir")
    log(L(f"{info['id']}: {info['sensor']}, {info['date']}.", f"{info['id']}: {info['sensor']}, {info['date']}."))
    if info["sensor"] == "LE07" and info["date"] > "2003-05-31":
        log(L("Landsat 7 after May 2003: the image has gaps in stripes (SLC-off); they stay as no data.",
              "Landsat 7 posterior a mayo de 2003: la imagen tiene huecos en bandas (SLC-off); quedan sin dato."),
            True)
    dss = [gdal.Open(info["files"][info["bands"][k]]) for k in keys]   # keep the datasets alive
    bands = [d.GetRasterBand(1) for d in dss]
    gt = dss[0].GetGeoTransform()
    proj = dss[0].GetProjection()
    try:
        c0, r0, w, h = _window(gt, dss[0].RasterXSize, dss[0].RasterYSize, bounds)
    except Exception:
        raise LandsatError(L("The extent does not overlap this Landsat scene.",
                             "La extensión no se solapa con esta escena Landsat."))
    out_gt = (gt[0] + c0 * gt[1], gt[1], 0.0, gt[3] + r0 * gt[5], 0.0, gt[5])
    qa_ds = qa_band = None
    if use_qa:
        if not info["has_qa"]:
            log(L("QA_PIXEL not found: no cloud mask applied.", "No está QA_PIXEL: no se aplica máscara de nubes."),
                True)
        else:
            qa_ds = gdal.Open(info["files"]["QA_PIXEL"])
            qa_band = qa_ds.GetRasterBand(1)
    bad_mask = sum(1 << b for b in QA_BAD_BITS)
    out = gdal.GetDriverByName("GTiff").Create(
        out_tif, w, h, 4, gdal.GDT_Float32,
        options=["COMPRESS=DEFLATE", "TILED=YES", "PREDICTOR=3", "BIGTIFF=IF_SAFER"])
    out.SetGeoTransform(out_gt)
    out.SetProjection(proj)
    for i, k in enumerate(keys, start=1):
        out.GetRasterBand(i).SetNoDataValue(NODATA)
        out.GetRasterBand(i).SetDescription(f"{k} ({info['bands'][k]})")
    out.SetMetadataItem("SOURCE", info["id"])
    out.SetMetadataItem("GLUB_SENSOR", info["sensor"])
    rows = strip_rows(w, bands[0].GetBlockSize()[1])
    n_total = n_outside = n_inside = n_cloud = n_land = n_valid = 0
    for rr in range(0, h, rows):
        nr = min(rows, h - rr)
        stack = []
        for k, band in zip(keys, bands):
            dn = band.ReadAsArray(c0, r0 + rr, w, nr).astype(np.float32)
            mult, add = info["scale"][k]
            refl = dn * mult + add
            refl[dn == 0] = np.nan
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
        if qa_band is not None:
            qa = qa_band.ReadAsArray(c0, r0 + rr, w, nr).astype(np.uint16)
            bad = ((qa & bad_mask) != 0) & valid
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
        for i in range(4):
            out.GetRasterBand(i + 1).WriteArray(stack[i], 0, rr)
    out.FlushCache()
    out = None
    if aoi_wkt and n_inside == 0:
        gdal.GetDriverByName("GTiff").Delete(out_tif)
        raise LandsatError(L("The area polygon does not cover any valid pixel of this scene.",
                             "El polígono no cubre ningún píxel válido de esta escena."))
    return {"pixels": n_total, "outside_area": n_outside, "masked_cloud": n_cloud, "masked_land": n_land,
            "valid_water": n_valid, "sensor": info["sensor"], "date": info["date"], "id": info["id"]}
