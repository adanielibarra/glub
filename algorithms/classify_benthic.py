from qgis.core import (QgsProcessingAlgorithm,
                       QgsProcessingException, QgsProcessingOutputFile,
                       QgsProcessingOutputRasterLayer,
                       QgsProcessingParameterBand,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterField,
                       QgsProcessingParameterFolderDestination,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterRasterLayer,
                       QgsProcessingParameterString, QgsWkbTypes)


from ..compat import NUM_DOUBLE, NUM_INTEGER, POINT_GEOMETRY, SRC_POINT, SRC_POLYGON
from ..author import CREDIT
from ..core import pipeline
from ..core.lang import L
from .aoi import read_training, set_core_lang, union_geometry

BANDS = ("blue", "green", "red", "nir")
SIGNS = ("automatic (StarShoal metadata, else from the values: mostly negative = elevation)", "depth, positive down", "elevation, negative down")
SIGN_VALUES = ("auto", 1.0, -1.0)


class ClassifyBenthic(QgsProcessingAlgorithm):
    def createInstance(self):
        return ClassifyBenthic()

    def name(self):
        return "classify_benthic"

    def displayName(self):
        return "Benthic habitat classification (seagrass, sand, rock...)"

    def group(self):
        return "4. Classification"

    def groupId(self):
        return "classification"

    def shortHelpString(self):
        return (CREDIT + "\n\n"
                "Supervised classification of the seabed with reference points or polygons (one class field).\n\n"
                "Features: the chosen reflectance bands and, optionally, every band of a water-column index "
                "raster (Lyzenga DII).\n\n"
                "Depth mask, three states: bottom visible (classified), bottom not visible (code 250, no data) "
                "and too deep for seagrass (code 251). With a deep-water polygon, a pixel is visible only if it "
                "differs from that water by more than n standard deviations in some band, so dark meadows drop "
                "out before sand. The optical limit uses a depth raster (e.g. StarShoal "
                "depth_*.tif; with 0 the limit is read from its metadata) and optionally its trust raster (0 = "
                "extrapolated = not visible). The ecological limit needs an INDEPENDENT bathymetry (EMODnet, "
                "chart, multibeam): with only an SDB, pixels past the optical limit stay 'not visible'.\n\n"
                "Samples in the hidden or too-deep zone are dropped. Pixels of one polygon always stay together "
                "in calibration or validation. Split: spatial blocks by class, or random by feature.\n\n"
                "Optional: shrink the reference polygons (inward buffer) to leave out mixed edge pixels; a "
                "majority filter and a minimum mapping unit on the final map (saved as classes_filtered.tif, the raw "
                "map is kept; only class pixels change and the report checks both maps).\n\n"
                "Bottom texture (optional): local standard deviation in 3 x 3 or 5 x 5 windows of the water-column "
                "indices (else of blue and green), added as features; it helps with patchy versus smooth bottoms "
                "of similar colour, but with 10 m pixels it may add little.\n\n"
                "Minimum probability (optional): if no class reaches it, the pixel is left unclassified (code 252) "
                "instead of forcing a class; the report gives the share of validation samples that fall there and "
                "the corrected areas treat that zone as one more stratum.\n\n"
                "Outputs in the folder: classes.tif (+ .qml style), probability.tif (max and per class), "
                "legend.csv (areas), samples.csv and report.html (confusion matrix, producer's and user's "
                "accuracy, F1, accuracy by polygon (majority vote) and by pixel, accuracy by depth, Olofsson et al. 2014 corrected areas).")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer("INPUT", "Reflectance raster"))
        for i, b in enumerate(BANDS, 1):
            self.addParameter(QgsProcessingParameterBand(b.upper(), f"{b.capitalize() if b != 'nir' else 'NIR'} band",
                                                         i, "INPUT"))
        self.addParameter(QgsProcessingParameterEnum("USE", "Reflectance bands used as features", list(BANDS),
                                                     True, [0, 1, 2], optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer("DII", "Water-column indices (all bands used)",
                                                            optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(
            "TRAIN", "Reference points or polygons", [SRC_POINT, SRC_POLYGON]))
        self.addParameter(QgsProcessingParameterField("FIELD", "Class field", parentLayerParameterName="TRAIN"))
        self.addParameter(QgsProcessingParameterNumber("MAXPOLY", "Max pixels per polygon (0 = all)",
                                                       NUM_INTEGER, 200, minValue=0))
        self.addParameter(QgsProcessingParameterNumber("SHRINK", "Shrink reference polygons by (CRS units, 0 = no)",
                                                       NUM_DOUBLE, 0.0, minValue=0))
        self.addParameter(QgsProcessingParameterEnum(
            "TEXTURE", "Bottom texture as features (local sd of the water-column indices, else of blue and green)",
            ["no", "3 x 3", "5 x 5"], False, 0))
        self.addParameter(QgsProcessingParameterNumber(
            "MINPROB", "Minimum class probability (0 = off; below it the pixel is left unclassified, code 252)",
            NUM_DOUBLE, 0.0, minValue=0.0, maxValue=0.99))
        self.addParameter(QgsProcessingParameterEnum("FILTER", "Majority filter on the final map",
                                                     ["no", "3 x 3", "5 x 5"], False, 0))
        self.addParameter(QgsProcessingParameterNumber("MMU", "Minimum mapping unit, pixels (0 = off)",
                                                       NUM_INTEGER, 0, minValue=0))
        self.addParameter(QgsProcessingParameterRasterLayer("OPT", "Depth raster for the optical limit", optional=True))
        self.addParameter(QgsProcessingParameterBand("OPT_BAND", "Depth band", 1, "OPT", optional=True))
        self.addParameter(QgsProcessingParameterEnum("OPT_SIGN", "Depth raster values", list(SIGNS), False, 0))
        self.addParameter(QgsProcessingParameterNumber("OPT_LIMIT", "Optical depth limit (m, 0 = from StarShoal metadata)",
                                                       NUM_DOUBLE, 0.0, minValue=0))
        self.addParameter(QgsProcessingParameterRasterLayer("TRUST", "StarShoal trust raster", optional=True))
        self.addParameter(QgsProcessingParameterRasterLayer("ECO", "Independent bathymetry for the ecological limit",
                                                            optional=True))
        self.addParameter(QgsProcessingParameterBand("ECO_BAND", "Bathymetry band", 1, "ECO", optional=True))
        self.addParameter(QgsProcessingParameterEnum("ECO_SIGN", "Bathymetry values", list(SIGNS), False, 0))
        self.addParameter(QgsProcessingParameterNumber("ECO_LIMIT", "Ecological depth limit (m)",
                                                       NUM_DOUBLE, 35.0, minValue=0))
        self.addParameter(QgsProcessingParameterFeatureSource(
            "DEEP", "Deep-water polygon for the bottom-signal test", [SRC_POLYGON], optional=True))
        self.addParameter(QgsProcessingParameterNumber("NSIGMA", "Signal test threshold (standard deviations)",
                                                       NUM_DOUBLE, 3.0, minValue=0.5))
        self.addParameter(QgsProcessingParameterEnum("SIG_BANDS", "Signal test bands", ["blue", "green", "red"],
                                                     True, [0, 1]))
        self.addParameter(QgsProcessingParameterEnum("METHOD", "Classifier",
                                                     ["Random Forest (scikit-learn)", "Maximum likelihood (numpy)"],
                                                     False, 0))
        self.addParameter(QgsProcessingParameterNumber("TREES", "Random Forest trees",
                                                       NUM_INTEGER, 300, minValue=10))
        self.addParameter(QgsProcessingParameterBoolean(
            "BALANCED", "Balance classes (rare classes found more often, their area grows)", False))
        self.addParameter(QgsProcessingParameterEnum("SPLIT", "Split", ["Spatial blocks by class", "Random by feature", "Common spatial blocks (full separation)"],
                                                     False, 0))
        self.addParameter(QgsProcessingParameterNumber("BLOCK", "Block size (raster units)",
                                                       NUM_DOUBLE, 500.0, minValue=1))
        self.addParameter(QgsProcessingParameterNumber("VAL", "Validation fraction",
                                                       NUM_DOUBLE, 0.3, minValue=0.05,
                                                       maxValue=0.9))
        self.addParameter(QgsProcessingParameterNumber("SEED", "Seed", NUM_INTEGER, 42))
        self.addParameter(QgsProcessingParameterString("BINS", "Report depth ranges (m)", "0,2,5,10,15,20"))
        self.addParameter(QgsProcessingParameterFolderDestination("OUTDIR", "Output folder"))
        self.addOutput(QgsProcessingOutputRasterLayer("CLASSES", "Classes"))
        self.addOutput(QgsProcessingOutputRasterLayer("PROBABILITY", "Probability"))
        self.addOutput(QgsProcessingOutputFile("REPORT", "Report"))
        self.addOutput(QgsProcessingOutputRasterLayer("CLASSES_FILTERED", "Classes, filtered"))

    def processAlgorithm(self, parameters, context, feedback):
        set_core_lang()
        layer = self.parameterAsRasterLayer(parameters, "INPUT", context)
        use = [BANDS[i] for i in self.parameterAsEnums(parameters, "USE", context)]
        dii = self.parameterAsRasterLayer(parameters, "DII", context)
        if not use and dii is None:
            raise QgsProcessingException("Choose reflectance bands or a water-column index raster.")
        opts = {}
        if use:
            idx = {b: self.parameterAsInt(parameters, b.upper(), context) for b in use}
        else:
            idx = {"blue": self.parameterAsInt(parameters, "BLUE", context)}
            opts["refl_features"] = False
        src = self.parameterAsSource(parameters, "TRAIN", context)
        field = self.parameterAsString(parameters, "FIELD", context)
        is_point = QgsWkbTypes.geometryType(src.wkbType()) == POINT_GEOMETRY
        training, skipped = read_training(src.getFeatures(), src.sourceCrs(), is_point, layer.crs(),
                                          context.transformContext(), field)
        if skipped:
            feedback.pushWarning(f"{skipped} features without geometry or class were skipped.")
        mask = {}
        opt = self.parameterAsRasterLayer(parameters, "OPT", context)
        lim = self.parameterAsDouble(parameters, "OPT_LIMIT", context)
        if opt is not None:
            mask.update(opt_path=opt.source(), opt_band=self.parameterAsInt(parameters, "OPT_BAND", context) or 1,
                        opt_sign=SIGN_VALUES[self.parameterAsEnum(parameters, "OPT_SIGN", context)])
        if lim > 0:
            mask["opt_limit"] = lim
        trust = self.parameterAsRasterLayer(parameters, "TRUST", context)
        if trust is not None:
            mask["trust_path"] = trust.source()
        eco = self.parameterAsRasterLayer(parameters, "ECO", context)
        if eco is not None:
            mask.update(eco_path=eco.source(), eco_band=self.parameterAsInt(parameters, "ECO_BAND", context) or 1,
                        eco_sign=SIGN_VALUES[self.parameterAsEnum(parameters, "ECO_SIGN", context)],
                        eco_limit=self.parameterAsDouble(parameters, "ECO_LIMIT", context))
        deep_src = self.parameterAsSource(parameters, "DEEP", context)
        if deep_src is not None:
            sb = [("blue", "green", "red")[i] for i in self.parameterAsEnums(parameters, "SIG_BANDS", context)]
            if not sb:
                raise QgsProcessingException("The signal test needs at least one band.")
            mask.update(deep_wkt=union_geometry(deep_src, layer.crs(), context, feedback).asWkt(),
                        sig_bands={b: self.parameterAsInt(parameters, b.upper(), context) for b in sb},
                        n_sigma=self.parameterAsDouble(parameters, "NSIGMA", context))
        try:
            bins = [float(s) for s in self.parameterAsString(parameters, "BINS", context).split(",") if s.strip()]
        except ValueError:
            raise QgsProcessingException("Depth ranges must be numbers separated by commas.")
        method = ("rf", "ml")[self.parameterAsEnum(parameters, "METHOD", context)]
        opts.update(method=method, trees=self.parameterAsInt(parameters, "TREES", context),
                    balanced=self.parameterAsBool(parameters, "BALANCED", context),
                    split=("blocks", "random", "blocks_all")[self.parameterAsEnum(parameters, "SPLIT", context)],
                    block_size=self.parameterAsDouble(parameters, "BLOCK", context),
                    val_fraction=self.parameterAsDouble(parameters, "VAL", context),
                    seed=self.parameterAsInt(parameters, "SEED", context),
                    max_per_polygon=self.parameterAsInt(parameters, "MAXPOLY", context), depth_bins=bins,
                    shrink=self.parameterAsDouble(parameters, "SHRINK", context),
                    filter_window=(0, 3, 5)[self.parameterAsEnum(parameters, "FILTER", context)],
                    mmu=self.parameterAsInt(parameters, "MMU", context),
                    min_prob=self.parameterAsDouble(parameters, "MINPROB", context),
                    texture_window=(0, 3, 5)[self.parameterAsEnum(parameters, "TEXTURE", context)])
        out_dir = self.parameterAsString(parameters, "OUTDIR", context)
        no = L("none", "ninguno")
        settings = [(L("Reflectance", "Reflectancia"), layer.source()),
                    (L("Reflectance bands used", "Bandas de reflectancia usadas"), ", ".join(use) or no),
                    (L("Water-column indices", "Índices de columna de agua"), dii.source() if dii else no),
                    (L("Reference data", "Verdad de campo"),
                     L(f"{src.sourceName()} ({training['kind']}), field '{field}'",
                       f"{src.sourceName()} ({training['kind']}), campo '{field}'")),
                    (L("Depth for the optical limit", "Profundidad para el límite óptico"), opt.source() if opt else no),
                    (L("StarShoal trust", "Confianza de StarShoal"), trust.source() if trust else no),
                    (L("Independent bathymetry", "Batimetría independiente"), eco.source() if eco else no),
                    (L("Method", "Método"), method),
                    (L("Split", "Separación"), L(f"{opts['split']}, block {opts['block_size']:g}, "
                                                 f"validation {opts['val_fraction']:g}, seed {opts['seed']}",
                                                 f"{opts['split']}, bloque {opts['block_size']:g}, "
                                                 f"validación {opts['val_fraction']:g}, semilla {opts['seed']}"))]

        def log(msg, warn=False):
            (feedback.pushWarning if warn else feedback.pushInfo)(msg)

        try:
            _s, _w, written = pipeline.classify_file(
                layer.source(), idx, training, opts, out_dir, dii_path=dii.source() if dii else None,
                mask=mask, settings=settings, credit=CREDIT, log=log,
                progress=lambda p: feedback.setProgress(int(p)))
        except ValueError as e:
            raise QgsProcessingException(str(e))
        return {"CLASSES_FILTERED": written.get("classes_filtered"), "CLASSES": written["classes"], "PROBABILITY": written["probability"], "REPORT": written["report"],
                "OUTDIR": out_dir}
