import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .algorithms.change_detection import ChangeDetection
from .algorithms.classify_benthic import ClassifyBenthic
from .algorithms.composite_median import CompositeMedian
from .algorithms.deglint_hedley import DeglintHedley
from .algorithms.download_s2 import DownloadSentinel2
from .algorithms.import_acolite import ImportAcolite
from .algorithms.polygonize_map import PolygonizeMap
from .algorithms.prepare_generic import PrepareGeneric
from .algorithms.prepare_landsat import PrepareLandsat
from .algorithms.prepare_s2 import PrepareSentinel2
from .algorithms.scene_clarity import SceneClarity
from .algorithms.validation_points import AssessWithPoints, GenerateValidationPoints
from .algorithms.water_column import WaterColumnDII


class GlubProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        for alg in (DownloadSentinel2(), PrepareSentinel2(), PrepareLandsat(), PrepareGeneric(), ImportAcolite(), DeglintHedley(),
                    CompositeMedian(), SceneClarity(), WaterColumnDII(), ClassifyBenthic(), PolygonizeMap(), GenerateValidationPoints(),
                    AssessWithPoints(), ChangeDetection()):
            self.addAlgorithm(alg)

    def id(self):
        return "glub"

    def name(self):
        return "GLUB"

    def longName(self):
        return "GLUB (Ibarra-Marinas et al., UAT)"

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))
