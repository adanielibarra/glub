"""Stratified random validation points for a class map, and the map assessment with them."""
import os

from qgis.core import (QgsProcessingAlgorithm, QgsProcessingContext,
                       QgsProcessingException, QgsProcessingOutputFile,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterField,
                       QgsProcessingParameterFileDestination,
                       QgsProcessingParameterFolderDestination,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterRasterLayer)

from ..author import CREDIT
from ..compat import NUM_DOUBLE, NUM_INTEGER, SRC_POINT
from ..core import report, sampling
from ..core.lang import L
from .aoi import set_core_lang

MODES = ("proportional to area, with a minimum per class", "equal per class")


def _log(feedback):
    def log(msg, warn=False):
        (feedback.pushWarning if warn else feedback.pushInfo)(msg)
    return log


class GenerateValidationPoints(QgsProcessingAlgorithm):
    def createInstance(self):
        return GenerateValidationPoints()

    def name(self):
        return "validation_points"

    def displayName(self):
        return "Validation points (stratified random by map class)"

    def group(self):
        return "5. Validation"

    def groupId(self):
        return "validation"

    def shortHelpString(self):
        return (CREDIT + "\n\n"
                "Random points within each class of the map (stratified random sampling, Olofsson et al. 2014), "
                "to label in the field or on better imagery WITHOUT looking at the map. With them, the assessment "
                "tool gives unbiased accuracy and error-corrected areas with 95 % intervals.\n\n"
                "Sample size: a total by hand, or (0) computed from the target standard error of overall accuracy "
                "and an expected user's accuracy: n = (sum W_i S_i / S(OA))^2, S_i = sqrt(U (1 - U)).\n\n"
                "Allocation: proportional to the area of each class, but at least a minimum per class; or equal. "
                "The low-confidence zone (code 252), if the map has it, is one more stratum. Optionally, a few "
                "points in the 'bottom not visible' and 'too deep' zones to check the mask (they do not enter the "
                "area estimate).\n\n"
                "Minimum distance: between points of the same class only. Points of different classes are not "
                "kept apart, because map errors gather at class edges.\n\n"
                "Output: a GeoPackage with an empty 'ref_class' field to fill (use the same names as the map "
                "classes), lon/lat for the GPS, and a CSV with the strata.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer("INPUT", "Class map (classes.tif)"))
        self.addParameter(QgsProcessingParameterNumber("NTOTAL", "Total points (0 = from the target error)",
                                                       NUM_INTEGER, 0, minValue=0))
        self.addParameter(QgsProcessingParameterNumber("SE", "Target standard error of overall accuracy",
                                                       NUM_DOUBLE, 0.02, minValue=0.001, maxValue=0.2))
        self.addParameter(QgsProcessingParameterNumber("UA", "Expected user's accuracy", NUM_DOUBLE, 0.8,
                                                       minValue=0.5, maxValue=0.99))
        self.addParameter(QgsProcessingParameterNumber("MINPER", "Minimum points per class", NUM_INTEGER, 50,
                                                       minValue=0))
        self.addParameter(QgsProcessingParameterEnum("MODE", "Allocation", list(MODES), False, 0))
        self.addParameter(QgsProcessingParameterNumber("NHIDDEN", "Points in 'bottom not visible' (mask check)",
                                                       NUM_INTEGER, 0, minValue=0))
        self.addParameter(QgsProcessingParameterNumber("NDEEP", "Points in 'too deep' (mask check)",
                                                       NUM_INTEGER, 0, minValue=0))
        self.addParameter(QgsProcessingParameterNumber("MINDIST", "Minimum distance within a class (m)",
                                                       NUM_DOUBLE, 30.0, minValue=0))
        self.addParameter(QgsProcessingParameterNumber("SEED", "Random seed", NUM_INTEGER, 42, minValue=0))
        self.addParameter(QgsProcessingParameterFileDestination("OUTPUT", "Validation points",
                                                                "GeoPackage (*.gpkg)"))
        self.addOutput(QgsProcessingOutputFile("STRATA", "Strata table"))

    def processAlgorithm(self, parameters, context, feedback):
        set_core_lang()
        layer = self.parameterAsRasterLayer(parameters, "INPUT", context)
        out = self.parameterAsFileOutput(parameters, "OUTPUT", context)
        if not out.lower().endswith(".gpkg"):
            out += ".gpkg"
        try:
            g = sampling.generate(
                layer.source(), out, n_total=self.parameterAsInt(parameters, "NTOTAL", context),
                target_se=self.parameterAsDouble(parameters, "SE", context),
                expected_ua=self.parameterAsDouble(parameters, "UA", context),
                min_per=self.parameterAsInt(parameters, "MINPER", context),
                mode=("proportional", "equal")[self.parameterAsEnum(parameters, "MODE", context)],
                n_hidden=self.parameterAsInt(parameters, "NHIDDEN", context),
                n_deep=self.parameterAsInt(parameters, "NDEEP", context),
                min_dist_m=self.parameterAsDouble(parameters, "MINDIST", context),
                seed=self.parameterAsInt(parameters, "SEED", context), log=_log(feedback))
        except ValueError as e:
            raise QgsProcessingException(str(e))
        try:
            context.addLayerToLoadOnCompletion(
                out + "|layername=validation_points",
                QgsProcessingContext.LayerDetails(L("validation points", "puntos de validación"),
                                                  context.project(), "OUTPUT"))
        except Exception as e:   # the file is written; only loading it into the project failed
            feedback.pushInfo(str(e))
        return {"OUTPUT": out, "STRATA": g["strata_csv"]}


class AssessWithPoints(QgsProcessingAlgorithm):
    def createInstance(self):
        return AssessWithPoints()

    def name(self):
        return "assess_map"

    def displayName(self):
        return "Map assessment with validation points (accuracy and corrected areas)"

    def group(self):
        return "5. Validation"

    def groupId(self):
        return "validation"

    def shortHelpString(self):
        return (CREDIT + "\n\n"
                "Accuracy of a class map and its error-corrected areas, from labelled validation points "
                "(Olofsson et al. 2014): overall, user's and producer's accuracy weighted by the area of each "
                "class, and the estimated area of each class with a 95 % interval.\n\n"
                "The stratum of each point is read from the map, so use the same map the points were drawn on. "
                "Reference labels are matched to the map class names (case and spaces ignored); labels the map "
                "does not have are kept as extra reference classes. Points without a label are left out (if they "
                "are not a random subset, the estimates are biased).\n\n"
                "Points in the 'bottom not visible' and 'too deep' zones go to a separate table (mask check).\n\n"
                "Valid for a probability sample (the points of the validation-point tool), not for field points "
                "placed where it was convenient.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer("INPUT", "Class map (classes.tif)"))
        self.addParameter(QgsProcessingParameterFeatureSource("POINTS", "Labelled validation points", [SRC_POINT]))
        self.addParameter(QgsProcessingParameterField("FIELD", "Reference class field",
                                                      parentLayerParameterName="POINTS", defaultValue="ref_class"))
        self.addParameter(QgsProcessingParameterFolderDestination("OUTDIR", "Output folder"))
        self.addOutput(QgsProcessingOutputFile("REPORT", "Report"))

    def processAlgorithm(self, parameters, context, feedback):
        set_core_lang()
        layer = self.parameterAsRasterLayer(parameters, "INPUT", context)
        src = self.parameterAsSource(parameters, "POINTS", context)
        field = self.parameterAsString(parameters, "FIELD", context)
        out_dir = self.parameterAsString(parameters, "OUTDIR", context)
        xs, ys, refs = read_points_labels(src.getFeatures(), src.sourceCrs(), layer.crs(),
                                          context.transformContext(), field)
        try:
            summ, warns = sampling.assess(layer.source(), xs, ys, refs, out_dir, log=_log(feedback))
        except ValueError as e:
            raise QgsProcessingException(str(e))
        settings = [(L("Class map", "Mapa de clases"), layer.source()),
                    (L("Validation points", "Puntos de validación"),
                     L(f"{src.sourceName()}, field '{field}'", f"{src.sourceName()}, campo '{field}'"))]
        rep = os.path.join(out_dir, "assessment.html")
        with open(rep, "w", encoding="utf-8") as fh:
            fh.write(report.build_assessment(settings, summ, warns, CREDIT))
        return {"REPORT": rep, "OUTDIR": out_dir}


def read_points_labels(features, src_crs, dest_crs, transform_context, field):
    """Point coordinates in dest_crs and the reference label of each point ('' when empty)."""
    from qgis.core import QgsCoordinateTransform
    xform = QgsCoordinateTransform(src_crs, dest_crs, transform_context)
    xs, ys, refs = [], [], []
    for f in features:
        g = f.geometry()
        if g is None or g.isNull() or g.isEmpty():
            continue
        pt = g.asMultiPoint()[0] if g.isMultipart() else g.asPoint()
        p = xform.transform(pt)
        try:
            v = f[field]
        except KeyError:
            v = None
        if v is None or str(v).strip() in ("", "NULL"):
            lab = ""
        else:
            lab = str(int(v)) if isinstance(v, float) and v.is_integer() else str(v).strip()
        xs.append(p.x())
        ys.append(p.y())
        refs.append(lab)
    return xs, ys, refs
