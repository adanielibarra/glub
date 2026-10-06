from qgis.core import (QgsProcessingAlgorithm,
                       QgsProcessingException, QgsProcessingParameterBand,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterRasterDestination,
                       QgsProcessingParameterRasterLayer)


from ..compat import NUM_DOUBLE, SRC_POLYGON
from ..author import CREDIT
from ..core import pipeline
from .aoi import set_core_lang, union_geometry


class DeglintHedley(QgsProcessingAlgorithm):
    def createInstance(self):
        return DeglintHedley()

    def name(self):
        return "deglint_hedley"

    def displayName(self):
        return "Sunglint correction (Hedley)"

    def group(self):
        return "2. Preprocessing"

    def groupId(self):
        return "preprocessing"

    def shortHelpString(self):
        return (
            CREDIT + "\n\n"
            "Removes sunglint with the method of Hedley et al. (2005). For each visible "
            "band, a linear regression against NIR is fitted over a sample of optically "
            "deep water where glint varies, and the NIR-predicted glint is subtracted.\n\n"
            "The sample polygon must be deep water (the bottom must not be visible) "
            "with some glint variation, inside the raster. If your area has no deep "
            "water, prepare a larger extent first.\n\n"
            "Check the R² per band in the log: values near 0 mean there is little glint "
            "or the sample is not good, and the correction will do little or harm.\n\n"
            "NIR reference: minimum NIR in the sample (as in Hedley et al.). A low "
            "percentile (e.g. 1) is less sensitive to noisy pixels.\n\n"
            "Output keeps the same 4 bands (blue, green, red, NIR), NIR unchanged.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer("INPUT", "Reflectance raster"))
        self.addParameter(QgsProcessingParameterBand("BLUE", "Blue band", 1, "INPUT"))
        self.addParameter(QgsProcessingParameterBand("GREEN", "Green band", 2, "INPUT"))
        self.addParameter(QgsProcessingParameterBand("RED", "Red band", 3, "INPUT"))
        self.addParameter(QgsProcessingParameterBand("NIR", "NIR band", 4, "INPUT"))
        self.addParameter(QgsProcessingParameterFeatureSource(
            "DEEP", "Deep-water sample polygon", [SRC_POLYGON]))
        self.addParameter(QgsProcessingParameterNumber(
            "PCT", "NIR reference percentile (0 = minimum)",
            NUM_DOUBLE, 0.0, minValue=0, maxValue=20))
        self.addParameter(QgsProcessingParameterRasterDestination("OUTPUT", "Deglinted reflectance"))

    def processAlgorithm(self, parameters, context, feedback):
        set_core_lang()
        layer = self.parameterAsRasterLayer(parameters, "INPUT", context)
        idx = {k.lower(): self.parameterAsInt(parameters, k, context)
               for k in ("BLUE", "GREEN", "RED", "NIR")}
        geom = union_geometry(self.parameterAsSource(parameters, "DEEP", context),
                              layer.crs(), context, feedback)
        out = self.parameterAsOutputLayer(parameters, "OUTPUT", context)

        def log(msg, warn=False):
            (feedback.pushWarning if warn else feedback.pushInfo)(msg)

        try:
            pipeline.deglint_file(layer.source(), idx, geom.asWkt(), out,
                                  self.parameterAsDouble(parameters, "PCT", context), log)
        except ValueError as e:
            raise QgsProcessingException(str(e))
        return {"OUTPUT": out}
