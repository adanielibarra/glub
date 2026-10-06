
from qgis.core import (QgsApplication,
                       QgsProcessingParameterFeatureSource, QgsAuthMethodConfig,
                       QgsCoordinateReferenceSystem, QgsProcessingAlgorithm,
                       QgsProcessingException, QgsProcessingOutputString,
                       QgsProcessingParameterAuthConfig,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterExtent,
                       QgsProcessingParameterFolderDestination,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterString)

from ..compat import NUM_DOUBLE, NUM_INTEGER, SRC_POLYGON
from ..author import CREDIT
from ..core import cdse
from .aoi import combine, union_geometry


class DownloadSentinel2(QgsProcessingAlgorithm):
    EXTENT, START, END, LEVEL, MAX_CLOUD, MAX_PRODUCTS = (
        "EXTENT", "START", "END", "LEVEL", "MAX_CLOUD", "MAX_PRODUCTS")
    AUTH, LIST_ONLY, OUTPUT, PRODUCTS = "AUTH", "LIST_ONLY", "OUTPUT", "PRODUCTS"
    LEVELS = ["L2A", "L1C"]

    def createInstance(self):
        return DownloadSentinel2()

    def name(self):
        return "download_sentinel2"

    def displayName(self):
        return "Download Sentinel-2 (Copernicus Data Space)"

    def group(self):
        return "1. Download"

    def groupId(self):
        return "download"

    def shortHelpString(self):
        return (
            CREDIT + "\n\n" +
            "Searches and downloads Sentinel-2 products from the Copernicus Data Space "
            "Ecosystem (free account required).\n\n"
            "Credentials: create a QGIS authentication configuration of type 'Basic' "
            "with your CDSE username and password and pick it here. This keeps the "
            "password out of the Processing history.\n\n"
            "L2A is surface reflectance (ready for the standard path). L1C is top of "
            "atmosphere and is meant for ACOLITE (later phase).\n\n"
            "Duplicates (same tile and date, different processing baseline) are "
            "removed, keeping the newest baseline. Products are sorted by cloud cover "
            "and the clearest ones are downloaded first.\n\n"
            "Area: an extent (canvas, layer or drawn) and/or a polygon layer. The search "
            "uses their bounding box; the exact polygon is applied later, in the "
            "Prepare step.\n\n"
            "Tick 'Only list' to see what would be downloaded without downloading.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterExtent(
            self.EXTENT, "Search extent (canvas, layer or drawn)", optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(
            "AREA", "Area polygon", [SRC_POLYGON], optional=True))
        self.addParameter(QgsProcessingParameterString(self.START, "Start date (YYYY-MM-DD)", "2025-06-01"))
        self.addParameter(QgsProcessingParameterString(self.END, "End date (YYYY-MM-DD)", "2025-08-31"))
        self.addParameter(QgsProcessingParameterEnum(self.LEVEL, "Processing level", self.LEVELS, defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_CLOUD, "Maximum tile cloud cover (%)",
            NUM_DOUBLE, 20.0, minValue=0, maxValue=100))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_PRODUCTS, "Maximum products to download",
            NUM_INTEGER, 3, minValue=1, maxValue=200))
        self.addParameter(QgsProcessingParameterAuthConfig(self.AUTH, "CDSE credentials (Basic auth config)"))
        self.addParameter(QgsProcessingParameterBoolean(self.LIST_ONLY, "Only list, do not download", False))
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUTPUT, "Output folder"))
        self.addOutput(QgsProcessingOutputString(self.PRODUCTS, "Downloaded files"))

    @staticmethod
    def _check_date(s):
        import datetime
        try:
            datetime.date.fromisoformat(s.strip())
        except ValueError:
            raise QgsProcessingException(f"Bad date '{s}', use YYYY-MM-DD.")
        return s.strip()

    def processAlgorithm(self, parameters, context, feedback):
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        ext = None
        if parameters.get(self.EXTENT):
            ext = self.parameterAsExtent(parameters, self.EXTENT, context, wgs84)
        source = self.parameterAsSource(parameters, "AREA", context)
        geom = union_geometry(source, wgs84, context, feedback) if source is not None else None
        ext = combine(ext, geom)
        if ext is None:
            raise QgsProcessingException("Give a search extent or an area polygon.")
        start = self._check_date(self.parameterAsString(parameters, self.START, context))
        end = self._check_date(self.parameterAsString(parameters, self.END, context))
        level = self.LEVELS[self.parameterAsEnum(parameters, self.LEVEL, context)]
        max_cloud = self.parameterAsDouble(parameters, self.MAX_CLOUD, context)
        max_products = self.parameterAsInt(parameters, self.MAX_PRODUCTS, context)
        list_only = self.parameterAsBool(parameters, self.LIST_ONLY, context)
        out_dir = self.parameterAsString(parameters, self.OUTPUT, context)

        wkt = cdse.bbox_to_wkt(ext.xMinimum(), ext.yMinimum(), ext.xMaximum(), ext.yMaximum())
        feedback.pushInfo(f"Searching Sentinel-2 {level}, {start} to {end}, cloud <= {max_cloud}%")
        try:
            products = cdse.search(wkt, start, end, level=level, max_cloud=max_cloud)
        except cdse.CDSEError as e:
            raise QgsProcessingException(str(e))

        if not products:
            feedback.reportError("No products found. Try a wider date range or more cloud.")
            return {self.OUTPUT: out_dir, self.PRODUCTS: ""}

        products.sort(key=lambda p: (p["cloud"] if p["cloud"] is not None else 999))
        feedback.pushInfo(f"{len(products)} products found (after removing duplicates):")
        for p in products:
            size = f"{p['size'] / 1e6:.0f} MB" if p["size"] else "? MB"
            feedback.pushInfo(f"  {p['name']}  cloud={p['cloud']}%  {size}")

        if list_only:
            return {self.OUTPUT: out_dir, self.PRODUCTS: ""}

        authid = self.parameterAsString(parameters, self.AUTH, context)
        if not authid:
            raise QgsProcessingException("Pick a CDSE authentication configuration.")
        cfg = QgsAuthMethodConfig()
        if not QgsApplication.authManager().loadAuthenticationConfig(authid, cfg, True):
            raise QgsProcessingException("Could not load the authentication configuration.")
        user, pwd = cfg.config("username"), cfg.config("password")
        if not user or not pwd:
            raise QgsProcessingException("The auth configuration must be 'Basic' with username and password.")

        todo = [p for p in products if p.get("online", True)][:max_products]
        done = []
        for i, p in enumerate(todo):
            if feedback.isCanceled():
                break
            feedback.pushInfo(f"Downloading {i + 1}/{len(todo)}: {p['name']}")
            try:
                token = cdse.get_token(user, pwd)  # fresh token each time, they expire in minutes
                path = cdse.download(
                    p, out_dir, token,
                    progress=lambda f, i=i: feedback.setProgress(100 * (i + f) / len(todo)),
                    is_canceled=feedback.isCanceled)
            except cdse.CDSEError as e:
                feedback.reportError(str(e))
                continue
            done.append(path)
            feedback.pushInfo(f"  saved: {path}")

        return {self.OUTPUT: out_dir, self.PRODUCTS: ";".join(done)}
