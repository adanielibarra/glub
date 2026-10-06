"""Minimal ES/EN translation table for the GLUB! window (no Qt Linguist).

tr(key, *args) returns the text in the current language. Unknown keys are
returned as they are, so a missing entry is visible but never breaks anything.
"""

LANGS = {"es": "Español", "en": "English"}
_lang = "es"


def set_lang(code):
    global _lang
    _lang = code if code in LANGS else "es"
    from ..core import lang as core_lang  # log messages and reports follow the window
    core_lang.set_lang(_lang)


def lang():
    return _lang


def tr(key, *args):
    entry = STRINGS.get(key)
    text = key if entry is None else entry[0 if _lang == "es" else 1]
    return text % args if args else text


def default_lang():
    """Spanish unless English was chosen in the Home tab."""
    try:
        from qgis.core import QgsSettings
        saved = QgsSettings().value("GLUB/lang", "")
        return saved if saved in LANGS else "es"
    except Exception:
        return "es"


def save_lang(code):
    from qgis.core import QgsSettings
    QgsSettings().setValue("GLUB/lang", code)


STRINGS = {
    # window and tabs
    "win.title": ("GLUB! · praderas y fondos desde satélite", "GLUB! · seagrass and seabed from satellite"),
    "tab.home": ("Inicio", "Home"),
    "tab.download": ("1 · Descarga", "1 · Download"),
    "tab.prepare": ("2 · Preparar", "2 · Prepare"),
    "tab.deglint": ("3 · Sunglint", "3 · Sunglint"),
    "tab.composite": ("4 · Compuesto", "4 · Composite"),
    "tab.watercol": ("5 · Columna de agua", "5 · Water column"),
    "tab.classify": ("6 · Clasificación", "6 · Classification"),
    "tab.validation": ("7 · Validación", "7 · Validation"),
    "tab.change": ("8 · Cambios", "8 · Change"),
    "menu.open": ("Abrir GLUB!", "Open GLUB!"),
    "menu.processing": ("Herramientas en Processing", "Tools in Processing"),

    # home
    "home.subtitle": ("Cartografía de praderas marinas y fondos someros para QGIS",
                      "Seagrass and shallow seabed mapping for QGIS"),
    "home.version": ("Versión %s", "Version %s"),
    "home.language": ("Idioma:", "Language:"),
    "home.manual": ("Manual (PDF)", "Manual (PDF)"),

    # shared
    "c.area": ("Zona", "Area"),
    "c.layer": ("Capa de polígonos:", "Polygon layer:"),
    "c.layer.tip": ("Opcional. Todo lo que quede fuera del polígono se ignora.",
                    "Optional. Everything outside the polygon is ignored."),
    "c.selected": ("Solo los objetos seleccionados", "Selected features only"),
    "c.extent": ("Extensión:", "Extent:"),
    "c.extent.tip": ("Opcional. Lienzo, capa o rectángulo dibujado. Si das también un polígono, se usa la intersección.",
                     "Optional. Canvas, layer or drawn rectangle. With a polygon too, the intersection is used."),
    "c.none": ("(ninguna)", "(none)"),
    "c.output": ("Salida", "Output"),
    "c.outfile": ("Fichero de salida:", "Output file:"),
    "c.outdir": ("Carpeta de salida:", "Output folder:"),
    "c.addmap": ("Añadir al mapa", "Add to the map"),
    "c.run": ("Ejecutar", "Run"),
    "c.help.tip": ("Ayuda: abre el manual en este apartado", "Help: opens the manual at this section"),
    "home.mode": ("Modo:", "Mode:"),
    "home.mode.simple": ("Sencillo", "Simple"),
    "home.mode.adv": ("Avanzado", "Advanced"),
    "home.mode.tip": ("Sencillo: solo las opciones imprescindibles, con valores por defecto razonables. Avanzado: "
                      "todas. Las opciones ocultas no se pierden: siguen con el valor que tengan.",
                      "Simple: only the essential options, with sensible defaults. Advanced: all of them. Hidden "
                      "options are not lost: they keep whatever value they have."),
    "c.save": ("Guardar ajustes…", "Save settings…"),
    "c.load": ("Cargar ajustes…", "Load settings…"),
    "c.saved": ("Ajustes guardados en %s", "Settings saved to %s"),
    "c.loaded": ("Ajustes cargados de %s", "Settings loaded from %s"),
    "c.load.missing": ("No se ha podido restaurar %s: ponlo a mano.", "Could not restore %s: set it by hand."),
    "c.cancel": ("Cancelar", "Cancel"),
    "c.busy": ("Ya hay un proceso en marcha en esta pestaña.", "A process is already running in this tab."),
    "c.done": ("Terminado.", "Finished."),
    "c.failed": ("Error: %s", "Error: %s"),
    "c.canceled": ("Cancelado.", "Canceled."),
    "c.raster": ("Ráster de reflectancia:", "Reflectance raster:"),
    "c.blue": ("Banda azul:", "Blue band:"),
    "c.green": ("Banda verde:", "Green band:"),
    "c.red": ("Banda roja:", "Red band:"),
    "c.nir": ("Banda NIR:", "NIR band:"),
    "c.image": ("Imagen", "Image"),
    "c.need.raster": ("Elige un ráster.", "Choose a raster."),
    "c.need.out": ("Elige dónde guardar el resultado.", "Choose where to save the result."),
    "c.nooverlap": ("La extensión y el polígono no se solapan.", "The extent and the polygon do not overlap."),
    "c.nopoly": ("La capa de polígonos no tiene polígonos válidos (o no hay ninguno seleccionado).",
                 "The polygon layer has no valid polygons (or none is selected)."),

    # download
    "dl.search": ("Búsqueda", "Search"),
    "dl.from": ("Desde:", "From:"),
    "dl.to": ("Hasta:", "To:"),
    "dl.level": ("Nivel:", "Level:"),
    "dl.level.l2a": ("L2A (reflectancia de superficie)", "L2A (surface reflectance)"),
    "dl.level.l1c": ("L1C (techo de atmósfera, para ACOLITE)", "L1C (top of atmosphere, for ACOLITE)"),
    "dl.cloud": ("Nubes máx. en la tesela:", "Max tile cloud cover:"),
    "dl.account": ("Cuenta de Copernicus Data Space", "Copernicus Data Space account"),
    "dl.auth": ("Credenciales:", "Credentials:"),
    "dl.auth.help": ("Crea una configuración de tipo <b>Basic</b> (botón +) con tu usuario y contraseña de "
                     "<a href='https://dataspace.copernicus.eu'>dataspace.copernicus.eu</a>. "
                     "La cuenta es gratuita. Buscar no la necesita; descargar sí.",
                     "Create a <b>Basic</b> configuration (+ button) with your "
                     "<a href='https://dataspace.copernicus.eu'>dataspace.copernicus.eu</a> username and "
                     "password. The account is free. Searching does not need it; downloading does."),
    "dl.btn.search": ("Buscar escenas", "Search scenes"),
    "dl.btn.download": ("Descargar seleccionadas", "Download selected"),
    "dl.btn.all": ("Todas", "All"),
    "dl.btn.none": ("Ninguna", "None"),
    "dl.col.date": ("Fecha", "Date"),
    "dl.col.tile": ("Tesela", "Tile"),
    "dl.col.cloud": ("Nubes %", "Cloud %"),
    "dl.col.size": ("MB", "MB"),
    "dl.col.name": ("Producto", "Product"),
    "dl.need.area": ("Da una extensión o una capa de polígonos para buscar.", "Give an extent or a polygon layer to search."),
    "dl.need.dir": ("Elige una carpeta de descarga.", "Choose a download folder."),
    "dl.need.auth": ("Elige una configuración de credenciales de Copernicus.", "Choose a Copernicus credentials configuration."),
    "dl.bad.auth": ("La configuración debe ser de tipo Basic, con usuario y contraseña.",
                    "The configuration must be Basic, with username and password."),
    "dl.need.sel": ("Marca al menos una escena.", "Tick at least one scene."),
    "dl.found": ("%d escenas encontradas (sin duplicados).", "%d scenes found (duplicates removed)."),
    "dl.none": ("No hay escenas. Prueba con más fechas o más nubes.", "No scenes. Try a wider date range or more cloud."),
    "dl.searching": ("Buscando en Copernicus Data Space...", "Searching Copernicus Data Space..."),
    "dl.getting": ("Descargando %d/%d: %s", "Downloading %d/%d: %s"),
    "dl.saved": ("  guardado: %s", "  saved: %s"),
    "dl.total": ("Tamaño total marcado: %.0f MB", "Total ticked size: %.0f MB"),

    # prepare
    "pr.input": ("Imagen de entrada", "Input image"),
    "pr.source": ("Origen:", "Source:"),
    "pr.src.l2a": ("Sentinel-2 L2A de Copernicus (Sen2Cor)", "Sentinel-2 L2A from Copernicus (Sen2Cor)"),
    "pr.src.aco": ("Salida de ACOLITE (NetCDF o GeoTIFF)", "ACOLITE output (NetCDF or GeoTIFF)"),
    "pr.src.landsat": ("Landsat 4-9 Collection 2 Level-2 de USGS", "Landsat 4-9 Collection 2 Level-2 from USGS"),
    "pr.landsat.tip": ("El .tar tal como se descarga de USGS EarthExplorer (hace falta cuenta gratuita), la carpeta "
                       "descomprimida o cualquier fichero del producto (el MTL o una banda). Píxeles de 30 m; llega "
                       "hasta 1984 con Landsat 5.",
                       "The .tar as downloaded from USGS EarthExplorer (free account needed), the unpacked folder or "
                       "any file of the product (the MTL or one band). 30 m pixels; it goes back to 1984 with "
                       "Landsat 5."),
    "pr.need.landsat": ("Elige un producto Landsat Collection 2 Level-2 (.tar, MTL o una banda).",
                        "Choose a Landsat Collection 2 Level-2 product (.tar, MTL or one band)."),
    "pr.whole.landsat": ("Sin extensión ni polígono: se procesa la escena entera (unos 185 x 180 km).",
                         "No extent or polygon: the whole scene is processed (about 185 x 180 km)."),
    "pr.src.generic": ("Otro ráster de reflectancia (PlanetScope, dron, otros sensores)",
                       "Other reflectance raster (PlanetScope, drone, other sensors)"),
    "pr.gen.bands": ("Bandas:", "Bands:"),
    "pr.gen.scale": ("Reflectancia = valor ×", "Reflectance = value ×"),
    "pr.gen.offset": ("+", "+"),
    "pr.gen.help": ("Cualquier ráster con azul, verde, rojo e infrarrojo cercano (hace falta el NIR para la máscara "
                    "de agua y el sunglint). Indica qué banda es cada una y cómo pasar los valores a reflectancia "
                    "(0-1): por ejemplo × 0,0001 para PlanetScope guardado como 0-10000. No quita nubes: hazlo antes "
                    "o deja las nubes fuera del polígono de zona. Si la escala no cuadra, el registro avisa.",
                    "Any raster with blue, green, red and near infrared (NIR is needed for the water mask and the "
                    "sunglint). Say which band is which and how to turn the values into reflectance (0-1): for "
                    "example × 0.0001 for PlanetScope stored as 0-10000. Clouds are not removed: do it before or "
                    "leave them outside the area polygon. If the scale does not fit, the log warns."),
    "pr.need.gen": ("Elige un ráster de reflectancia.", "Choose a reflectance raster."),
    "pr.whole.gen": ("Sin extensión ni polígono: se procesa el ráster entero.",
                     "No extent or polygon: the whole raster is processed."),
    "pr.qa": ("Quitar nubes, sombras y nieve con QA_PIXEL", "Remove clouds, shadows and snow with QA_PIXEL"),
    "pr.zip": ("Fichero:", "File:"),
    "pr.quantity": ("Magnitud:", "Quantity:"),
    "pr.quantity.tip": ("rhos: reflectancia de superficie (L2R), la habitual. rhow y Rrs solo si el fichero L2W las trae.",
                        "rhos: surface reflectance (L2R), the usual one. rhow and Rrs only if the L2W file has them."),
    "pr.aco.help": ("ACOLITE es un programa aparte (RBINS, GPL-3). Pásalo sobre un Sentinel-2 L1C (descárgalo en la "
                    "pestaña 1 con nivel L1C) y trae aquí su ..._L2R.nc. No hay máscara de nubes: deja las nubes fuera "
                    "con el polígono. Su corrección de brillo viene desactivada por defecto; si no la activaste, usa la pestaña 3.",
                    "ACOLITE is a separate program (RBINS, GPL-3). Run it on a Sentinel-2 L1C (download it in tab 1 with "
                    "level L1C) and bring here its ..._L2R.nc. There is no cloud mask: leave clouds out with the polygon. "
                    "Its glint correction is off by default; if you did not turn it on, use tab 3."),
    "pr.need.aco": ("Elige un NetCDF de ACOLITE (.nc) o uno de sus GeoTIFF exportados.",
                    "Choose an ACOLITE NetCDF (.nc) or one of its exported GeoTIFFs."),
    "pr.vars": ("Variables usadas: %s", "Variables used: %s"),
    "pr.zip.tip": ("Tal como se descarga, sin descomprimir.", "As downloaded, no need to unzip."),
    "pr.masks": ("Máscaras", "Masks"),
    "pr.scl": ("Quitar nubes y sombras con SCL", "Remove clouds and shadows with SCL"),
    "pr.scl.tip": ("Ojo: SCL puede marcar como nube fondos someros muy claros (arena blanca). Compruébalo en tu zona.",
                   "Careful: SCL can label very bright shallow bottoms (white sand) as cloud. Check it on your site."),
    "pr.ndwi": ("Quitar tierra con NDWI, umbral:", "Remove land with NDWI, threshold:"),
    "pr.need.zip": ("Elige un fichero .zip de Sentinel-2 L2A.", "Choose a Sentinel-2 L2A zip file."),
    "pr.whole": ("Sin extensión ni polígono: se procesa la tesela entera (unos 110 x 110 km).",
                 "No extent or polygon: the whole tile is processed (about 110 x 110 km)."),
    "pr.stats": ("Píxeles: %d. Fuera del polígono: %d. Nubes/sombras: %d. Tierra: %d. Agua útil: %d.",
                 "Pixels: %d. Outside the polygon: %d. Cloud/shadow: %d. Land: %d. Usable water: %d."),

    # deglint
    "dg.deep": ("Muestra de agua profunda", "Deep-water sample"),
    "dg.deep.layer": ("Polígono de agua profunda:", "Deep-water polygon:"),
    "dg.deep.help": ("Agua donde no se vea el fondo y con algo de brillo del sol. Tiene que caer dentro del ráster. "
                     "Si tu zona no tiene agua profunda, prepara antes una extensión mayor.",
                     "Water where the bottom is not visible, with some sunglint. It must fall inside the raster. "
                     "If your area has no deep water, prepare a larger extent first."),
    "dg.pct": ("Percentil de referencia del NIR (0 = mínimo):", "NIR reference percentile (0 = minimum):"),
    "dg.need.deep": ("Elige el polígono de agua profunda.", "Choose the deep-water polygon."),


    # band names and R_inf (shared)
    "ba.b.blue": ("azul", "blue"),
    "ba.b.green": ("verde", "green"),
    "ba.b.red": ("rojo", "red"),
    "ba.b.nir": ("NIR", "NIR"),
    "ba.k": ("R∞ = media − k·σ, k:", "R_inf = mean − k·sd, k:"),

    # composite
    "cp.inputs": ("Rásteres de entrada (preparados y, mejor, ya sin sunglint)",
                  "Input rasters (prepared and, better, already deglinted)"),
    "cp.add": ("Añadir...", "Add..."),
    "cp.addlayers": ("Añadir capas del proyecto", "Add project layers"),
    "cp.remove": ("Quitar", "Remove"),
    "cp.help": ("Mediana píxel a píxel de varias fechas. Quita nubes sueltas, espuma, brillo residual y "
                "turbidez de un día. Todo se remuestrea a la rejilla del primero. Se escribe también un "
                "_count.tif con cuántas fechas valen en cada píxel.",
                "Per-pixel median of several dates. It removes stray clouds, foam, residual glint and one-day "
                "turbidity. Everything is resampled to the grid of the first raster. A _count.tif with the "
                "number of valid dates per pixel is written too."),
    "cp.min": ("Mínimo de fechas válidas por píxel:", "Minimum valid dates per pixel:"),
    "cp.maxdays": ("Avisar si las fechas abarcan más de (días):", "Warn if the dates span more than (days):"),
    "cp.maxdays.tip": ("Solo avisa, no quita escenas. La Cymodocea y la transparencia del agua cambian a lo largo "
                       "del año; también avisa si hay varias estaciones o varios años.",
                       "It only warns, no scene is removed. Cymodocea and water clarity change over the year; it "
                       "also warns about several seasons or years."),
    "cp.need": ("Hacen falta al menos dos rásteres.", "At least two rasters are needed."),

    # water column
    "wc.sand": ("Muestra de fondo uniforme", "Uniform-bottom sample"),
    "wc.sand.layer": ("Polígono de un solo fondo:", "Single-bottom polygon:"),
    "wc.sand.help": ("Un solo tipo de fondo (casi siempre arena) visto a <b>varias profundidades</b>, de lo más "
                     "somero a donde aún se ve el fondo. Con él se calcula la relación de atenuación entre "
                     "bandas (Lyzenga, 1981). Sin rango de profundidades, el índice no vale.",
                     "One bottom type (usually sand) seen at <b>several depths</b>, from the shallowest to where "
                     "the bottom is still visible. It gives the attenuation ratio between bands (Lyzenga, 1981). "
                     "Without a depth range the index is useless."),
    "wc.deep": ("Agua profunda para R∞ (opcional):", "Deep water for R_inf (optional):"),
    "wc.deep.tip": ("Agua donde no se ve el fondo. Sin ella, R∞ = 0.", "Water where the bottom is not seen. Without it, R_inf = 0."),
    "wc.bands": ("Bandas:", "Bands:"),
    "wc.bands.tip": ("Se calcula un índice por cada par. Con Sentinel-2, el rojo solo ve el fondo en los primeros "
                     "metros: en casi todos los sitios basta azul y verde.",
                     "One index per pair. With Sentinel-2, red only sees the bottom in the first metres: in most "
                     "places blue and green are enough."),
    "wc.floor": ("Suelo de R − R∞ (σ del agua profunda):", "Floor of R − R_inf (deep-water sd):"),
    "wc.floor.tip": ("Donde R queda por debajo de R∞ el logaritmo no existe y saldría un hueco. Con suelo, esos "
                     "píxeles toman el valor mínimo y se marcan en un _floored.tif: ahí el índice no mide el "
                     "fondo. Pasa en agua profunda y también con fondos más oscuros que el agua, donde el modelo "
                     "de Lyzenga no vale. 0 = sin suelo (huecos). Solo con polígono de agua profunda.",
                     "Where R falls below R_inf the logarithm does not exist and a hole would appear. With a "
                     "floor, those pixels take the minimum value and are flagged in a _floored.tif: there the "
                     "index does not measure the bottom. It happens in deep water and also over bottoms darker "
                     "than the water, where the Lyzenga model does not hold. 0 = no floor (holes). Only with a "
                     "deep-water polygon."),
    "wc.need.sand": ("Elige el polígono de fondo uniforme.", "Choose the uniform-bottom polygon."),
    "wc.need.bands": ("Marca al menos dos bandas.", "Tick at least two bands."),

    # classification
    "cl.feat": ("Variables", "Features"),
    "cl.refl": ("Reflectancia:", "Reflectance:"),
    "cl.use": ("Bandas de reflectancia:", "Reflectance bands:"),
    "cl.dii": ("Índices de columna de agua (pestaña 5):", "Water-column indices (tab 5):"),
    "cl.dii.tip": ("Opcional, recomendado. Se usan todas sus bandas.", "Optional, recommended. All its bands are used."),
    "cl.depthfeat": ("Usar también la profundidad como variable", "Also use depth as a feature"),
    "cl.depthfeat.tip": ("No recomendado. El error de la batimetría desde satélite depende del color del fondo "
                         "(una pradera oscura parece más honda), así que meterla como variable mete un error "
                         "ligado a las clases. Se usa la capa de profundidad de la máscara.",
                         "Not recommended. The error of satellite-derived depth depends on bottom colour (a dark "
                         "meadow looks deeper), so as a feature it brings an error tied to the classes. The "
                         "optical-mask depth raster is used."),
    "cl.train": ("Verdad de campo", "Reference data"),
    "cl.train.layer": ("Capa de puntos o polígonos:", "Point or polygon layer:"),
    "cl.train.field": ("Campo de clase:", "Class field:"),
    "cl.maxpoly": ("Máx. píxeles por polígono (0 = todos):", "Max pixels per polygon (0 = all):"),
    "cl.train.help": ("Una clase por objeto (pradera, arena, roca...). Solo cuentan las muestras donde se ve el "
                      "fondo: las que caen en zona no visible o demasiado honda se descartan y se avisa.",
                      "One class per feature (seagrass, sand, rock...). Only samples where the bottom is seen "
                      "count: those in the hidden or too-deep zone are dropped with a warning."),
    "cl.shrink": ("Encoger polígonos:", "Shrink polygons:"),
    "cl.shrink.tip": ("Buffer hacia dentro antes de muestrear, para dejar fuera los píxeles del borde, que "
                      "suelen ser mezcla (p. ej. 10 m = un píxel de Sentinel-2). 0 = sin encoger. Los "
                      "polígonos más estrechos que el doble desaparecen y se avisa.",
                      "Inward buffer before sampling, to leave out edge pixels, which are usually mixed "
                      "(e.g. 10 m = one Sentinel-2 pixel). 0 = no shrinking. Polygons narrower than twice "
                      "the value vanish, with a warning."),
    "cp.clar": ("Transparencia del agua de cada escena (opcional)", "Water clarity of each scene (optional)"),
    "cp.clar.deep": ("Polígono de agua profunda:", "Deep-water polygon:"),
    "cp.clar.bottom": ("Polígono de fondo claro (opcional):", "Bright-bottom polygon (optional):"),
    "cp.clar.run": ("Ordenar por transparencia", "Rank by clarity"),
    "cp.clar.drop": ("Quitar las marcadas", "Remove the flagged ones"),
    "cp.clar.need": ("Elige un polígono de agua profunda.", "Choose a deep-water polygon."),
    "cp.clar.help": ("Mide cada escena de la lista en agua profunda (rojo y ruido) y, si das un polígono sobre un "
                     "fondo claro (arena a pocos metros), el contraste del fondo: cuántas desviaciones típicas se "
                     "separa del agua profunda, lo mismo que la prueba de señal. Más contraste = el fondo se ve más "
                     "hondo ese día. Ordena la lista y marca las escenas dudosas, pero no quita nada si no se lo "
                     "pides. Guarda scene_clarity.csv junto a la primera escena.",
                     "Measures each scene of the list over deep water (red and noise) and, with a polygon over a "
                     "bright bottom (sand a few metres deep), the bottom contrast: how many standard deviations it "
                     "stands out from deep water, the same as the signal test. More contrast = the bottom is seen "
                     "deeper that day. It sorts the list and flags doubtful scenes, but removes nothing unless you "
                     "ask. It saves scene_clarity.csv next to the first scene."),
    "ch.maps": ("Mapas de clases de dos fechas", "Class maps of two dates"),
    "ch.map1": ("Fecha 1 (antes):", "Date 1 (before):"),
    "ch.map2": ("Fecha 2 (después):", "Date 2 (after):"),
    "ch.help": ("Dos classes.tif del mismo sitio. Las clases se emparejan por nombre. Solo se compara donde el fondo "
                "está clasificado en las dos fechas: si en alguna es 'no visible', 'demasiado hondo' o 'baja "
                "confianza', queda como 'no comparable', para no confundir agua turbia con pérdida de pradera. El "
                "cambio cartografiado es orientativo: los errores de los dos mapas se suman. Para cifras que "
                "publicar, lleva change.tif a la pestaña 7 y etiqueta los puntos en las dos fechas.",
                "Two classes.tif of the same place. Classes are matched by name. Only pixels where the bottom is "
                "classified on both dates are compared: 'not visible', 'too deep' or 'low confidence' on either date "
                "is 'not comparable', so turbid water is not taken for meadow loss. Mapped change is indicative: "
                "the errors of the two maps add up. For figures to publish, take change.tif to tab 7 and label the "
                "points on both dates."),
    "ch.mmu": ("Unidad mínima de cambio (píxeles):", "Minimum change unit (pixels):"),
    "ch.mmu.tip": ("Las manchas de cambio más pequeñas se unen a la mancha vecina (se guarda aparte, "
                   "change_filtered.tif). 0 o 1 = no.",
                   "Smaller change patches are merged into the neighbouring patch (saved separately, "
                   "change_filtered.tif). 0 or 1 = off."),
    "ch.need": ("Elige dos mapas de clases distintos.", "Choose two different class maps."),
    "ch.res": ("Píxeles comparables: %s; con cambio: %s (%s). Por clase (fecha 1 → fecha 2):",
               "Comparable pixels: %s; changed: %s (%s). By class (date 1 → date 2):"),
    "va.map": ("Mapa", "Map"),
    "va.map.layer": ("Mapa de clases (classes.tif):", "Class map (classes.tif):"),
    "va.mode.gen": ("Generar puntos de validación", "Generate validation points"),
    "va.mode.ass": ("Evaluar el mapa con puntos ya etiquetados", "Assess the map with labelled points"),
    "va.help": ("Primero genera los puntos, etiquétalos en campo (o con mejor imagen) sin mirar el mapa, y luego "
                "evalúa con el mismo mapa. Así la exactitud y las superficies corregidas son estimaciones válidas "
                "(Olofsson et al., 2014).",
                "First generate the points, label them in the field (or on better imagery) without looking at the "
                "map, then assess with the same map. That way accuracy and corrected areas are valid estimates "
                "(Olofsson et al., 2014)."),
    "va.gen": ("Puntos aleatorios estratificados por clase", "Stratified random points by class"),
    "va.n": ("Total de puntos:", "Total points:"),
    "va.n.auto": ("calcular", "compute"),
    "va.se": ("Error típico objetivo de la exactitud global:", "Target standard error of overall accuracy:"),
    "va.ua": ("Exactitud de usuario esperada:", "Expected user's accuracy:"),
    "va.min": ("Mínimo por clase:", "Minimum per class:"),
    "va.mode": ("Reparto:", "Allocation:"),
    "va.mode.prop": ("Proporcional a la superficie, con mínimo", "Proportional to area, with a minimum"),
    "va.mode.equal": ("Igual en todas las clases", "Equal for every class"),
    "va.hidden": ("Puntos en 'fondo no visible' (control):", "Points in 'bottom not visible' (check):"),
    "va.deep": ("Puntos en 'demasiado hondo' (control):", "Points in 'too deep' (check):"),
    "va.dist": ("Distancia mínima dentro de una clase:", "Minimum distance within a class:"),
    "va.out": ("Puntos (GeoPackage):", "Points (GeoPackage):"),
    "va.gen.help": ("Con 'calcular', n = (Σ W·S / EE)², con S = √(U(1−U)): un error típico de 0,02 con U = 0,8 "
                    "da unos 400 puntos. La zona de baja confianza, si la hay, es un estrato más. Los puntos de "
                    "control de la máscara no entran en las superficies. La distancia mínima solo separa puntos de "
                    "la misma clase: los errores se juntan en los bordes y no hay que alejarse de ellos.",
                    "With 'compute', n = (Σ W·S / SE)², with S = √(U(1−U)): a standard error of 0.02 with U = 0.8 "
                    "gives about 400 points. The low-confidence zone, if any, is one more stratum. Mask-check "
                    "points do not enter the areas. The minimum distance only separates points of the same class: "
                    "errors gather at edges and the points must not avoid them."),
    "va.ass": ("Evaluación con puntos etiquetados", "Assessment with labelled points"),
    "va.pts": ("Capa de puntos:", "Point layer:"),
    "va.field": ("Campo de clase de referencia:", "Reference class field:"),
    "va.ass.help": ("Las etiquetas se emparejan con los nombres de clase del mapa (sin mirar mayúsculas ni "
                    "espacios); las que el mapa no tiene quedan como clases aparte. Los puntos sin etiqueta se "
                    "dejan fuera: si faltan los difíciles (hondos, lejanos), las cifras salen sesgadas.",
                    "Labels are matched to the map class names (case and spaces ignored); those the map does not "
                    "have are kept as extra classes. Points without a label are left out: if the hard ones (deep, "
                    "far) are missing, the figures are biased."),
    "va.open": ("Abrir el informe", "Open the report"),
    "va.layer": ("puntos de validación", "validation points"),
    "va.need.map": ("Elige el mapa de clases.", "Choose the class map."),
    "va.need.pts": ("Elige la capa de puntos y el campo de clase.", "Choose the point layer and the class field."),
    "va.res.oa": ("Exactitud global: %s ± %s (95 %%), %s puntos. Superficies estimadas:",
                  "Overall accuracy: %s ± %s (95 %%), %s points. Estimated areas:"),
    "va.res.none": ("Ningún punto útil: revisa las etiquetas y que los puntos caigan en el mapa.",
                    "No usable point: check the labels and that the points fall on the map."),
    "cl.tex": ("Textura del fondo:", "Bottom texture:"),
    "cl.tex.tip": ("Añade como variables la desviación típica local (ventana de 3×3 o 5×5 píxeles) de los índices "
                   "de columna de agua, o del azul y el verde si no los hay. Ayuda a separar fondos a manchas "
                   "(pradera fragmentada, roca) de fondos lisos (arena) con color parecido. Con píxeles de 10 m "
                   "puede aportar poco: compara la exactitud con y sin textura y mira su importancia en el informe.",
                   "Adds as features the local standard deviation (3×3 or 5×5 pixel window) of the water-column "
                   "indices, or of blue and green without them. It helps to separate patchy bottoms (fragmented "
                   "meadow, rock) from smooth ones (sand) of similar colour. With 10 m pixels it may add little: "
                   "compare the accuracy with and without texture and look at its importance in the report."),
    "cl.vec": ("Exportar también a polígonos (GeoPackage)", "Also export to polygons (GeoPackage)"),
    "cl.vec.tip": ("Cada mancha de una clase pasa a ser un polígono con su clase, superficie (ha) y perímetro (m). "
                   "Si hay mapa filtrado, se exporta ese. Los bordes siguen los píxeles, sin suavizar.",
                   "Each patch of a class becomes a polygon with its class, area (ha) and perimeter (m). If there "
                   "is a filtered map, that one is exported. The outlines follow the pixels, not smoothed."),
    "ch.vec": ("Exportar también a polígonos (GeoPackage)", "Also export to polygons (GeoPackage)"),
    "cl.minprob": ("Probabilidad mínima:", "Minimum probability:"),
    "cl.minprob.off": ("no (todo se clasifica)", "off (classify everything)"),
    "cl.minprob.tip": ("Si ninguna clase llega a esta probabilidad, el píxel queda 'sin clasificar (baja confianza)', "
                       "código 252, en vez de forzar una clase. El informe dice qué parte de la validación cae ahí, y "
                       "las superficies corregidas reparten esa zona entre las clases. La probabilidad es relativa, "
                       "no una confianza calibrada: prueba 0,5 a 0,6 y mira cuánto mapa se pierde.",
                       "If no class reaches this probability, the pixel is left 'unclassified (low confidence)', "
                       "code 252, instead of forcing a class. The report says how much of the validation falls "
                       "there, and the corrected areas share that zone out among the classes. The probability is "
                       "relative, not a calibrated confidence: try 0.5 to 0.6 and see how much map you lose."),
    "cl.post": ("Mapa final (opcional)", "Final map (optional)"),
    "cl.filter": ("Filtro de mayoría:", "Majority filter:"),
    "cl.filter.off": ("No", "No"),
    "cl.mmu": ("Unidad mínima (píxeles):", "Minimum mapping unit (pixels):"),
    "cl.mmu.tip": ("Las manchas más pequeñas se unen a la clase vecina. 0 o 1 = no. Un píxel de 10 m son 0,01 ha.",
                   "Smaller patches are merged into the neighbouring class. 0 or 1 = off. A 10 m pixel is 0.01 ha."),
    "cl.post.help": ("Se guarda aparte (classes_filtered.tif); el mapa sin filtrar se conserva. Solo cambian "
                     "píxeles de clase, nunca las zonas sin fondo visible o demasiado hondas. El informe da la "
                     "exactitud de los dos mapas.",
                     "Saved separately (classes_filtered.tif); the raw map is kept. Only class pixels change, "
                     "never the hidden or too-deep zones. The report gives the accuracy of both maps."),
    "cl.oa.unsure": ("Probabilidad mínima %s: %s píxeles sin clasificar (%s de la validación). La exactitud de "
                     "arriba es la de lo clasificado.",
                     "Minimum probability %s: %s pixels unclassified (%s of the validation). The accuracy above is "
                     "that of what is classified."),
    "cl.oa.filt": ("Mapa filtrado: %s por píxel%s.", "Filtered map: %s by pixel%s."),
    "cl.mask": ("Máscara por profundidad", "Depth mask"),
    "cl.opt": ("Profundidad para el límite óptico:", "Depth for the optical limit:"),
    "cl.opt.tip": ("La batimetría de StarShoal (depth_*.tif) u otra. Opcional pero muy recomendable.",
                   "StarShoal bathymetry (depth_*.tif) or another. Optional but strongly advised."),
    "cl.sign": ("Valores:", "Values:"),
    "cl.sign.auto": ("Automático (StarShoal; si no, por los valores: casi todos negativos = cota)",
                     "Automatic (StarShoal; else from the values: mostly negative = elevation)"),
    "cl.sign.depth": ("Profundidad, positiva hacia abajo", "Depth, positive down"),
    "cl.sign.elev": ("Cota, negativa hacia abajo", "Elevation, negative down"),
    "cl.optlim": ("Límite óptico:", "Optical limit:"),
    "cl.optlim.auto": ("del ráster de StarShoal", "from the StarShoal raster"),
    "cl.optlim.tip": ("Profundidad hasta la que el satélite ve el fondo. En 0 se lee de los metadatos de "
                      "StarShoal (STARSHOAL_DEPTH_LIMIT_M).",
                      "Depth down to which the satellite sees the bottom. At 0 it is read from the StarShoal "
                      "metadata (STARSHOAL_DEPTH_LIMIT_M)."),
    "cl.trust": ("Confianza de StarShoal (opcional):", "StarShoal trust (optional):"),
    "cl.trust.tip": ("trust_*.tif: los píxeles extrapolados (0) cuentan como fondo no visible.",
                     "trust_*.tif: extrapolated pixels (0) count as bottom not visible."),
    "cl.eco": ("Batimetría independiente (opcional):", "Independent bathymetry (optional):"),
    "cl.eco.tip": ("EMODnet, carta náutica, multihaz... Para marcar lo que es demasiado hondo para una pradera. "
                   "No uses aquí un SDB: pasado su límite óptico está extrapolado.",
                   "EMODnet, nautical chart, multibeam... To mark what is too deep for a meadow. Do not use an "
                   "SDB here: past its optical limit it is extrapolated."),
    "cl.ecolim": ("Límite ecológico:", "Ecological limit:"),
    "cl.ecolim.tip": ("Profundidad a partir de la cual no hay pradera en tu costa. Depende de la transparencia "
                      "del agua; compruébalo con la cartografía o el seguimiento local.",
                      "Depth below which there is no meadow on your coast. It depends on water clarity; check "
                      "it against local maps or monitoring."),
    "cl.mask.help": ("Sin batimetría independiente, lo que pasa del límite óptico queda como <b>fondo no "
                     "visible</b> (sin dato), nunca como <b>sin pradera</b>. Con el polígono de agua profunda, "
                     "además, cada píxel tiene que separarse de esa agua para contar como visible.",
                     "Without an independent bathymetry, what lies past the optical limit stays <b>bottom not "
                     "visible</b> (no data), never <b>no seagrass</b>. With the deep-water polygon, each pixel "
                     "must also differ from that water to count as visible."),
    "cl.sig": ("Agua profunda (prueba de señal):", "Deep water (signal test):"),
    "cl.sig.tip": ("Polígono de agua ópticamente profunda, donde no se ve nada de fondo. Un píxel solo cuenta "
                   "como visible si se separa de esa agua en alguna banda. Así el límite depende del fondo: una "
                   "pradera oscura deja de verse antes que la arena.",
                   "Polygon of optically deep water, where no bottom at all is seen. A pixel counts as visible "
                   "only if it differs from that water in some band. This makes the limit depend on the "
                   "bottom: a dark meadow fades before sand does."),
    "cl.nsig": ("Umbral (desviaciones típicas):", "Threshold (standard deviations):"),
    "cl.sigbands": ("Bandas de la prueba:", "Test bands:"),
    "cl.need.sigband": ("La prueba de señal necesita al menos una banda.", "The signal test needs at least one band."),
    "cl.oa.poly": ("Por polígono: %s (n = %d polígonos). Es la cifra honesta; la de píxeles es optimista.",
                   "By polygon: %s (n = %d polygons). This is the honest figure; the pixel one is optimistic."),
    "cl.model": ("Clasificador y validación", "Classifier and validation"),
    "cl.method": ("Método:", "Method:"),
    "cl.m.rf": ("Random Forest (scikit-learn)", "Random Forest (scikit-learn)"),
    "cl.m.ml": ("Máxima verosimilitud (solo numpy)", "Maximum likelihood (numpy only)"),
    "cl.trees": ("Árboles:", "Trees:"),
    "cl.balanced": ("Equilibrar clases", "Balance classes"),
    "cl.balanced.tip": ("Apagado (por defecto): el modelo sigue las proporciones de clases de tu muestra. "
                        "Encendido: todas las clases pesan igual; las raras se detectan más, pero su superficie "
                        "cartografiada crece. Para superficies, déjalo apagado y mira las áreas corregidas del "
                        "informe. Ojo: si muestreas una clase más de lo que abunda, también se infla sin equilibrar.",
                        "Off (default): the model follows the class shares of your sample. On: every class weighs "
                        "the same; rare classes are found more often but their mapped area grows. For areas, leave "
                        "it off and look at the corrected areas in the report. Careful: a class sampled more than "
                        "it occurs is inflated even without balancing."),
    "cl.split": ("Separación:", "Split:"),
    "cl.split.blocks": ("Bloques espaciales por clase", "Spatial blocks by class"),
    "cl.split.random": ("Al azar (por objeto)", "Random (by feature)"),
    "cl.split.common": ("Bloques espaciales comunes (separación completa)", "Common spatial blocks (full separation)"),
    "cl.block": ("Tamaño de bloque:", "Block size:"),
    "cl.valfrac": ("Fracción de validación:", "Validation fraction:"),
    "cl.seed": ("Semilla:", "Seed:"),
    "cl.bins": ("Tramos de profundidad del informe (m):", "Report depth ranges (m):"),
    "cl.addprob": ("Añadir también la probabilidad", "Also add the probability"),
    "cl.results": ("Resultados (validación)", "Results (validation)"),
    "cl.col.class": ("Clase", "Class"),
    "cl.col.nval": ("n validación", "Validation n"),
    "cl.col.pa": ("Productor", "Producer's"),
    "cl.col.ua": ("Usuario", "User's"),
    "cl.col.area": ("Superficie", "Area"),
    "cl.oa": ("Exactitud global: %s (n = %d). Fondo visible: %d píxeles; no visible: %d; demasiado hondo: %d.",
              "Overall accuracy: %s (n = %d). Bottom visible: %d pixels; not visible: %d; too deep: %d."),
    "cl.open": ("Abrir informe", "Open report"),
    "cl.need.train": ("Elige la capa de verdad de campo y el campo de clase.", "Choose the reference layer and the class field."),
    "cl.need.feat": ("Marca al menos una banda o da los índices de columna de agua.",
                     "Tick at least one band or give the water-column indices."),
    "cl.need.opt": ("Para usar la profundidad como variable, elige la capa de profundidad.",
                    "To use depth as a feature, choose the depth raster."),
    "cl.need.optlim": ("Para usar solo la batimetría independiente, da el límite óptico (no puede leerse de ella).",
                       "To use only the independent bathymetry, give the optical limit (it cannot be read from it)."),
    "cl.few": ("Solo hay %d objetos de verdad de campo válidos.", "Only %d usable reference features."),
    "cl.skipped": ("%d objetos sin geometría o sin clase se han ignorado.", "%d features without geometry or class were skipped."),
    "cl.depthwarn": ("Ojo: la profundidad entra como variable (no recomendado, mira la ayuda).",
                     "Careful: depth is used as a feature (not recommended, see the help)."),
}
