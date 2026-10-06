from qgis.core import (QgsCoordinateReferenceSystem,
                       QgsProcessingParameterFeatureSource, QgsProcessingAlgorithm,
                       QgsProcessingException, QgsProcessingParameterBoolean,
                       QgsProcessingParameterExtent, QgsProcessingParameterFile,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterRasterDestination)

from ..compat import NUM_DOUBLE, SRC_POLYGON
from ..author import CREDIT
from ..core import s2safe
from .aoi import combine, union_geometry


class PrepareSentinel2(QgsProcessingAlgorithm):
    AREA = "AREA"
    INPUT, EXTENT, USE_SCL, WATER, NDWI_T, OUTPUT = (
        "INPUT", "EXTENT", "USE_SCL", "WATER", "NDWI_T", "OUTPUT")

    def createInstance(self):
        return PrepareSentinel2()

    def name(self):
        return "prepare_sentinel2_l2a"

    def displayName(self):
        return "Prepare Sentinel-2 L2A reflectance"

    def group(self):
        return "2. Preprocessing"

    def groupId(self):
        return "preprocessing"

    def shortHelpString(self):
        return (
            CREDIT + "\n\n" +
            "Reads a Sentinel-2 L2A zip (as downloaded, no need to unzip), clips it and "
            "writes a 4-band surface reflectance GeoTIFF: 1 blue (B02), 2 green (B03), "
            "3 red (B04), 4 NIR (B08), 10 m.\n\n"
            "The BOA_ADD_OFFSET of processing baseline 04.00+ is read from the metadata "
            "and applied.\n\n"
            "Cloud mask: Scene Classification (SCL) classes 0, 1, 3, 8, 9, 10, 11 are "
            "removed. Careful: SCL can label very bright shallow bottoms (white sand) "
            "as cloud. Check it over your site.\n\n"
            "Water mask: keeps pixels with NDWI (green-NIR)/(green+NIR) above the "
            "threshold. Very shallow bright bottoms can fail this too.\n\n"
            "Area: use the extent (canvas, layer or drawn rectangle) and/or a polygon "
            "layer. With a polygon, everything outside it becomes nodata; tick "
            "'Selected features only' to use just some polygons. If both are given, "
            "the intersection is used.\n\n"
            "Sunglint correction is a separate tool (Sunglint correction, Hedley).")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(
            self.INPUT, "Sentinel-2 L2A zip", extension="zip"))
        self.addParameter(QgsProcessingParameterExtent(
            self.EXTENT, "Clip extent (canvas, layer or drawn)", optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.AREA, "Area polygon (outside becomes nodata)",
            [SRC_POLYGON], optional=True))
        self.addParameter(QgsProcessingParameterBoolean(self.USE_SCL, "Mask clouds with SCL", True))
        self.addParameter(QgsProcessingParameterBoolean(self.WATER, "Mask land with NDWI", True))
        self.addParameter(QgsProcessingParameterNumber(
            self.NDWI_T, "NDWI threshold", NUM_DOUBLE, 0.0,
            minValue=-1, maxValue=1))
        self.addParameter(QgsProcessingParameterRasterDestination(self.OUTPUT, "Reflectance"))

    def processAlgorithm(self, parameters, context, feedback):
        zip_path = self.parameterAsFile(parameters, self.INPUT, context)
        out = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        try:
            wkt = s2safe.crs_wkt(zip_path)
        except s2safe.SafeError as e:
            raise QgsProcessingException(str(e))

        crs = QgsCoordinateReferenceSystem.fromWkt(wkt)
        ext = None
        if parameters.get(self.EXTENT):
            ext = self.parameterAsExtent(parameters, self.EXTENT, context, crs)
        geom = None
        source = self.parameterAsSource(parameters, self.AREA, context)
        if source is not None:
            geom = union_geometry(source, crs, context, feedback)
        box = combine(ext, geom)
        bounds = None
        if box is not None:
            bounds = (box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum())
        else:
            feedback.pushWarning("No extent or area: processing the whole tile (about 110 x 110 km).")

        try:
            stats = s2safe.prepare(
                zip_path, out, bounds=bounds,
                use_scl=self.parameterAsBool(parameters, self.USE_SCL, context),
                water_mask=self.parameterAsBool(parameters, self.WATER, context),
                ndwi_threshold=self.parameterAsDouble(parameters, self.NDWI_T, context),
                log=feedback.pushWarning,
                aoi_wkt=geom.asWkt() if geom is not None else None)
        except s2safe.SafeError as e:
            raise QgsProcessingException(str(e))

        feedback.pushInfo(f"Offsets applied: {stats['offsets']}, quantification {stats['quantification']}")
        tot = max(stats["pixels"], 1)
        feedback.pushInfo(
            f"Valid pixels: {stats['pixels']}. Outside the area polygon: {stats['outside_area']}. Masked as cloud/shadow: {stats['masked_cloud']} "
            f"({100 * stats['masked_cloud'] / tot:.1f}%). Masked as land: {stats['masked_land']} "
            f"({100 * stats['masked_land'] / tot:.1f}%). Water left: {stats['valid_water']}.")
        return {self.OUTPUT: out}
