from qgis.core import (QgsProcessingAlgorithm,
                       QgsProcessingException, QgsProcessingParameterBand,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterRasterDestination,
                       QgsProcessingParameterRasterLayer)


from ..compat import NUM_DOUBLE, SRC_POLYGON
from ..author import CREDIT
from ..core import pipeline
from .aoi import set_core_lang, union_geometry

BANDS = ("blue", "green", "red")


class WaterColumnDII(QgsProcessingAlgorithm):
    def createInstance(self):
        return WaterColumnDII()

    def name(self):
        return "water_column_dii"

    def displayName(self):
        return "Water-column correction (Lyzenga depth-invariant index)"

    def group(self):
        return "3. Composite and water column"

    def groupId(self):
        return "watercolumn"

    def shortHelpString(self):
        return (CREDIT + "\n\n"
                "Depth-invariant bottom index of Lyzenga (1981). Over a polygon of ONE bottom type (usually "
                "sand) seen at several depths, the attenuation ratio of each band pair is k_i/k_j = a + "
                "sqrt(a² + 1), a = (var X_i - var X_j) / (2 cov(X_i, X_j)), X = ln(R - R_inf). The index is "
                "X_i - (k_i/k_j) X_j, one band per pair.\n\n"
                "Check the correlation of each pair in the log: below about 0.7 the ratio is unreliable (the "
                "polygon has little depth range or mixes bottoms, or the band does not see the bottom). With "
                "Sentinel-2 the red band only sees the bottom in the first metres; blue and green are usually "
                "the useful pair.\n\n"
                "R_inf: mean - k sd of a deep-water polygon (optional; 0 without it).\n\n"
                "Where R <= R_inf the logarithm does not exist. With a deep-water polygon, R - R_inf is floored "
                "at FLOOR standard deviations of deep water and those pixels are flagged in <output>_floored.tif: "
                "there the index does not measure the bottom (deep-water noise, or a bottom darker than the water "
                "column, where the Lyzenga model does not hold).")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer("INPUT", "Reflectance raster"))
        self.addParameter(QgsProcessingParameterBand("BLUE", "Blue band", 1, "INPUT"))
        self.addParameter(QgsProcessingParameterBand("GREEN", "Green band", 2, "INPUT"))
        self.addParameter(QgsProcessingParameterBand("RED", "Red band", 3, "INPUT"))
        self.addParameter(QgsProcessingParameterEnum("USE", "Bands to pair", list(BANDS), True, [0, 1]))
        self.addParameter(QgsProcessingParameterFeatureSource(
            "SAND", "Uniform-bottom polygon (one bottom type, several depths)", [SRC_POLYGON]))
        self.addParameter(QgsProcessingParameterFeatureSource(
            "DEEP", "Deep-water polygon for R_inf", [SRC_POLYGON], optional=True))
        self.addParameter(QgsProcessingParameterNumber("K", "R_inf = mean - k sd, k",
                                                       NUM_DOUBLE, 2.0, minValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            "FLOOR", "Floor of R - R_inf, in deep-water sd (0 = no floor, holes stay)",
            NUM_DOUBLE, 1.0, minValue=0))
        self.addParameter(QgsProcessingParameterRasterDestination("OUTPUT", "Depth-invariant indices"))

    def processAlgorithm(self, parameters, context, feedback):
        set_core_lang()
        layer = self.parameterAsRasterLayer(parameters, "INPUT", context)
        use = [BANDS[i] for i in self.parameterAsEnums(parameters, "USE", context)]
        if len(use) < 2:
            raise QgsProcessingException("Choose at least two bands.")
        idx = {b: self.parameterAsInt(parameters, b.upper(), context) for b in use}
        sand = union_geometry(self.parameterAsSource(parameters, "SAND", context), layer.crs(), context, feedback)
        deep_src = self.parameterAsSource(parameters, "DEEP", context)
        deep = union_geometry(deep_src, layer.crs(), context, feedback).asWkt() if deep_src else None
        out = self.parameterAsOutputLayer(parameters, "OUTPUT", context)

        def log(msg, warn=False):
            (feedback.pushWarning if warn else feedback.pushInfo)(msg)

        try:
            pipeline.watercolumn_file(layer.source(), idx, sand.asWkt(), out, deep,
                                      self.parameterAsDouble(parameters, "K", context), log,
                                      floor_sigma=self.parameterAsDouble(parameters, "FLOOR", context))
        except ValueError as e:
            raise QgsProcessingException(str(e))
        return {"OUTPUT": out}
