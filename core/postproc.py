"""Optional clean-up of the class map: majority filter and minimum mapping unit.

Only class codes (1..k) change. The mask codes (bottom not visible, too deep,
no data) are never filtered and never absorb a class patch, so the clean-up does
not move the boundary of where the map speaks.

  majority  each class pixel takes the most frequent class in its window
            (3x3 or 5x5, class pixels only); ties keep the original class.
  mmu       patches smaller than N pixels (4-connected) are merged into the
            neighbouring class patch (GDAL sieve, with the mask codes masked out).

The raw map is kept; the filtered one is a separate file. Filtering changes the
map, so its accuracy is checked again on the same validation samples.
"""
import numpy as np
from osgeo import gdal

from . import blockio
from .lang import L

gdal.UseExceptions()
MAX_CLASS = 249


def majority_strip(block, k, size):
    """block: uint8 with halo rows/cols already included. Returns the filtered centre."""
    h = size // 2
    H, W = block.shape
    counts = np.zeros((k + 1, H - 2 * h, W - 2 * h), dtype=np.int16)
    for dr in range(-h, h + 1):
        for dc in range(-h, h + 1):
            win = block[h + dr:H - h + dr, h + dc:W - h + dc]
            for c in range(1, k + 1):
                counts[c] += win == c
    centre = block[h:H - h, h:W - h]
    best = counts.argmax(0).astype(np.uint8)
    top = counts.max(0)
    tie = (counts == top[None]).sum(0) > 1
    out = centre.copy()
    is_class = (centre >= 1) & (centre <= k)
    change = is_class & ~tie & (top > 0)
    out[change] = best[change]
    return out


def clean(src_path, dst_path, k, window=0, mmu=0, log=print):
    """Write the cleaned class raster. window: 0 (off), 3 or 5. mmu: pixels (0 = off)."""
    grid = blockio.Grid.of(src_path)
    src = gdal.Open(src_path)
    sb = src.GetRasterBand(1)
    drv = gdal.GetDriverByName("GTiff")
    dst = drv.CreateCopy(dst_path, src, options=["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"])
    db = dst.GetRasterBand(1)
    changed = 0
    if window and window > 1:
        h = window // 2
        for r0, nr in grid.strips():
            a0, a1 = max(0, r0 - h), min(grid.h, r0 + nr + h)
            blk = sb.ReadAsArray(0, a0, grid.w, a1 - a0)
            pad_top, pad_bot = h - (r0 - a0), h - (a1 - (r0 + nr))
            blk = np.pad(blk, ((pad_top, pad_bot), (h, h)), constant_values=255)
            out = majority_strip(blk, k, window)
            changed += int((out != blk[h:-h, h:-h]).sum())
            db.WriteArray(out, 0, r0)
        dst.FlushCache()
        log(L(f"Majority filter {window}x{window}: {changed} class pixels changed.",
              f"Filtro de mayoría {window}x{window}: {changed} píxeles de clase cambiados."))
    if mmu and mmu > 1:
        # mask: class pixels only (mask codes neither change nor absorb patches)
        mds = drv.Create(dst_path + ".mask.tif", grid.w, grid.h, 1, gdal.GDT_Byte,
                         options=["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"])
        for r0, nr in grid.strips():
            a = db.ReadAsArray(0, r0, grid.w, nr)
            mds.GetRasterBand(1).WriteArray(((a >= 1) & (a <= k)).astype(np.uint8), 0, r0)
        mds.FlushCache()
        before = drv.CreateCopy(dst_path + ".before.tif", dst, options=["COMPRESS=DEFLATE", "TILED=YES"])
        gdal.SieveFilter(before.GetRasterBand(1), mds.GetRasterBand(1), db, int(mmu), 4)
        dst.FlushCache()
        n = 0
        for r0, nr in grid.strips():
            n += int((before.GetRasterBand(1).ReadAsArray(0, r0, grid.w, nr) !=
                      db.ReadAsArray(0, r0, grid.w, nr)).sum())
        before = mds = None
        drv.Delete(dst_path + ".before.tif")
        drv.Delete(dst_path + ".mask.tif")
        log(L(f"Minimum mapping unit {mmu} pixels: {n} class pixels merged into neighbouring patches.",
              f"Unidad mínima de {mmu} píxeles: {n} píxeles de clase unidos a manchas vecinas."))
        changed += n
    dst.SetMetadataItem("GLUB_CLEANUP", f"majority {window or 'off'}; minimum mapping unit "
                                           f"{str(mmu) + ' px' if mmu and mmu > 1 else 'off'}")
    dst = None
    return changed


def values_at(path, rows, cols):
    """Raster values at pixel positions, read strip by strip."""
    grid = blockio.Grid.of(path)
    ds = gdal.Open(path)  # keep the dataset alive while reading its band
    b = ds.GetRasterBand(1)
    out = np.zeros(len(rows), dtype=np.int64)
    for r0, nr in grid.strips():
        sel = np.nonzero((rows >= r0) & (rows < r0 + nr))[0]
        if len(sel):
            a = b.ReadAsArray(0, r0, grid.w, nr)
            out[sel] = a[rows[sel] - r0, cols[sel]]
    return out


def class_counts(path, k):
    grid = blockio.Grid.of(path)
    ds = gdal.Open(path)
    b = ds.GetRasterBand(1)
    cnt = np.zeros(k, dtype=np.int64)
    for r0, nr in grid.strips():
        a = b.ReadAsArray(0, r0, grid.w, nr)
        a = a[(a >= 1) & (a <= k)]
        cnt += np.bincount(a.astype(np.int64) - 1, minlength=k)
    return cnt
