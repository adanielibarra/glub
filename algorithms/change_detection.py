import os

from qgis.core import (QgsProcessingAlgorithm, QgsProcessingException,
                       QgsProcessingOutputFile, QgsProcessingOutputRasterLayer,
                       QgsProcessingParameterFolderDestination,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterRasterLayer)

from ..author import CREDIT
from ..compat import NUM_INTEGER
from ..core import change, report
from ..core.lang import L
from .aoi import set_core_lang


class ChangeDetection(QgsProcessingAlgorithm):
    def createInstance(self):
        return ChangeDetection()

    def name(self):
        return "change_detection"

    def displayName(self):
        return "Change between two class maps (date 1 -> date 2)"

    def group(self):
        return "5. Validation"

    def groupId(self):
        return "validation"

    def shortHelpString(self):
        return (CREDIT + "\n\n"
                "Transitions between two class maps of the same place (classes.tif of two dates). Classes are "
                "matched by name; the second map is put on the grid of the first. Only pixels where the bottom "
                "is classified on both dates are compared; 'bottom not visible', 'too deep' or 'low confidence' "
                "on either date is 'not comparable' (code 250).\n\n"
                "Output: change.tif (one code per transition, names in the metadata and a QGIS style; seagrass "
                "loss in red, gain in green), change_matrix.csv (hectares), change_report.html (transition matrix, "
                "gains and losses by class) and, with a minimum change unit, change_filtered.tif.\n\n"
                "Mapped change is indicative: the errors of the two maps add up. For change areas to publish, "
                "draw stratified validation points on change.tif and label each one on both dates.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer("MAP1", "Class map, date 1"))
        self.addParameter(QgsProcessingParameterRasterLayer("MAP2", "Class map, date 2"))
        self.addParameter(QgsProcessingParameterNumber("MMU", "Minimum change unit, pixels (0 = off)",
                                                       NUM_INTEGER, 0, minValue=0))
        self.addParameter(QgsProcessingParameterFolderDestination("OUTDIR", "Output folder"))
        self.addOutput(QgsProcessingOutputRasterLayer("CHANGE", "Change"))
        self.addOutput(QgsProcessingOutputFile("REPORT", "Report"))

    def processAlgorithm(self, parameters, context, feedback):
        set_core_lang()
        m1 = self.parameterAsRasterLayer(parameters, "MAP1", context)
        m2 = self.parameterAsRasterLayer(parameters, "MAP2", context)
        mmu = self.parameterAsInt(parameters, "MMU", context)
        out_dir = self.parameterAsString(parameters, "OUTDIR", context)

        def log(msg, warn=False):
            (feedback.pushWarning if warn else feedback.pushInfo)(msg)

        try:
            s, w = change.compare(m1.source(), m2.source(), out_dir, mmu, log)
        except ValueError as e:
            raise QgsProcessingException(str(e))
        settings = [(L("Map, date 1", "Mapa, fecha 1"), m1.source()), (L("Map, date 2", "Mapa, fecha 2"), m2.source()),
                    (L("Minimum change unit", "Unidad mínima de cambio"), str(mmu) if mmu > 1 else L("off", "no"))]
        rep = os.path.join(out_dir, "change_report.html")
        with open(rep, "w", encoding="utf-8") as fh:
            fh.write(report.build_change(settings, s, w, CREDIT))
        return {"CHANGE": s["path"], "REPORT": rep, "OUTDIR": out_dir}
