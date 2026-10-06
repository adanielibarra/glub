from qgis.core import (QgsProcessingAlgorithm,
                       QgsProcessingException, QgsProcessingOutputRasterLayer,
                       QgsProcessingParameterMultipleLayers,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterRasterDestination)

from .aoi import set_core_lang
from ..compat import NUM_INTEGER, SRC_RASTER
from ..author import CREDIT
from ..core import pipeline


class CompositeMedian(QgsProcessingAlgorithm):
    def createInstance(self):
        return CompositeMedian()

    def name(self):
        return "composite_median"

    def displayName(self):
        return "Median composite of several dates"

    def group(self):
        return "3. Composite and water column"

    def groupId(self):
        return "watercolumn"

    def shortHelpString(self):
        return (CREDIT + "\n\n"
                "Per-pixel median of several reflectance rasters (same bands in the same order). Every raster "
                "is resampled, nearest neighbour, to the grid of the first one. A second raster "
                "(<output>_count.tif) counts the valid dates per pixel.\n\n"
                "Correct the sunglint of each date before compositing: glint changes from day to day and a "
                "median does not remove it reliably.\n\n"
                "The acquisition date of each raster is read from its metadata or name and written to the log; "
                "a warning is given when the dates span more than MAXDAYS days, several seasons or several years. "
                "Nothing is removed automatically.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterMultipleLayers("INPUTS", "Reflectance rasters",
                                                               SRC_RASTER))
        self.addParameter(QgsProcessingParameterNumber("MIN", "Minimum valid dates per pixel",
                                                       NUM_INTEGER, 1, minValue=1))
        self.addParameter(QgsProcessingParameterNumber("MAXDAYS", "Warn if the dates span more than (days)",
                                                       NUM_INTEGER, 45, minValue=1))
        self.addParameter(QgsProcessingParameterRasterDestination("OUTPUT", "Median composite"))
        self.addOutput(QgsProcessingOutputRasterLayer("COUNT", "Valid dates per pixel"))

    def processAlgorithm(self, parameters, context, feedback):
        set_core_lang()
        layers = self.parameterAsLayerList(parameters, "INPUTS", context)
        out = self.parameterAsOutputLayer(parameters, "OUTPUT", context)

        def log(msg, warn=False):
            (feedback.pushWarning if warn else feedback.pushInfo)(msg)

        try:
            st = pipeline.composite_file([l.source() for l in layers], out,
                                         self.parameterAsInt(parameters, "MIN", context), log,
                                         self.parameterAsInt(parameters, "MAXDAYS", context))
        except ValueError as e:
            raise QgsProcessingException(str(e))
        return {"OUTPUT": out, "COUNT": st["count"]}
