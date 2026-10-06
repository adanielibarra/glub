from qgis.core import (QgsProcessingAlgorithm, QgsProcessingException,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFileDestination,
                       QgsProcessingParameterMultipleLayers)

from ..author import CREDIT
from ..compat import SRC_POLYGON, SRC_RASTER
from ..core import clarity
from .aoi import set_core_lang, union_geometry


class SceneClarity(QgsProcessingAlgorithm):
    def createInstance(self):
        return SceneClarity()

    def name(self):
        return "scene_clarity"

    def displayName(self):
        return "Rank scenes by water clarity"

    def group(self):
        return "3. Composite and water column"

    def groupId(self):
        return "watercolumn"

    def shortHelpString(self):
        return (CREDIT + "\n\n"
                "Ranks prepared reflectance rasters of the same place (bands blue, green, red, NIR in that order, "
                "same CRS) by how clear the water is, to choose the dates to map or to composite.\n\n"
                "Deep-water polygon (needed): mean and standard deviation of blue and green, mean red and NIR. "
                "Bright-bottom polygon (optional, e.g. sand a few metres deep): bottom contrast = (median R - deep "
                "mean) / deep sd, the larger of blue and green; the same quantity as the bottom-signal test of the "
                "classification. More contrast = the bottom is seen deeper that day.\n\n"
                "Ranking by bottom contrast, or by the red mean of deep water without a bottom polygon. Flags "
                "(nothing is removed): contrast below half of the best scene, bottom polygon mostly without data, "
                "deep-water sd above twice the median of the scenes. Rules of thumb for comparing dates of one "
                "place, not absolute water-quality thresholds.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterMultipleLayers("INPUTS", "Reflectance rasters", SRC_RASTER))
        self.addParameter(QgsProcessingParameterFeatureSource("DEEP", "Deep-water polygon", [SRC_POLYGON]))
        self.addParameter(QgsProcessingParameterFeatureSource("BOTTOM", "Bright-bottom polygon", [SRC_POLYGON],
                                                              optional=True))
        self.addParameter(QgsProcessingParameterFileDestination("OUTPUT", "Clarity table", "CSV (*.csv)"))

    def processAlgorithm(self, parameters, context, feedback):
        set_core_lang()
        layers = self.parameterAsLayerList(parameters, "INPUTS", context)
        if len(layers) < 2:
            raise QgsProcessingException("Give at least two rasters.")
        crs = layers[0].crs()
        deep = union_geometry(self.parameterAsSource(parameters, "DEEP", context), crs, context, feedback).asWkt()
        bsrc = self.parameterAsSource(parameters, "BOTTOM", context)
        bot = union_geometry(bsrc, crs, context, feedback).asWkt() if bsrc is not None else None
        out = self.parameterAsFileOutput(parameters, "OUTPUT", context)

        def log(msg, warn=False):
            (feedback.pushWarning if warn else feedback.pushInfo)(msg)

        try:
            clarity.rank([l.source() for l in layers], {"blue": 1, "green": 2, "red": 3, "nir": 4}, deep, bot,
                         log, out)
        except ValueError as e:
            raise QgsProcessingException(str(e))
        return {"OUTPUT": out}
