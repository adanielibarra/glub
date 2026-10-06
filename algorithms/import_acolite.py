from qgis.core import (QgsCoordinateReferenceSystem,
                       QgsProcessingAlgorithm, QgsProcessingException,
                       QgsProcessingParameterBoolean, QgsProcessingParameterEnum,
                       QgsProcessingParameterExtent,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFile, QgsProcessingParameterNumber,
                       QgsProcessingParameterRasterDestination)

from ..compat import NUM_DOUBLE, SRC_POLYGON
from ..author import CREDIT
from ..core import acolite
from .aoi import combine, union_geometry


class ImportAcolite(QgsProcessingAlgorithm):
    def createInstance(self):
        return ImportAcolite()

    def name(self):
        return "import_acolite"

    def displayName(self):
        return "Import ACOLITE output"

    def group(self):
        return "2. Preprocessing"

    def groupId(self):
        return "preprocessing"

    def shortHelpString(self):
        return (
            CREDIT + "\n\n"
            "Turns an ACOLITE output into the GLUB 4-band reflectance GeoTIFF (blue, green, red, NIR). "
            "ACOLITE is a separate program (RBINS, GPL-3); run it on a Sentinel-2 L1C product and give "
            "here its L2R NetCDF (..._L2R.nc) or one of its exported GeoTIFFs (..._L2R_rhos_492.tif).\n\n"
            "For each band the variable with the nearest wavelength is used (within 30 nm of 490, 560, 665 "
            "and 842 nm), so it works for Sentinel-2A, 2B and 2C. The chosen variables are written in the log "
            "and in the raster metadata.\n\n"
            "Quantity: rhos (surface reflectance, L2R) by default; rhow or Rrs if you give an L2W file that "
            "has them.\n\n"
            "There is no cloud mask here (ACOLITE L2R has none); use the area polygon to leave clouds out. "
            "ACOLITE's own residual glint correction is off by default; if you did not turn it on, the "
            "Hedley correction of GLUB still applies.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile("INPUT", "ACOLITE NetCDF or exported GeoTIFF",
                                                     fileFilter="ACOLITE (*.nc *.tif *.tiff)"))
        self.addParameter(QgsProcessingParameterEnum("QUANTITY", "Quantity", list(acolite.QUANTITIES), defaultValue=0))
        self.addParameter(QgsProcessingParameterExtent("EXTENT", "Clip extent (canvas, layer or drawn)", optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(
            "AREA", "Area polygon (outside becomes nodata)", [SRC_POLYGON], optional=True))
        self.addParameter(QgsProcessingParameterBoolean("WATER", "Mask land with NDWI", True))
        self.addParameter(QgsProcessingParameterNumber(
            "NDWI_T", "NDWI threshold", NUM_DOUBLE, 0.0, minValue=-1, maxValue=1))
        self.addParameter(QgsProcessingParameterRasterDestination("OUTPUT", "Reflectance"))

    def processAlgorithm(self, parameters, context, feedback):
        path = self.parameterAsFile(parameters, "INPUT", context)
        quantity = acolite.QUANTITIES[self.parameterAsEnum(parameters, "QUANTITY", context)]
        out = self.parameterAsOutputLayer(parameters, "OUTPUT", context)
        try:
            crs = QgsCoordinateReferenceSystem.fromWkt(acolite.crs_wkt(path, quantity))
        except acolite.AcoliteError as e:
            raise QgsProcessingException(str(e))
        ext = self.parameterAsExtent(parameters, "EXTENT", context, crs) if parameters.get("EXTENT") else None
        source = self.parameterAsSource(parameters, "AREA", context)
        geom = union_geometry(source, crs, context, feedback) if source is not None else None
        box = combine(ext, geom)
        bounds = None if box is None else (box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum())
        try:
            st = acolite.import_acolite(
                path, out, quantity=quantity, bounds=bounds, aoi_wkt=geom.asWkt() if geom is not None else None,
                water_mask=self.parameterAsBool(parameters, "WATER", context),
                ndwi_threshold=self.parameterAsDouble(parameters, "NDWI_T", context), log=feedback.pushInfo)
        except acolite.AcoliteError as e:
            raise QgsProcessingException(str(e))
        feedback.pushInfo(f"Pixels: {st['pixels']}. Outside the polygon: {st['outside_area']}. "
                          f"Land: {st['masked_land']}. Usable water: {st['valid_water']}.")
        return {"OUTPUT": out}
