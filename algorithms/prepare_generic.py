from qgis.core import (QgsProcessingAlgorithm, QgsProcessingException,
                       QgsProcessingParameterBand, QgsProcessingParameterBoolean,
                       QgsProcessingParameterExtent,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterRasterDestination,
                       QgsProcessingParameterRasterLayer)

from ..author import CREDIT
from ..compat import NUM_DOUBLE, SRC_POLYGON
from ..core import generic
from .aoi import combine, set_core_lang, union_geometry


class PrepareGeneric(QgsProcessingAlgorithm):
    def createInstance(self):
        return PrepareGeneric()

    def name(self):
        return "prepare_generic"

    def displayName(self):
        return "Prepare any reflectance raster (PlanetScope, drone, other sensors)"

    def group(self):
        return "2. Preprocessing"

    def groupId(self):
        return "preprocessing"

    def shortHelpString(self):
        return (CREDIT + "\n\n"
                "Turns any raster with blue, green, red and near-infrared bands into the GLUB 4-band reflectance "
                "GeoTIFF (1 blue, 2 green, 3 red, 4 NIR), at its own pixel size, so the other tools can use it. "
                "Reflectance = value x SCALE + OFFSET (e.g. 0.0001 and 0 for PlanetScope surface reflectance "
                "stored as 0-10000). Clip by extent and/or polygon, NDWI water mask. Clouds are not removed. "
                "NIR is needed (water mask and sunglint correction).")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer("INPUT", "Reflectance raster"))
        for i, (k, lab) in enumerate((("BLUE", "Blue band"), ("GREEN", "Green band"), ("RED", "Red band"),
                                      ("NIR", "NIR band")), start=1):
            self.addParameter(QgsProcessingParameterBand(k, lab, i, "INPUT"))
        self.addParameter(QgsProcessingParameterNumber("SCALE", "Scale (reflectance = value x scale + offset)",
                                                       NUM_DOUBLE, 1.0))
        self.addParameter(QgsProcessingParameterNumber("OFFSET", "Offset", NUM_DOUBLE, 0.0))
        self.addParameter(QgsProcessingParameterExtent("EXTENT", "Clip extent", optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource("AREA", "Area polygon (outside becomes nodata)",
                                                              [SRC_POLYGON], optional=True))
        self.addParameter(QgsProcessingParameterBoolean("WATER", "Mask land with NDWI", True))
        self.addParameter(QgsProcessingParameterNumber("NDWI_T", "NDWI threshold", NUM_DOUBLE, 0.0,
                                                       minValue=-1, maxValue=1))
        self.addParameter(QgsProcessingParameterRasterDestination("OUTPUT", "Reflectance"))

    def processAlgorithm(self, parameters, context, feedback):
        set_core_lang()
        lyr = self.parameterAsRasterLayer(parameters, "INPUT", context)
        out = self.parameterAsOutputLayer(parameters, "OUTPUT", context)
        crs = lyr.crs()
        ext = self.parameterAsExtent(parameters, "EXTENT", context, crs) if parameters.get("EXTENT") else None
        src = self.parameterAsSource(parameters, "AREA", context)
        geom = union_geometry(src, crs, context, feedback) if src is not None else None
        box = combine(ext, geom)
        bounds = None if box is None else (box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum())

        def log(msg, warn=False):
            (feedback.pushWarning if warn else feedback.pushInfo)(msg)

        bands = {k.lower(): self.parameterAsInt(parameters, k, context) for k in ("BLUE", "GREEN", "RED", "NIR")}
        try:
            st = generic.prepare(lyr.source(), out, bands, self.parameterAsDouble(parameters, "SCALE", context),
                                 self.parameterAsDouble(parameters, "OFFSET", context), bounds=bounds,
                                 aoi_wkt=geom.asWkt() if geom is not None else None,
                                 water_mask=self.parameterAsBool(parameters, "WATER", context),
                                 ndwi_threshold=self.parameterAsDouble(parameters, "NDWI_T", context), log=log)
        except generic.GenericError as e:
            raise QgsProcessingException(str(e))
        feedback.pushInfo(f"Valid pixels: {st['pixels']}. Outside the area: {st['outside_area']}. Land: "
                          f"{st['masked_land']}. Water left: {st['valid_water']}.")
        return {"OUTPUT": out}
