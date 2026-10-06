"""Block-wise raster access, so a whole Sentinel-2 tile fits in memory. GDAL + numpy.

Rasters are read in strips of rows (all columns). Other rasters are put on the
reference grid through an in-memory VRT (lazy warping, nothing is loaded until a
strip is read). Polygons are rasterized only over their own bounding window.
"""
import numpy as np
from osgeo import gdal, ogr, osr
from .lang import L

gdal.UseExceptions()
NODATA = -9999.0
# pixels per strip; one float32 layer of a strip is then about 16 MB
STRIP_PIXELS = 4_000_000


class Grid:
    def __init__(self, gt, proj, w, h):
        if gt[2] != 0 or gt[4] != 0:
            raise ValueError(L("Rotated rasters are not supported.", "No se admiten rásteres girados."))
        self.gt, self.proj, self.w, self.h = tuple(gt), proj, w, h

    @classmethod
    def of(cls, path):
        ds = gdal.Open(path)
        return cls(ds.GetGeoTransform(), ds.GetProjection(), ds.RasterXSize, ds.RasterYSize)

    def strips(self, pixels=STRIP_PIXELS):
        rows = max(1, min(self.h, pixels // max(self.w, 1)))
        for r0 in range(0, self.h, rows):
            yield r0, min(rows, self.h - r0)

    def bounds(self):
        gt = self.gt
        return (gt[0], gt[3] + gt[5] * self.h, gt[0] + gt[1] * self.w, gt[3])


class Layer:
    """One band of a raster, on the grid (warped lazily if needed). read() gives float32, NaN = no data."""

    def __init__(self, path, band, grid, resample="bilinear"):
        src = gdal.Open(path)
        if band < 1 or band > src.RasterCount:
            raise ValueError(L(f"{path}: band {band} does not exist (it has {src.RasterCount}).",
                               f"{path}: la banda {band} no existe (tiene {src.RasterCount})."))
        self.metadata = src.GetMetadata() or {}
        self.description = src.GetRasterBand(band).GetDescription()
        same = (tuple(src.GetGeoTransform()) == grid.gt and src.RasterXSize == grid.w
                and src.RasterYSize == grid.h)
        if same:
            self.ds, self.b = src, src.GetRasterBand(band)
        else:
            self.ds = gdal.Warp("", src, format="VRT", outputBounds=grid.bounds(), width=grid.w,
                                height=grid.h, dstSRS=grid.proj, resampleAlg=resample, bandList=[band],
                                dstNodata=NODATA, outputType=gdal.GDT_Float32)
            self.b = self.ds.GetRasterBand(1)
        self.nodata = self.b.GetNoDataValue()

    def read(self, r0, nr, c0=0, nc=None):
        nc = self.ds.RasterXSize - c0 if nc is None else nc
        a = self.b.ReadAsArray(c0, r0, nc, nr).astype(np.float32)
        if self.nodata is not None and np.isfinite(self.nodata):
            a[a == np.float32(self.nodata)] = np.nan
        return a


def layers_of(path, idx, grid, resample="bilinear"):
    return {name: Layer(path, i, grid, resample) for name, i in idx.items()}


def window_of(wkt, grid):
    """(r0, nr, c0, nc) of the pixels covering the geometry envelope, clipped; None if outside."""
    g = ogr.CreateGeometryFromWkt(wkt)
    if g is None:
        raise ValueError(L("Could not read the polygon.", "No se pudo leer el polígono."))
    x0, x1, y0, y1 = g.GetEnvelope()
    gt = grid.gt
    c0 = int(np.floor((x0 - gt[0]) / gt[1]))
    c1 = int(np.ceil((x1 - gt[0]) / gt[1]))
    r0 = int(np.floor((y1 - gt[3]) / gt[5]))
    r1 = int(np.ceil((y0 - gt[3]) / gt[5]))
    c0, r0 = max(c0, 0), max(r0, 0)
    c1, r1 = min(c1, grid.w), min(r1, grid.h)
    if c1 <= c0 or r1 <= r0:
        return None
    return r0, r1 - r0, c0, c1 - c0


def rasterize_window(wkt, grid, win):
    """Bool mask (pixel centres inside the polygon) over the window."""
    r0, nr, c0, nc = win
    gt = grid.gt
    wgt = (gt[0] + c0 * gt[1], gt[1], 0.0, gt[3] + r0 * gt[5], 0.0, gt[5])
    srs = osr.SpatialReference()
    srs.ImportFromWkt(grid.proj)
    mem = ogr.GetDriverByName("Memory").CreateDataSource("w")
    lyr = mem.CreateLayer("w", srs, ogr.wkbUnknown)
    f = ogr.Feature(lyr.GetLayerDefn())
    f.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
    lyr.CreateFeature(f)
    ras = gdal.GetDriverByName("MEM").Create("", nc, nr, 1, gdal.GDT_Byte)
    ras.SetGeoTransform(wgt)
    ras.SetProjection(grid.proj)
    gdal.RasterizeLayer(ras, [1], lyr, burn_values=[1])
    return ras.GetRasterBand(1).ReadAsArray().astype(bool)


def sample_polygon(wkt, layers, grid):
    """Values of each layer at the pixels inside the polygon: {name: 1-D array}."""
    win = window_of(wkt, grid)
    if win is None:
        return {k: np.array([], dtype=np.float32) for k in layers}
    m = rasterize_window(wkt, grid, win)
    r0, nr, c0, nc = win
    return {k: lyr.read(r0, nr, c0, nc)[m] for k, lyr in layers.items()}


class Writer:
    """Tiled, compressed GeoTIFF written strip by strip."""

    def __init__(self, path, grid, names, dtype=gdal.GDT_Float32, nodata=NODATA, metadata=None):
        self.ds = gdal.GetDriverByName("GTiff").Create(
            path, grid.w, grid.h, len(names), dtype,
            options=["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"])
        self.ds.SetGeoTransform(grid.gt)
        self.ds.SetProjection(grid.proj)
        for k, v in (metadata or {}).items():
            self.ds.SetMetadataItem(str(k), str(v))
        for i, n in enumerate(names, start=1):
            b = self.ds.GetRasterBand(i)
            b.SetNoDataValue(nodata)
            b.SetDescription(n)
        self.path = path

    def write(self, r0, arrays):
        for i, a in enumerate(arrays, start=1):
            self.ds.GetRasterBand(i).WriteArray(a, 0, r0)

    def close(self):
        self.ds.FlushCache()
        self.ds = None
        return self.path


class TextureLayer:
    """Local standard deviation of another layer in a square window (3 or 5 pixels), read
    strip by strip with a halo of rows and columns, so it matches a whole-raster filter.
    No-data pixels are left out of the window; fewer than 3 valid pixels gives NaN."""

    def __init__(self, layer, window, name):
        if window not in (3, 5):
            raise ValueError("window must be 3 or 5")
        self.src, self.k, self.h = layer, window, window // 2
        self.ds = layer.ds
        self.description = name
        self.metadata = {}

    def read(self, r0, nr, c0=0, nc=None):
        H, W = self.ds.RasterYSize, self.ds.RasterXSize
        nc = W - c0 if nc is None else nc
        h = self.h
        a0, a1 = max(0, r0 - h), min(H, r0 + nr + h)
        b0, b1 = max(0, c0 - h), min(W, c0 + nc + h)
        a = self.src.read(a0, a1 - a0, b0, b1 - b0).astype(np.float64)
        # pad to a full halo with NaN (outside the raster)
        a = np.pad(a, ((h - (r0 - a0), h - (a1 - (r0 + nr))), (h - (c0 - b0), h - (b1 - (c0 + nc)))),
                   constant_values=np.nan)
        ok = np.isfinite(a)
        v = np.where(ok, a, 0.0)
        s = np.zeros((nr, nc))
        s2 = np.zeros((nr, nc))
        n = np.zeros((nr, nc))
        for dr in range(self.k):
            for dc in range(self.k):
                win = (slice(dr, dr + nr), slice(dc, dc + nc))
                s += v[win]
                s2 += v[win] ** 2
                n += ok[win]
        with np.errstate(invalid="ignore", divide="ignore"):
            m = s / n
            var = np.maximum(s2 / n - m * m, 0.0)
        out = np.sqrt(var).astype(np.float32)
        out[n < 3] = np.nan
        return out
