from qgis.core import (QgsProcessingAlgorithm, QgsProcessingContext,
                       QgsProcessingException, QgsProcessingParameterBoolean,
                       QgsProcessingParameterFileDestination,
                       QgsProcessingParameterRasterLayer)

from ..author import CREDIT
from ..core import vectorize
from ..core.lang import L
from .aoi import set_core_lang


class PolygonizeMap(QgsProcessingAlgorithm):
    def createInstance(self):
        return PolygonizeMap()

    def name(self):
        return "polygonize_map"

    def displayName(self):
        return "Class or change map to polygons (class, area, perimeter)"

    def group(self):
        return "4. Classification"

    def groupId(self):
        return "classification"

    def shortHelpString(self):
        return (CREDIT + "\n\n"
                "Turns a GLUB class map (classes.tif or classes_filtered.tif) or change map (change.tif) into "
                "polygons: each patch of 4-connected pixels of one code is a polygon with the fields code, class, "
                "area_ha and perimeter_m. The outlines follow the pixel edges (the map as it is, not smoothed). "
                "Only class codes by default; the mask zones (bottom not visible, too deep, low confidence, not "
                "comparable) can be added. Use the filtered map if you do not want one polygon per stray pixel.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer("INPUT", "Class or change map"))
        self.addParameter(QgsProcessingParameterBoolean("MASK", "Also export the mask zones", False))
        self.addParameter(QgsProcessingParameterFileDestination("OUTPUT", "Polygons", "GeoPackage (*.gpkg)"))

    def processAlgorithm(self, parameters, context, feedback):
        set_core_lang()
        lyr = self.parameterAsRasterLayer(parameters, "INPUT", context)
        out = self.parameterAsFileOutput(parameters, "OUTPUT", context)
        if not out.lower().endswith(".gpkg"):
            out += ".gpkg"
        try:
            vectorize.polygonize(lyr.source(), out, self.parameterAsBool(parameters, "MASK", context),
                                     log=feedback.pushInfo)
        except (ValueError, RuntimeError) as e:
            raise QgsProcessingException(str(e))
        try:
            context.addLayerToLoadOnCompletion(out + "|layername=classes", QgsProcessingContext.LayerDetails(
                L("polygons", "polígonos"), context.project(), "OUTPUT"))
        except Exception:
            pass
        return {"OUTPUT": out}
