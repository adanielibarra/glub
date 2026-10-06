"""Home tab: logos, language selector and instructions."""
import configparser
import os

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
                                 QTextBrowser, QVBoxLayout, QWidget)

from ..author import AUTHOR, COAUTHORS
from . import i18n
from .common import Translatable
from .i18n import tr

PLUGIN_DIR = os.path.dirname(os.path.dirname(__file__))
LOGO_HEIGHT = 96
INST_HEIGHT = 56


def is_simple():
    """Simple mode unless the user chose advanced (saved setting)."""
    try:
        from qgis.core import QgsSettings
        return QgsSettings().value("GLUB/mode", "simple") != "advanced"
    except Exception:
        return True


def plugin_version():
    cp = configparser.ConfigParser()
    try:
        cp.read(os.path.join(PLUGIN_DIR, "metadata.txt"), encoding="utf-8")
        return cp.get("general", "version")
    except Exception:
        return "?"


def _person(p, lang):
    links = [f"ORCID <a href='https://orcid.org/{p['orcid']}'>{p['orcid']}</a>"] if p.get("orcid") else []
    if p.get("scholar"):
        links.append(f"<a href='{p['scholar']}'>Google Scholar</a>")
    if p.get("researchgate"):
        links.append(f"<a href='{p['researchgate']}'>ResearchGate</a>")
    if p.get("github"):
        links.append(f"GitHub <a href='https://github.com/{p['github']}'>{p['github']}</a>")
    mail = f"<br><a href='mailto:{p['email']}'>{p['email']}</a>" if p.get("email") else ""
    aff = f"<br>{p['affiliation']}" if p.get("affiliation") else ""
    lk = f"<br>{' · '.join(links)}" if links else ""
    return f"<p><b>{p['name']}</b>{aff}{mail}{lk}</p>"


def credits_html(lang):
    people = [AUTHOR] + COAUTHORS
    head = "Créditos" if lang == "es" else "Credits"
    made = "Autores" if lang == "es" else "Authors"
    data = ("Datos: contiene datos modificados de Copernicus Sentinel [año de los datos], servidos por el "
            "Copernicus Data Space Ecosystem." if lang == "es" else
            "Data: contains modified Copernicus Sentinel data [year of the data], served by the "
            "Copernicus Data Space Ecosystem.")
    return (f"<h3>{head}</h3><p>{made}:</p>"
            + "".join(_person(p, lang) for p in people) + f"<p>{data}</p>")


HTML = {
    "es": """
<h3>Qué es GLUB! (GIS Looking Under the Blue)</h3>
<p>Cartografía de fondos someros desde satélite: descarga Sentinel-2, prepara la reflectancia, corrige la
columna de agua y clasifica el fondo (pradera, arena, roca...) con tu verdad de campo. Va de la mano de
<b>StarShoal</b>: su batimetría sirve para decidir dónde se ve el fondo.</p>
<p><b>Lo realista con Sentinel-2 es pradera / no pradera</b> en agua clara y somera. Distinguir especies
(<i>Posidonia</i> frente a <i>Cymodocea</i>) o pradera viva frente a mata muerta es mucho menos fiable.</p>

<h3>Pestañas 1 a 3 · Descarga, Preparar, Sunglint</h3>
<p>Las mismas que StarShoal: Sentinel-2 del Copernicus Data Space (L2A o L1C para ACOLITE), recorte y máscara
de nubes y tierra, importación de ACOLITE y corrección de brillo de Hedley et al. (2005). Para publicar,
mejor ACOLITE que Sen2Cor. La pestaña 2 lee también <b>Landsat 4-9</b> (Collection 2 Level-2 de USGS, a 30 m,
desde 1984), que se descarga aparte en EarthExplorer, y <b>cualquier ráster de reflectancia</b> con azul, verde,
rojo e infrarrojo cercano (PlanetScope, dron, otros sensores).</p>
<p><b>Modo sencillo o avanzado</b> (arriba a la derecha): el sencillo solo enseña lo imprescindible; el avanzado,
todas las opciones. Los botones <b>?</b> abren el manual en el apartado de cada pestaña o grupo.</p>
<p>Todas las pestañas tienen <b>Guardar ajustes</b> y <b>Cargar ajustes</b>; la clasificación, la validación y los
cambios los guardan solos junto a sus resultados.</p>

<h3>Pestaña 4 · Compuesto (opcional)</h3>
<p>Mediana de varias fechas, píxel a píxel. Quita nubes sueltas, espuma y turbidez de un día. Corrige el
sunglint de cada fecha <b>antes</b> de componer. Lee la fecha de cada escena y avisa si abarcan demasiados
días, varias estaciones o varios años (la <i>Cymodocea</i> cambia a lo largo del año).</p>
<p>Con un polígono de agua profunda (y, mejor, otro sobre arena a pocos metros) <b>ordena las escenas por
transparencia del agua</b>: mide el contraste del fondo frente al agua profunda y marca las dudosas (turbias,
ruidosas o con nube sobre el fondo). No quita nada si no se lo pides.</p>

<h3>Pestaña 5 · Columna de agua</h3>
<p>Índice de fondo invariante con la profundidad de Lyzenga (1981). Con un polígono de <b>un solo fondo</b>
(arena) visto a varias profundidades, calcula la relación de atenuación entre bandas y escribe un índice
por cada par. Mira la correlación del registro: si es baja, la muestra no vale. Con Sentinel-2 solo azul y
verde llegan bien al fondo, así que suele salir un único índice útil. Donde R queda por debajo de R∞ el
logaritmo no existe: en vez de dejar huecos se pone un suelo y esos píxeles se marcan en un
<code>_floored.tif</code>. Si caen muchos sobre pradera, ese fondo es más oscuro que el agua y el índice de
Lyzenga no le va bien.</p>

<h3>Pestaña 6 · Clasificación</h3>
<ul>
<li>Variables: bandas de reflectancia y/o los índices de la pestaña 5.</li>
<li>Verdad de campo: puntos o polígonos con un campo de clase. Los píxeles de un mismo polígono van
siempre juntos a calibración o a validación.</li>
<li><b>Máscara de tres estados</b>: <i>fondo visible</i> (se clasifica), <i>fondo no visible</i> (sin dato)
y <i>demasiado hondo</i> (sin pradera). El límite óptico sale de una batimetría (la de StarShoal, con su
límite y su capa de confianza); el ecológico (35 m por defecto, cámbialo según tu costa) necesita una
batimetría <b>independiente</b> (EMODnet, carta, multihaz). Con solo el SDB, lo que pasa del límite óptico
queda como sin dato: un SDB no distingue 25 m de 40 m.</li>
<li><b>Prueba de señal</b> (recomendada): con un polígono de agua ópticamente profunda, un píxel solo cuenta
como visible si se separa de esa agua en alguna banda. Así el límite depende del fondo: una pradera oscura
deja de verse antes que la arena.</li>
<li>Random Forest (con scikit-learn) o máxima verosimilitud (solo numpy).</li>
<li>Opcional: encoger los polígonos de verdad de campo para quitar píxeles de borde, y limpiar el mapa final con
filtro de mayoría y unidad mínima (se guarda aparte, <code>classes_filtered.tif</code>).</li>
<li>Validación por bloques espaciales por clase, por bloques comunes a todas las clases (separación
espacial completa) o al azar. Con polígonos, la exactitud principal es <b>por polígono</b>
(voto de la mayoría de sus píxeles); la de píxeles sale más alta de lo real. Informe con matriz de confusión,
exactitud del productor y del usuario, F1, exactitud por tramos de profundidad (con la batimetría independiente si la hay, porque el SDB lee más
honda la pradera) y superficies corregidas por el error
(Olofsson et al., 2014).</li>
<li>Opcional: <b>exportar a polígonos</b> (GeoPackage con clase, superficie y perímetro de cada mancha).</li>
<li>Opcional: <b>textura del fondo</b> (desviación típica local en 3×3 o 5×5 de los índices de columna de agua,
o del azul y el verde). Ayuda con fondos a manchas frente a fondos lisos de color parecido; con píxeles de 10 m
puede aportar poco, así que compara con y sin ella.</li>
<li>Opcional: <b>probabilidad mínima</b>. Si ninguna clase llega a ella, el píxel queda "sin clasificar (baja
confianza)" en vez de forzar una clase.</li>
<li>Salidas: clases (con estilo), probabilidad por clase, leyenda con superficies, muestras en CSV e informe
HTML.</li>
</ul>

<h3>Pestaña 7 · Validación</h3>
<ul>
<li><b>Generar puntos</b>: puntos al azar dentro de cada clase del mapa (muestreo aleatorio estratificado,
Olofsson et al., 2014), con el tamaño de muestra calculado o a mano, un mínimo por clase y distancia mínima
dentro de cada clase. Salen en un GeoPackage con un campo <code>ref_class</code> vacío y lon/lat para el GPS.</li>
<li>Etiqueta los puntos en campo (o con mejor imagen) <b>sin mirar el mapa</b>, con los mismos nombres de
clase.</li>
<li><b>Evaluar el mapa</b>: exactitud global, del usuario y del productor ponderadas por superficie, y la
superficie de cada clase corregida con su intervalo del 95 %. Con estos puntos sí son estimaciones válidas.</li>
</ul>

<h3>Pestaña 8 · Cambios</h3>
<p>Compara dos mapas de clases del mismo sitio (fecha 1 → fecha 2): mapa de transiciones (pérdida de pradera en
rojo, ganancia en verde), matriz en hectáreas y ganancias y pérdidas por clase. Solo compara donde el fondo está
clasificado en las dos fechas. El cambio cartografiado es orientativo, porque los errores de los dos mapas se
suman; para cifras que publicar, lleva el mapa de cambios a la pestaña 7.</p>

<h3>Limitaciones</h3>
<ul>
<li>El límite inferior de las praderas suele quedar más hondo que el límite óptico: este mapa no dice
dónde acaba la pradera en profundidad.</li>
<li>Pradera, macroalgas, roca con epífitos y mata muerta se parecen, y más cuanto más hondo.</li>
<li>Píxeles de 10 m: manchas pequeñas y bordes son píxeles mezclados.</li>
<li>La verdad de campo debe ser de fechas cercanas a la imagen.</li>
<li>Las superficies corregidas de la pestaña 6 suponen un muestreo probabilístico; con puntos tomados donde se
pudo, son orientativas. Para cifras que publicar, usa la pestaña 7.</li>
<li>Probado con datos sintéticos y en QGIS 3.34; no probado aún con datos reales de campo.</li>
</ul>
<p>Todas las herramientas están también en la caja de Processing (GLUB).</p>
""",
    "en": """
<h3>What GLUB! (GIS Looking Under the Blue) is</h3>
<p>Shallow seabed mapping from satellite: it downloads Sentinel-2, prepares the reflectance, corrects for
the water column and classifies the bottom (seagrass, sand, rock...) with your reference data. It works
together with <b>StarShoal</b>: its bathymetry tells where the bottom is visible.</p>
<p><b>With Sentinel-2 the realistic target is seagrass / not seagrass</b> in clear, shallow water.
Separating species (<i>Posidonia</i> from <i>Cymodocea</i>) or live meadow from dead matte is much less
reliable.</p>

<h3>Tabs 1 to 3 · Download, Prepare, Sunglint</h3>
<p>The same as StarShoal: Sentinel-2 from the Copernicus Data Space (L2A, or L1C for ACOLITE), clipping and
cloud and land masks, ACOLITE import and the Hedley et al. (2005) glint correction. For publication, ACOLITE
is better than Sen2Cor. Tab 2 also reads <b>Landsat 4-9</b> (USGS Collection 2 Level-2, 30 m, since 1984),
downloaded separately from EarthExplorer, and <b>any reflectance raster</b> with blue, green, red and near infrared
(PlanetScope, drone, other sensors).</p>
<p><b>Simple or advanced mode</b> (top right): simple shows only the essentials; advanced, every option. The
<b>?</b> buttons open the manual at the section of each tab or group.</p>
<p>Every tab has <b>Save settings</b> and <b>Load settings</b>; classification, validation and change also save
them on their own next to their results.</p>

<h3>Tab 4 · Composite (optional)</h3>
<p>Per-pixel median of several dates. It removes stray clouds, foam and one-day turbidity. Correct the
glint of each date <b>before</b> compositing. It reads the date of each scene and warns when they span
too many days, several seasons or several years (<i>Cymodocea</i> changes over the year).</p>
<p>With a deep-water polygon (and, better, another over sand a few metres deep) it <b>ranks the scenes by water
clarity</b>: it measures the bottom contrast against deep water and flags doubtful ones (turbid, noisy or with
cloud over the bottom). It removes nothing unless you ask.</p>

<h3>Tab 5 · Water column</h3>
<p>Lyzenga (1981) depth-invariant bottom index. With a polygon over <b>one bottom type</b> (sand) seen at
several depths, it computes the attenuation ratio between bands and writes one index per pair. Check the
correlation in the log: if it is low, the sample is not good. With Sentinel-2 only blue and green reach the
bottom well, so there is usually a single useful index. Where R falls below R_inf the logarithm does not
exist: instead of holes, a floor is applied and those pixels are flagged in a <code>_floored.tif</code>. If
many fall on seagrass, that bottom is darker than the water and the Lyzenga index does not suit it.</p>

<h3>Tab 6 · Classification</h3>
<ul>
<li>Features: reflectance bands and/or the indices of tab 5.</li>
<li>Reference data: points or polygons with a class field. The pixels of one polygon always go together
to calibration or validation.</li>
<li><b>Three-state mask</b>: <i>bottom visible</i> (classified), <i>bottom not visible</i> (no data) and
<i>too deep</i> (no seagrass). The optical limit comes from a bathymetry (StarShoal's, with its limit and
trust layer); the ecological one (35 m by default, change it for your coast) needs an <b>independent</b>
bathymetry (EMODnet, chart, multibeam). With only the SDB, what lies past the optical limit stays no data:
an SDB cannot tell 25 m from 40 m.</li>
<li><b>Signal test</b> (advised): with a polygon of optically deep water, a pixel counts as visible only if it
differs from that water in some band. The limit then depends on the bottom: a dark meadow fades before
sand does.</li>
<li>Random Forest (with scikit-learn) or maximum likelihood (numpy only).</li>
<li>Optional: shrink the reference polygons to drop edge pixels, and clean the final map with a majority filter
and a minimum mapping unit (saved separately, <code>classes_filtered.tif</code>).</li>
<li>Validation with spatial blocks by class, common blocks for every class (full spatial separation) or
random. With polygons, the main accuracy is <b>by polygon</b> (majority
vote of its pixels); the pixel figure is higher than the real one. Report with confusion matrix, producer's
and user's accuracy, F1, accuracy by depth range (with the independent bathymetry when given, since an SDB reads meadows as
deeper) and error-corrected areas (Olofsson et al., 2014).</li>
<li>Optional: <b>export to polygons</b> (GeoPackage with class, area and perimeter of each patch).</li>
<li>Optional: <b>bottom texture</b> (local standard deviation in 3×3 or 5×5 of the water-column indices, or of
blue and green). It helps with patchy versus smooth bottoms of similar colour; with 10 m pixels it may add little,
so compare with and without it.</li>
<li>Optional: <b>minimum probability</b>. If no class reaches it, the pixel is left "unclassified (low
confidence)" instead of forcing a class.</li>
<li>Outputs: classes (styled), per-class probability, legend with areas, samples as CSV and an HTML
report.</li>
</ul>

<h3>Tab 7 · Validation</h3>
<ul>
<li><b>Generate points</b>: random points within each map class (stratified random sampling, Olofsson et
al., 2014), with the sample size computed or by hand, a minimum per class and a minimum distance within each
class. They come in a GeoPackage with an empty <code>ref_class</code> field and lon/lat for the GPS.</li>
<li>Label the points in the field (or on better imagery) <b>without looking at the map</b>, with the same class
names.</li>
<li><b>Assess the map</b>: overall, user's and producer's accuracy weighted by area, and the area of each class
corrected with its 95 % interval. With these points they are valid estimates.</li>
</ul>

<h3>Tab 8 · Change</h3>
<p>Compares two class maps of the same place (date 1 → date 2): transition map (seagrass loss in red, gain in
green), matrix in hectares and gains and losses by class. It only compares where the bottom is classified on both
dates. Mapped change is indicative, because the errors of the two maps add up; for figures to publish, take the
change map to tab 7.</p>

<h3>Limitations</h3>
<ul>
<li>The lower edge of meadows usually lies deeper than the optical limit: this map does not show where
meadows end in depth.</li>
<li>Seagrass, macroalgae, rock with epiphytes and dead matte look alike, more so in deeper water.</li>
<li>10 m pixels: small patches and edges are mixed pixels.</li>
<li>Reference data should be close in date to the image.</li>
<li>The corrected areas of tab 6 assume a probability sample; with points taken where it was possible, they
are indicative. For figures to publish, use tab 7.</li>
<li>Tested with synthetic data and in QGIS 3.34; not yet tested with real field data.</li>
</ul>
<p>Every tool is also in the Processing Toolbox (GLUB).</p>
""",
}


class HomeTab(QWidget, Translatable):
    languageChanged = pyqtSignal(str)
    modeChanged = pyqtSignal(bool)   # True = simple

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)

        head = QHBoxLayout()
        logo = QLabel()
        pm = QPixmap(os.path.join(PLUGIN_DIR, "about", "glub.png"))
        if not pm.isNull():
            logo.setPixmap(pm.scaledToHeight(LOGO_HEIGHT, Qt.TransformationMode.SmoothTransformation))
        head.addWidget(logo)
        head.addSpacing(12)
        tbox = QVBoxLayout()
        tbox.addWidget(QLabel("<span style='font-size:18pt; font-weight:600'>GLUB!</span>"
                              "<span style='font-size:11pt; color:gray'>&nbsp;&nbsp;GIS Looking Under the Blue</span>"))
        self.subtitle = QLabel()
        self._t(self.subtitle.setText, "home.subtitle")
        self.version = QLabel()
        self._t(self.version.setText, "home.version", plugin_version())
        tbox.addWidget(self.subtitle)
        tbox.addWidget(self.version)
        head.addLayout(tbox)
        head.addStretch()
        self.btn_manual = QPushButton()
        self._t(self.btn_manual.setText, "home.manual")
        self.btn_manual.clicked.connect(self._open_manual)
        head.addWidget(self.btn_manual)
        head.addSpacing(16)
        head.addWidget(self._lbl("home.language"))
        self.cb_lang = QComboBox()
        for code, name in i18n.LANGS.items():
            self.cb_lang.addItem(name, code)
        self.cb_lang.setCurrentIndex(self.cb_lang.findData(i18n.lang()))
        self.cb_lang.currentIndexChanged.connect(self._lang_changed)
        head.addWidget(self.cb_lang)
        head.addSpacing(16)
        head.addWidget(self._lbl("home.mode"))
        self.cb_mode = QComboBox()
        self._t(self.cb_mode.setToolTip, "home.mode.tip")
        self.cb_mode.addItems([tr("home.mode.simple"), tr("home.mode.adv")])
        self.cb_mode.setCurrentIndex(0 if is_simple() else 1)
        self.cb_mode.currentIndexChanged.connect(self._mode_changed)
        head.addWidget(self.cb_mode)
        lay.addLayout(head)

        # institutional logos on a white strip (they are made for a light background)
        strip = QFrame()
        strip.setObjectName("sbLogoStrip")
        strip.setStyleSheet("#sbLogoStrip { background: white; border-radius: 6px; }")
        hl = QHBoxLayout(strip)
        hl.setContentsMargins(16, 8, 16, 8)
        hl.setSpacing(36)
        hl.addStretch()
        for name in ("uat.png", "fic.png"):
            lab = QLabel()
            pm = QPixmap(os.path.join(PLUGIN_DIR, "about", name))
            if not pm.isNull():
                lab.setPixmap(pm.scaledToHeight(INST_HEIGHT, Qt.TransformationMode.SmoothTransformation))
            else:
                lab.setText(name.split(".")[0].upper())
            hl.addWidget(lab)
        hl.addStretch()
        lay.addWidget(strip)

        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(True)
        lay.addWidget(self.text, 1)
        self._retranslate_extra()

    def _open_manual(self):
        from qgis.PyQt.QtCore import QUrl
        from qgis.PyQt.QtGui import QDesktopServices
        path = os.path.join(PLUGIN_DIR, "docs", f"manual_{i18n.lang()}.pdf")
        if os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _mode_changed(self, i):
        try:
            from qgis.core import QgsSettings
            QgsSettings().setValue("GLUB/mode", "simple" if i == 0 else "advanced")
        except Exception as e:   # the mode still applies in this session
            QgsMessageLog.logMessage(f"Could not save the mode: {e}", "GLUB", Qgis.MessageLevel.Info)
        self.modeChanged.emit(i == 0)

    def _lang_changed(self):
        code = self.cb_lang.currentData()
        i18n.set_lang(code)
        try:
            i18n.save_lang(code)
        except Exception as e:  # not being able to remember the language is not fatal
            from qgis.core import Qgis, QgsMessageLog
            QgsMessageLog.logMessage(f"Could not save the language: {e}", "GLUB", Qgis.MessageLevel.Info)
        self.languageChanged.emit(code)

    def _retranslate_extra(self):
        self.text.setHtml(HTML[i18n.lang()] + credits_html(i18n.lang()))
        if hasattr(self, "cb_mode"):
            i = self.cb_mode.currentIndex()
            self.cb_mode.blockSignals(True)
            self.cb_mode.clear()
            self.cb_mode.addItems([tr("home.mode.simple"), tr("home.mode.adv")])
            self.cb_mode.setCurrentIndex(i)
            self.cb_mode.blockSignals(False)
        idx = self.cb_lang.findData(i18n.lang())
        if idx != self.cb_lang.currentIndex():
            self.cb_lang.blockSignals(True)
            self.cb_lang.setCurrentIndex(idx)
            self.cb_lang.blockSignals(False)
