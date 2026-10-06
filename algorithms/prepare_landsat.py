from qgis.core import (QgsCoordinateReferenceSystem, QgsProcessingAlgorithm,
                       QgsProcessingException, QgsProcessingParameterBoolean,
                       QgsProcessingParameterExtent,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFile, QgsProcessingParameterNumber,
                       QgsProcessingParameterRasterDestination)

from ..author import CREDIT
from ..compat import NUM_DOUBLE, SRC_POLYGON
from ..core import landsat
from .aoi import combine, set_core_lang, union_geometry


class PrepareLandsat(QgsProcessingAlgorithm):
    def createInstance(self):
        return PrepareLandsat()

    def name(self):
        return "prepare_landsat_l2"

    def displayName(self):
        return "Prepare Landsat 4-9 Collection 2 Level-2 reflectance"

    def group(self):
        return "2. Preprocessing"

    def groupId(self):
        return "preprocessing"

    def shortHelpString(self):
        return (CREDIT + "\n\n"
                "Reads a Landsat 4, 5, 7, 8 or 9 Collection 2 Level-2 product from USGS (the .tar bundle as "
                "downloaded, the unpacked folder, or any file of it) and writes the same 4-band surface "
                "reflectance GeoTIFF as the Sentinel-2 tool: 1 blue, 2 green, 3 red, 4 NIR, at 30 m.\n\n"
                "Bands: SR_B2-B5 for Landsat 8/9, SR_B1-B4 for Landsat 4/5/7. Reflectance = DN x 2.75e-05 - 0.2 "
                "(read from the MTL file when present). Cloud mask: QA_PIXEL bits fill, dilated cloud, cirrus, "
                "cloud, cloud shadow and snow. Water mask: NDWI above the threshold.\n\n"
                "Landsat 7 after May 2003 has gaps in stripes (SLC-off), left as no data. Landsat reaches back "
                "to 1984 (TM), useful for long change series; its 30 m pixels are coarser than Sentinel-2's 10 m.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile("INPUT", "Landsat product (.tar, folder file or MTL)"))
        self.addParameter(QgsProcessingParameterExtent("EXTENT", "Clip extent", optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource("AREA", "Area polygon (outside becomes nodata)",
                                                              [SRC_POLYGON], optional=True))
        self.addParameter(QgsProcessingParameterBoolean("USE_QA", "Mask clouds with QA_PIXEL", True))
        self.addParameter(QgsProcessingParameterBoolean("WATER", "Mask land with NDWI", True))
        self.addParameter(QgsProcessingParameterNumber("NDWI_T", "NDWI threshold", NUM_DOUBLE, 0.0,
                                                       minValue=-1, maxValue=1))
        self.addParameter(QgsProcessingParameterRasterDestination("OUTPUT", "Reflectance"))

    def processAlgorithm(self, parameters, context, feedback):
        set_core_lang()
        path = self.parameterAsFile(parameters, "INPUT", context)
        out = self.parameterAsOutputLayer(parameters, "OUTPUT", context)
        try:
            crs = QgsCoordinateReferenceSystem.fromWkt(landsat.crs_wkt(path))
        except landsat.LandsatError as e:
            raise QgsProcessingException(str(e))
        ext = self.parameterAsExtent(parameters, "EXTENT", context, crs) if parameters.get("EXTENT") else None
        src = self.parameterAsSource(parameters, "AREA", context)
        geom = union_geometry(src, crs, context, feedback) if src is not None else None
        box = combine(ext, geom)
        bounds = None if box is None else (box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum())
        if bounds is None:
            feedback.pushWarning("No extent or area: processing the whole scene (about 185 x 180 km).")

        def log(msg, warn=False):
            (feedback.pushWarning if warn else feedback.pushInfo)(msg)

        try:
            st = landsat.prepare(path, out, bounds=bounds,
                                 use_qa=self.parameterAsBool(parameters, "USE_QA", context),
                                 water_mask=self.parameterAsBool(parameters, "WATER", context),
                                 ndwi_threshold=self.parameterAsDouble(parameters, "NDWI_T", context),
                                 log=log, aoi_wkt=geom.asWkt() if geom is not None else None)
        except landsat.LandsatError as e:
            raise QgsProcessingException(str(e))
        feedback.pushInfo(f"Valid pixels: {st['pixels']}. Outside the area: {st['outside_area']}. Cloud/shadow: "
                          f"{st['masked_cloud']}. Land: {st['masked_land']}. Water left: {st['valid_water']}.")
        return {"OUTPUT": out}
