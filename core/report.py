"""Plain HTML report for a GLUB classification (English or Spanish). No external assets."""
import html
import math

import numpy as np

from .lang import L

CSS = """
body{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:2em;max-width:70em;color:#1b2b34}
h1{color:#0b4f6c}h2{border-bottom:1px solid #9cc;padding-bottom:.2em;margin-top:1.6em}
table{border-collapse:collapse;margin:.6em 0}th,td{border:1px solid #bcd;padding:.3em .6em;text-align:right}
th{background:#e6f2f5}td.l,th.l{text-align:left}td.d{background:#eaf5ea;font-weight:600}
.warn{background:#fff4e0;border-left:4px solid #e69500;padding:.5em 1em;margin:.5em 0}
code{background:#eef5f7;padding:0 .3em}.note{color:#678;font-size:.9em}
.sw{display:inline-block;width:.9em;height:.9em;border:1px solid #888;vertical-align:middle;margin-right:.4em}
"""


def _f(v, d=2):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    try:
        if isinstance(v, (int,)) or (hasattr(v, "dtype") and v.dtype.kind in "iu"):
            return str(int(v))
        x = float(v)
        if abs(x) < 0.5 * 10 ** -d:   # no "-0.0"
            x = 0.0
        return f"{x:.{d}f}"
    except (TypeError, ValueError):
        return str(v)


def _pct(v):
    return "n/a" if v is None or (isinstance(v, float) and math.isnan(v)) or v != v else f"{100 * v:.1f} %"


def _e(s):
    return html.escape(str(s))


def build(settings, s, warnings, credit=""):
    classes = s["classes"]
    k = len(classes)
    unit = "ha" if s["ha"] else "px"
    ha = s["ha"] or 1.0
    MR = L("Map \\ Reference", "Mapa \\ Referencia")
    UA, PA = L("User's acc.", "Exactitud usuario"), L("Producer's acc.", "Exactitud productor")
    lang = "es" if L("en", "es") == "es" else "en"
    p = [f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'><title>"
         + L("GLUB report", "Informe GLUB") + f"</title><style>{CSS}</style></head><body><h1>"
         + L("GLUB · benthic habitat classification", "GLUB · clasificación de hábitats bentónicos") + "</h1>"]
    if warnings:
        p.append("<h2>" + L("Warnings", "Avisos") + "</h2>")
        p += [f"<div class='warn'>{_e(w)}</div>" for w in warnings]
    p.append("<h2>" + L("Settings", "Parámetros") + "</h2><table>")
    p += [f"<tr><td class='l'>{_e(a)}</td><td class='l'>{_e(b)}</td></tr>" for a, b in settings]
    p.append("</table>")

    m = s["mask"]
    p.append("<h2>" + L("Where the map speaks", "Dónde habla el mapa") + "</h2>")
    p.append("<table><tr><th class='l'>" + L("Zone", "Zona") + "</th><th>" + L("Pixels", "Píxeles") + "</th><th>"
             + L("Area", "Superficie") + "</th><th>" + L("Meaning", "Significado") + "</th></tr>")
    for lab, n, mean in ((L("Bottom visible", "Fondo visible"), m["visible"], L("classified", "se clasifica")),
                         (L("Bottom not visible", "Fondo no visible"), m["hidden"],
                          L("no data: seagrass may or may not be there", "sin dato: puede haber pradera o no")),
                         (L("Too deep", "Demasiado hondo"), m["too_deep"],
                          L("deeper than the ecological limit: no seagrass",
                            "más hondo que el límite ecológico: sin pradera"))):
        p.append(f"<tr><td class='l'>{lab}</td><td>{n}</td><td>{_f(n * ha, 1)} {unit}</td>"
                 f"<td class='l'>{mean}</td></tr>")
    mp = s.get("min_prob") or 0
    if mp > 0:
        nu = s.get("n_unsure_px", 0)
        p.append(f"<tr><td class='l'>{L('of which: low confidence', 'de ellos: baja confianza')}</td><td>{nu}</td>"
                 f"<td>{_f(nu * ha, 1)} {unit}</td><td class='l'>"
                 + L(f"bottom visible, but no class reaches probability {mp:g}: left unclassified (code 252)",
                     f"fondo visible, pero ninguna clase llega a probabilidad {mp:g}: queda sin clasificar "
                     "(código 252)") + "</td></tr>")
    p.append("</table>")
    ol = s.get("opt_limit")
    el = s.get("eco_limit")
    p.append("<p>" + L("Optical depth limit: ", "Límite óptico: ")
             + (_f(ol, 1) + " m" if ol is not None else L("none", "ninguno")) + ". "
             + L("Ecological depth limit: ", "Límite ecológico: ")
             + (_f(el, 1) + " m" if el is not None else L("none (no independent bathymetry)",
                                                           "ninguno (sin batimetría independiente)")) + ". "
             + L("The lower edge of a meadow usually lies deeper than the optical limit of the image, so this map "
                 "does not show where meadows end in depth.",
                 "El límite inferior de una pradera suele quedar más hondo que el límite óptico de la imagen, así "
                 "que este mapa no dice dónde acaba la pradera en profundidad.") + "</p>")
    if s.get("signal"):
        det = "; ".join(L(f"{_e(b)}: mean {v['mean']:.5f}, sd {v['sd']:.5f}, n = {v['n']}",
                          f"{_e(b)}: media {v['mean']:.5f}, σ {v['sd']:.5f}, n = {v['n']}")
                        for b, v in s["signal"].items())
        p.append(L(f"<p><b>Bottom-signal test:</b> a pixel counts as visible only if it differs from the deep-water "
                   f"sample by more than {_f(s['n_sigma'], 1)} standard deviations in some band ({det}). It removed "
                   f"{m['no_signal']} pixels that were within the optical depth limit. This makes the limit depend "
                   "on the bottom: dark meadows drop out at shallower depth than sand.</p>",
                   f"<p><b>Prueba de señal:</b> un píxel solo cuenta como visible si se separa de la muestra de "
                   f"agua profunda más de {_f(s['n_sigma'], 1)} desviaciones típicas en alguna banda ({det}). Ha "
                   f"quitado {m['no_signal']} píxeles que estaban dentro del límite óptico. Así el límite depende "
                   "del fondo: las praderas oscuras dejan de verse antes que la arena.</p>"))
    else:
        p.append(L("<p class='note'>No bottom-signal test: one optical limit for every bottom. Near the limit, dark "
                   "meadows may be classified where they barely differ from deep water.</p>",
                   "<p class='note'>Sin prueba de señal: un solo límite óptico para todos los fondos. Cerca del "
                   "límite, las praderas oscuras pueden clasificarse donde apenas se distinguen del agua "
                   "profunda.</p>"))

    p.append("<h2>" + L("Training and validation samples", "Muestras de calibración y validación") + "</h2>")
    split = {"blocks": L("spatial blocks by class (whole blocks of each class go to validation; samples of "
                         "different classes in one block can fall on different sides)",
                         "bloques espaciales por clase (bloques enteros de cada clase van a validación; muestras "
                         "de clases distintas en un mismo bloque pueden caer en lados distintos)"),
             "blocks_all": L("common spatial blocks (a block goes whole to one side, whatever its classes: full "
                             "spatial separation)",
                             "bloques espaciales comunes (un bloque va entero a un lado, tenga las clases que "
                             "tenga: separación espacial completa)"),
             "random": L("random by group", "al azar por objeto")}.get(s["split"], s["split"])
    poly = s["training_kind"] == "polygons"
    unit_s = L("polygons", "polígonos") if poly else L("points", "puntos")
    p.append(L(f"<p>Split: {split}. Pixels of one polygon always stay on the same side. Calibration: "
               f"{s['n_cal']} samples from {s['groups_cal']} {unit_s}; validation: {s['n_val']} samples from "
               f"{s['groups_val']} {unit_s}. The map is made with the model fitted on the calibration samples, "
               "the same one that is validated.</p>",
               f"<p>Separación: {split}. Los píxeles de un polígono van siempre al mismo lado. Calibración: "
               f"{s['n_cal']} muestras de {s['groups_cal']} {unit_s}; validación: {s['n_val']} muestras de "
               f"{s['groups_val']} {unit_s}. El mapa sale del modelo ajustado con la calibración, el mismo que se "
               "valida.</p>"))
    if s.get("shrink"):
        p.append(L(f"<p>Reference polygons were shrunk by {s['shrink']:g} (CRS units) before sampling.</p>",
                   f"<p>Los polígonos de referencia se encogieron {s['shrink']:g} (unidades del SRC) antes de "
                   "muestrear.</p>"))
    p.append("<table><tr><th class='l'>" + L("Code", "Código") + "</th><th class='l'>" + L("Class", "Clase")
             + "</th><th>" + L("Calibration", "Calibración") + "</th><th>" + L("Validation", "Validación")
             + "</th><th>" + L("Mapped pixels", "Píxeles cartografiados") + "</th><th>"
             + L("Mapped area", "Superficie cartografiada") + f" ({unit})</th></tr>")
    for i, c in enumerate(classes):
        p.append(f"<tr><td class='l'>{i + 1}</td><td class='l'>{_e(c)}</td><td>{s['n_cal_class'][i]}</td>"
                 f"<td>{s['n_val_class'][i]}</td><td>{int(s['map_px'][i])}</td>"
                 f"<td>{_f(s['map_px'][i] * ha, 1)}</td></tr>")
    p.append("</table>")

    a = s["acc"]
    g = s.get("groups_acc")
    if g:
        gs = g["summary"]
        ties = (L(f"; {g['ties']} ties counted as errors", f"; {g['ties']} empates contados como error")
                if g["ties"] else "")
        p.append("<h2>" + L("Accuracy by polygon (validation)", "Exactitud por polígono (validación)") + "</h2>")
        p.append(L(f"<p><b>Overall accuracy by polygon: {_pct(g['oa'])}</b> (n = {g['n']} polygons; each polygon "
                   f"votes with the majority class of its pixels{ties}). This is the honest figure: the pixels of "
                   "one polygon are not independent samples.</p>",
                   f"<p><b>Exactitud global por polígono: {_pct(g['oa'])}</b> (n = {g['n']} polígonos; cada "
                   f"polígono vota con la clase mayoritaria de sus píxeles{ties}). Es la cifra honesta: los píxeles "
                   "de un polígono no son muestras independientes.</p>"))
        p.append(f"<table><tr><th class='l'>{MR}</th>" + "".join(f"<th>{_e(c)}</th>" for c in classes)
                 + f"<th>{UA}</th></tr>")
        for i, c in enumerate(classes):
            cells = "".join(f"<td class='{'d' if i == j else ''}'>{int(g['cm'][i, j])}</td>" for j in range(k))
            p.append(f"<tr><td class='l'>{_e(c)}</td>{cells}<td>{_pct(gs['ua'][i])}</td></tr>")
        p.append(f"<tr><td class='l'>{PA}</td>" + "".join(f"<td>{_pct(v)}</td>" for v in gs["pa"])
                 + "<td></td></tr></table>")
        counts = ", ".join(f"{_e(c)} {int(g['n_ref'][i])}" for i, c in enumerate(classes))
        p.append(L(f"<p class='note'>Reference polygons per class: {counts}. With few polygons per class, these "
                   "percentages move a lot with one polygon.</p>",
                   f"<p class='note'>Polígonos de referencia por clase: {counts}. Con pocos polígonos por clase, "
                   "estos porcentajes cambian mucho con un solo polígono.</p>"))
    if a["n"]:
        if g:
            p.append("<h2>" + L("Accuracy by pixel (validation samples)",
                                "Exactitud por píxel (muestras de validación)") + "</h2>")
            p.append(L(f"<p><b>Overall accuracy by pixel: {_pct(a['oa'])}</b> (n = {a['n']} pixels; optimistic, "
                       "see the polygon table above).</p>",
                       f"<p><b>Exactitud global por píxel: {_pct(a['oa'])}</b> (n = {a['n']} píxeles; optimista, "
                       "mira la tabla por polígono).</p>"))
        else:
            p.append("<h2>" + L("Accuracy (validation samples)", "Exactitud (muestras de validación)") + "</h2>")
            p.append(L(f"<p><b>Overall accuracy: {_pct(a['oa'])}</b> (n = {a['n']}).</p>",
                       f"<p><b>Exactitud global: {_pct(a['oa'])}</b> (n = {a['n']}).</p>"))
        if a.get("n_unsure"):
            ub = ", ".join(f"{_e(c)} {int(a['unsure_by_ref'][i])}" for i, c in enumerate(classes))
            tot = a["n"] + a["n_unsure"]
            p.append(L(f"<p>{a['n_unsure']} of {tot} validation samples ({_pct(a['n_unsure'] / tot)}) fall below "
                       f"the minimum probability ({s['min_prob']:g}) and are left out of this matrix (by reference "
                       f"class: {ub}). The accuracy above is that of the pixels the map does classify; read it "
                       "together with this share.</p>",
                       f"<p>{a['n_unsure']} de {tot} muestras de validación ({_pct(a['n_unsure'] / tot)}) quedan por "
                       f"debajo de la probabilidad mínima ({s['min_prob']:g}) y no entran en esta matriz (por clase de "
                       f"referencia: {ub}). La exactitud de arriba es la de los píxeles que el mapa sí clasifica; "
                       "léela junto con esta proporción.</p>"))
        p.append("<p>" + L("Confusion matrix: rows = map, columns = reference.",
                           "Matriz de confusión: filas = mapa, columnas = referencia.") + "</p>"
                 + f"<table><tr><th class='l'>{MR}</th>" + "".join(f"<th>{_e(c)}</th>" for c in classes)
                 + f"<th>Total</th><th>{UA}</th></tr>")
        cm = s["cm"]
        for i, c in enumerate(classes):
            cells = "".join(f"<td class='{'d' if i == j else ''}'>{int(cm[i, j])}</td>" for j in range(k))
            p.append(f"<tr><td class='l'>{_e(c)}</td>{cells}<td>{int(cm[i].sum())}</td><td>{_pct(a['ua'][i])}</td></tr>")
        p.append("<tr><td class='l'>Total</td>" + "".join(f"<td>{int(cm[:, j].sum())}</td>" for j in range(k))
                 + f"<td>{int(cm.sum())}</td><td></td></tr>")
        p.append(f"<tr><td class='l'>{PA}</td>" + "".join(f"<td>{_pct(v)}</td>" for v in a["pa"])
                 + "<td></td><td></td></tr></table>")
        p.append("<table><tr><th class='l'>" + L("Class", "Clase") + "</th><th>" + L("Reference n", "n referencia")
                 + "</th><th>" + L("Producer's", "Productor") + "</th><th>" + L("User's", "Usuario")
                 + "</th><th>F1</th></tr>")
        for i, c in enumerate(classes):
            p.append(f"<tr><td class='l'>{_e(c)}</td><td>{a['n_ref'][i]}</td><td>{_pct(a['pa'][i])}</td>"
                     f"<td>{_pct(a['ua'][i])}</td><td>{_f(a['f1'][i], 3)}</td></tr>")
        p.append("</table>" + L("<p class='note'>Producer's accuracy: share of the reference samples of a class that "
                                "the map gets right (omission = 1 − PA). User's accuracy: share of the samples mapped "
                                "as a class that really are that class (commission = 1 − UA). Counts are pixels; one "
                                "polygon gives several correlated pixels, so the real sample size is closer to the "
                                "number of polygons.</p>",
                                "<p class='note'>Exactitud del productor: parte de las muestras de referencia de una "
                                "clase que el mapa acierta (omisión = 1 − EP). Exactitud del usuario: parte de lo "
                                "cartografiado como una clase que de verdad lo es (comisión = 1 − EU). Se cuentan "
                                "píxeles; un polígono da varios píxeles correlacionados, así que el tamaño real de "
                                "la muestra se parece más al número de polígonos.</p>"))

    f = s.get("filtered")
    if f:
        p.append("<h2>" + L("Filtered map", "Mapa filtrado") + " (classes_filtered.tif)</h2>")
        parts = []
        if f["window"] > 1:
            parts.append(L(f"majority filter {f['window']}x{f['window']}",
                           f"filtro de mayoría {f['window']}x{f['window']}"))
        if f["mmu"] > 1:
            parts.append(L(f"minimum mapping unit {f['mmu']} pixels ({_f(f['mmu'] * ha, 2)} {unit})",
                           f"unidad mínima de {f['mmu']} píxeles ({_f(f['mmu'] * ha, 2)} {unit})"))
        p.append("<p>" + ", ".join(parts).capitalize() + ". "
                 + L("Only class pixels change; the zones 'bottom not visible' and 'too deep' stay as they are. "
                     "The raw map is kept in classes.tif.",
                     "Solo cambian píxeles de clase; las zonas 'fondo no visible' y 'demasiado hondo' se quedan "
                     "como están. El mapa sin filtrar sigue en classes.tif.") + "</p>")
        if f.get("acc"):
            fa = f["acc"]
            gp = (L(f", by polygon {_pct(f['groups_acc']['oa'])}", f", por polígono {_pct(f['groups_acc']['oa'])}")
                  if f.get("groups_acc") else "")
            rp = (L(f", by polygon {_pct(g['oa'])}", f", por polígono {_pct(g['oa'])}") if g else "")
            p.append(L(f"<p><b>Overall accuracy of the filtered map on the same validation samples: by pixel "
                       f"{_pct(fa['oa'])}{gp}</b> (raw map: by pixel {_pct(a['oa'])}{rp}).</p>",
                       f"<p><b>Exactitud global del mapa filtrado con las mismas muestras de validación: por píxel "
                       f"{_pct(fa['oa'])}{gp}</b> (mapa sin filtrar: por píxel {_pct(a['oa'])}{rp}).</p>"))
            p.append(L("<p class='note'>Filtering tends to help inside polygons (the samples are drawn in homogeneous "
                       "patches) and to hurt at edges and in small real patches, which the reference samples rarely "
                       "cover. A higher accuracy here does not prove the filtered map is better everywhere.</p>",
                       "<p class='note'>Filtrar suele ayudar dentro de los polígonos (las muestras se dibujan en "
                       "manchas homogéneas) y estropear los bordes y las manchas pequeñas reales, que las muestras "
                       "casi nunca cubren. Que aquí suba la exactitud no demuestra que el mapa filtrado sea mejor en "
                       "todas partes.</p>"))
        p.append("<table><tr><th class='l'>" + L("Class", "Clase") + f"</th><th>{L('Raw', 'Sin filtrar')} ({unit})"
                 f"</th><th>{L('Filtered', 'Filtrado')} ({unit})</th></tr>")
        for i, c in enumerate(classes):
            p.append(f"<tr><td class='l'>{_e(c)}</td><td>{_f(s['map_px'][i] * ha, 1)}</td>"
                     f"<td>{_f(f['map_px'][i] * ha, 1)}</td></tr>")
        p.append("</table><p class='note'>" + L("The corrected areas below refer to the raw map.",
                                              "Las superficies corregidas de abajo son del mapa sin filtrar.")
                 + "</p>")

    adj = s.get("adj")
    if adj:
        p.append("<h2>" + L("Area corrected for map errors", "Superficie corregida por los errores del mapa")
                 + " (Olofsson et al., 2014)</h2>")
        p.append("<div class='warn'>" + L(
            "These estimators assume a probability sample of reference data (for example stratified random by map "
            "class). Field points or polygons placed where it was convenient are not one, so take these areas and "
            "intervals as indicative.",
            "Estos estimadores suponen un muestreo probabilístico de la referencia (por ejemplo, aleatorio "
            "estratificado por clase del mapa). Puntos o polígonos puestos donde se pudo no lo son, así que toma "
            "estas superficies e intervalos como orientativos.") + "</div>")
        p.append("<table><tr><th class='l'>" + L("Class", "Clase") + f"</th><th>{L('Mapped', 'Cartografiada')} "
                 f"({unit})</th><th>{L('Corrected', 'Corregida')} ({unit})</th><th>± 95 % ({unit})</th><th>"
                 + L("Corrected PA", "EP corregida") + "</th><th>" + L("Corrected UA", "EU corregida") + "</th></tr>")
        for i, c in enumerate(classes):
            p.append(f"<tr><td class='l'>{_e(c)}</td><td>{_f(adj['mapped'][i], 1)}</td><td>{_f(adj['area'][i], 1)}</td>"
                     f"<td>{_f(adj['ci'][i], 1)}</td><td>{_pct(adj['pa'][i])}</td><td>{_pct(adj['ua'][i])}</td></tr>")
        p.append("</table><p>" + L(f"Corrected overall accuracy: {_pct(adj['oa'])}. Only the zone where the bottom "
                                   "is visible is included.",
                                   f"Exactitud global corregida: {_pct(adj['oa'])}. Solo incluye la zona con fondo "
                                   "visible.") + "</p>")
        if (s.get("min_prob") or 0) > 0:
            p.append("<p class='note'>" + L(
                "The low-confidence zone enters as one more map stratum: its validation samples share its area out "
                "among the classes, and in the corrected overall accuracy it counts as wrong.",
                "La zona de baja confianza entra como un estrato más del mapa: sus muestras de validación reparten su "
                "superficie entre las clases, y en la exactitud global corregida cuenta como error.") + "</p>")

    if s.get("bins"):
        src = {"eco": L("independent bathymetry", "batimetría independiente"),
               "sdb": L("StarShoal SDB (biased over dark bottoms: seagrass tends to read deeper)",
                        "SDB de StarShoal (sesgado sobre fondos oscuros: la pradera tiende a salir más honda)"),
               "opt": L("optical-limit depth raster", "capa de profundidad del límite óptico")}.get(
            s.get("bins_source"), "n/a")
        p.append("<h2>" + L("Accuracy by depth (validation samples)",
                            "Exactitud por profundidad (muestras de validación)") + "</h2>")
        p.append("<p>" + L(f"Depth from: {_e(src)}. If accuracy falls with depth, the water column is still driving "
                           "the classes.",
                           f"Profundidad de: {_e(src)}. Si la exactitud cae con la profundidad, la columna de agua "
                           "sigue mandando en las clases.") + "</p><table><tr><th class='l'>"
                 + L("Depth (m)", "Profundidad (m)") + "</th><th>n</th><th>" + L("Overall accuracy", "Exactitud global")
                 + "</th></tr>")
        for b in s["bins"]:
            rng = b["range"] if b["range"] != "no depth" else L("no depth", "sin profundidad")
            p.append(f"<tr><td class='l'>{_e(rng)}</td><td>{b['n']}</td><td>{_pct(b['oa'])}</td></tr>")
        p.append("</table>")

    if s.get("importances"):
        p.append("<h2>" + L("Feature importance (Random Forest)", "Importancia de las variables (Random Forest)")
                 + "</h2><table><tr><th class='l'>" + L("Feature", "Variable") + "</th><th>"
                 + L("Importance", "Importancia") + "</th></tr>")
        for name, v in sorted(s["importances"].items(), key=lambda kv: -kv[1]):
            p.append(f"<tr><td class='l'>{_e(name)}</td><td>{v:.3f}</td></tr>")
        p.append("</table><p class='note'>" + L(
            "Impurity-based importance: it favours correlated and continuous features, read it as a rough guide.",
            "Importancia por impureza: favorece variables correlacionadas y continuas, tómala como una guía "
            "aproximada.") + "</p>")

    px = s.get("pixel_m")
    pxt = (f"{px:.0f}" if px and abs(px - round(px)) < 0.05 else f"{px:.1f}") if px else None
    p.append("<h2>" + L("Limits of this map", "Límites de este mapa") + "</h2><ul>" + L(
        (f"<li>{pxt} m pixels: small" if pxt else "<li>Small") + " patches and meadow edges are mixed pixels.</li>"
        "<li>With multispectral satellite images (Sentinel-2, Landsat), seagrass versus not seagrass is the realistic target; separating seagrass "
        "species, or live meadow from dead matte, is much less reliable.</li>"
        "<li>Dark bottoms (seagrass, macroalgae, rock with epiphytes, dead matte) look alike; the more "
        "water above, the more alike.</li>"
        "<li>The map is as good as the reference samples: their date should be close to the image date.</li>",
        (f"<li>Píxeles de {pxt} m: las" if pxt else "<li>Las") + " manchas pequeñas y los bordes de pradera son píxeles mezclados.</li>"
        "<li>Con imágenes de satélite multiespectrales (Sentinel-2, Landsat) lo realista es pradera frente a no pradera; separar especies, o pradera viva de mata "
        "muerta, es mucho menos fiable.</li>"
        "<li>Los fondos oscuros (pradera, macroalgas, roca con epífitos, mata muerta) se parecen, y más cuanta más "
        "agua hay encima.</li>"
        "<li>El mapa es tan bueno como las muestras de referencia: su fecha debe estar cerca de la de la "
        "imagen.</li>") + "</ul>")
    if credit:
        p.append(f"<p class='note'>{_e(credit)}</p>")
    p.append("</body></html>")
    return "\n".join(p)


def build_assessment(settings, s, warnings, credit=""):
    """Report of a map assessed with stratified random validation points."""
    unit = "ha" if s["ha"] else "px"
    ha = s["ha"] or 1.0
    k, classes, strata = s["k"], s["classes"], s["strata"]
    m, adj = s["cm"], s["adj"]
    lang = "es" if L("en", "es") == "es" else "en"
    p = [f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'><title>"
         + L("GLUB assessment", "Evaluación GLUB") + f"</title><style>{CSS}</style></head><body><h1>"
         + L("Map assessment with validation points", "Evaluación del mapa con puntos de validación") + "</h1>"]
    if warnings:
        p.append("<h2>" + L("Warnings", "Avisos") + "</h2>")
        p += [f"<div class='warn'>{_e(w)}</div>" for w in warnings]
    p.append("<h2>" + L("Settings", "Parámetros") + "</h2><table>")
    p += [f"<tr><td class='l'>{_e(a)}</td><td class='l'>{_e(b)}</td></tr>" for a, b in settings]
    p.append("</table>")
    p.append("<p>" + L(f"Points used: {s['n_used']} of {s['n_points']}.", f"Puntos usados: {s['n_used']} de {s['n_points']}.")
             + " " + L("The estimators assume the points were drawn at random within each map class (stratified "
                       "random sampling, as the point generator does) and labelled without looking at the map.",
                       "Los estimadores suponen que los puntos se sortearon al azar dentro de cada clase del mapa "
                       "(muestreo aleatorio estratificado, como hace el generador de puntos) y que se etiquetaron "
                       "sin mirar el mapa.") + "</p>")
    p.append("<h2>" + L("Strata", "Estratos") + "</h2><table><tr><th class='l'>" + L("Map stratum", "Estrato del mapa")
             + f"</th><th>{L('Pixels', 'Píxeles')}</th><th>{L('Area', 'Superficie')} ({unit})</th><th>W</th><th>"
             + L("Points", "Puntos") + "</th></tr>")
    tot = max(int(s["pixels"].sum()), 1)
    for i, nm in enumerate(strata):
        p.append(f"<tr><td class='l'>{_e(nm)}</td><td>{int(s['pixels'][i])}</td>"
                 f"<td>{_f(s['pixels'][i] * ha, 1)}</td><td>{s['pixels'][i] / tot:.4f}</td>"
                 f"<td>{int(s['n_strata'][i])}</td></tr>")
    p.append("</table>")
    MR = L("Map \\ Reference", "Mapa \\ Referencia")
    p.append("<h2>" + L("Confusion matrix (point counts)", "Matriz de confusión (número de puntos)") + "</h2>")
    p.append(f"<table><tr><th class='l'>{MR}</th>" + "".join(f"<th>{_e(c)}</th>" for c in classes)
             + "<th>Total</th></tr>")
    for i, nm in enumerate(strata):
        cells = "".join(f"<td class='{'d' if i == j else ''}'>{int(m[i, j])}</td>" for j in range(len(classes)))
        p.append(f"<tr><td class='l'>{_e(nm)}</td>{cells}<td>{int(m[i].sum())}</td></tr>")
    p.append("</table><p class='note'>" + L(
        "Counts of points. In a stratified sample the classes are not sampled in proportion to their area, so "
        "accuracy is not read from these counts directly: the table below weights each row by the area of its "
        "stratum.",
        "Número de puntos. En un muestreo estratificado las clases no se muestrean en proporción a su superficie, "
        "así que la exactitud no se lee directamente de estos números: la tabla de abajo pondera cada fila por la "
        "superficie de su estrato.") + "</p>")
    if adj is not None:
        p.append("<h2>" + L("Accuracy and area (Olofsson et al., 2014)", "Exactitud y superficie (Olofsson et al., 2014)")
                 + "</h2>")
        p.append(L(f"<p><b>Overall accuracy: {_pct(adj['oa'])} ± {_pct(s['ci_oa'])}</b> (95 % interval).</p>",
                   f"<p><b>Exactitud global: {_pct(adj['oa'])} ± {_pct(s['ci_oa'])}</b> (intervalo del 95 %).</p>"))
        p.append("<table><tr><th class='l'>" + L("Class", "Clase") + f"</th><th>{L('Mapped', 'Cartografiada')} ({unit})"
                 f"</th><th>{L('Estimated', 'Estimada')} ({unit})</th><th>± 95 % ({unit})</th><th>"
                 + L("User's acc.", "Exactitud usuario") + "</th><th>± 95 %</th><th>" + L("Producer's acc.", "Exactitud productor")
                 + "</th></tr>")
        for j, c in enumerate(classes):
            mapped = _f(adj["mapped"][j], 1) if j < k else "0"
            ua = _pct(adj["ua"][j]) if j < k else "n/a"
            cu = _pct(s["ci_ua"][j]) if j < k else ""
            p.append(f"<tr><td class='l'>{_e(c)}</td><td>{mapped}</td><td>{_f(adj['area'][j], 1)}</td>"
                     f"<td>{_f(adj['ci'][j], 1)}</td><td>{ua}</td><td>{cu}</td><td>{_pct(adj['pa'][j])}</td></tr>")
        p.append("</table><p class='note'>" + L(
            "Estimated area: what the map plus the errors seen at the points say is really there, within the "
            "strata above (the zone where the bottom is visible, including the low-confidence zone if any). "
            "Producer's accuracy is area-weighted too. No kappa (Pontius and Millones, 2011).",
            "Superficie estimada: lo que el mapa, corregido con los errores vistos en los puntos, dice que hay de "
            "verdad, dentro de los estratos de arriba (la zona con fondo visible, con la de baja confianza si la "
            "hay). La exactitud del productor también va ponderada por superficie. Sin kappa (Pontius y Millones, "
            "2011).") + "</p>")
    if s.get("mask_check"):
        p.append("<h2>" + L("Points outside the classified zone (mask check)", "Puntos fuera de la zona clasificada "
                                                                             "(control de la máscara)") + "</h2>")
        p.append("<table><tr><th class='l'>" + L("Zone", "Zona") + "</th>" + "".join(f"<th>{_e(c)}</th>" for c in classes)
                 + "</tr>")
        for nm, v in s["mask_check"].items():
            p.append(f"<tr><td class='l'>{_e(nm)}</td>" + "".join(f"<td>{int(x)}</td>" for x in v) + "</tr>")
        p.append("</table><p class='note'>" + L(
            "What is really found where the map does not speak. Seagrass in the 'too deep' zone means the ecological "
            "limit is too shallow; seagrass in the 'bottom not visible' zone is the meadow the satellite cannot see. "
            "These points are not part of the area estimate above.",
            "Lo que hay de verdad donde el mapa no habla. Pradera en la zona 'demasiado hondo' indica que el límite "
            "ecológico está demasiado somero; pradera en la zona 'fondo no visible' es la pradera que el satélite no "
            "ve. Estos puntos no entran en la estimación de superficie de arriba.") + "</p>")
    if credit:
        p.append(f"<p class='note'>{_e(credit)}</p>")
    p.append("</body></html>")
    return "\n".join(p)


def build_change(settings, s, warnings, credit=""):
    """Report of the change between two class maps."""
    unit = "ha" if s["ha"] else "px"
    ha = s["ha"] or 1.0
    classes, T = s["classes"], s["trans"]
    k = len(classes)
    lang = "es" if L("en", "es") == "es" else "en"
    p = [f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'><title>"
         + L("GLUB change report", "Informe de cambios GLUB") + f"</title><style>{CSS}</style></head><body><h1>"
         + L("Change between two maps", "Cambios entre dos mapas") + "</h1>"]
    p.append("<div class='warn'>" + L(
        "Mapped change is indicative. Subtracting two maps adds up the errors of both, and the apparent change can "
        "be as large as the real one. For change areas to publish, draw stratified points on change.tif with the "
        "validation tab and label each one on both dates.",
        "El cambio cartografiado es orientativo. Restar dos mapas suma los errores de los dos, y el cambio aparente "
        "puede ser tan grande como el real. Para superficies de cambio que publicar, saca puntos estratificados "
        "sobre change.tif con la pestaña de validación y etiqueta cada uno en las dos fechas.") + "</div>")
    if warnings:
        p.append("<h2>" + L("Warnings", "Avisos") + "</h2>")
        p += [f"<div class='warn'>{_e(w)}</div>" for w in warnings]
    p.append("<h2>" + L("Settings", "Parámetros") + "</h2><table>")
    p += [f"<tr><td class='l'>{_e(a)}</td><td class='l'>{_e(b)}</td></tr>" for a, b in settings]
    for lab, v in ((L("Date 1", "Fecha 1"), s.get("date1")), (L("Date 2", "Fecha 2"), s.get("date2"))):
        p.append(f"<tr><td class='l'>{lab}</td><td class='l'>{_e(v or L('not found in the map', 'no consta en el mapa'))}</td></tr>")
    for lab, v in ((L("Validation accuracy, map 1", "Exactitud de validación, mapa 1"), s.get("oa1")),
                   (L("Validation accuracy, map 2", "Exactitud de validación, mapa 2"), s.get("oa2"))):
        p.append(f"<tr><td class='l'>{lab}</td><td class='l'>{_pct(v) if v is not None else L('not stored', 'no consta')}</td></tr>")
    p.append("</table>")
    comp = s["comparable"]
    p.append("<h2>" + L("Where the maps can be compared", "Dónde se pueden comparar los mapas") + "</h2>")
    p.append(L(f"<p>Comparable (bottom classified on both dates): {comp} pixels ({_f(comp * ha, 1)} {unit}); "
               f"with change: {s['changed']} ({_pct(s['changed'] / comp if comp else float('nan'))}). Not comparable "
               f"(bottom not visible, too deep or low confidence on one of the dates): {s['not_comparable']} pixels "
               f"({_f(s['not_comparable'] * ha, 1)} {unit}).</p>",
               f"<p>Comparables (fondo clasificado en las dos fechas): {comp} píxeles ({_f(comp * ha, 1)} {unit}); "
               f"con cambio: {s['changed']} ({_pct(s['changed'] / comp if comp else float('nan'))}). No comparables "
               f"(fondo no visible, demasiado hondo o baja confianza en alguna de las fechas): {s['not_comparable']} "
               f"píxeles ({_f(s['not_comparable'] * ha, 1)} {unit}).</p>"))
    if s.get("noise") is not None:
        p.append(L(f"<p>With the validation accuracies of the two maps, about {_pct(s['noise'])} of the pixels could "
                   "disagree by error alone if the errors were independent (they usually are not fully, so take it "
                   "as a rough scale, not a correction).</p>",
                   f"<p>Con las exactitudes de validación de los dos mapas, cerca del {_pct(s['noise'])} de los píxeles "
                   "podrían no coincidir solo por error si los errores fueran independientes (casi nunca lo son del "
                   "todo, así que tómalo como una escala aproximada, no como una corrección).</p>"))
    p.append("<h2>" + L("Transition matrix", "Matriz de transiciones") + f" ({unit})</h2>")
    p.append("<table><tr><th class='l'>" + L("Date 1 \\ Date 2", "Fecha 1 \\ Fecha 2") + "</th>"
             + "".join(f"<th>{_e(c)}</th>" for c in classes) + "<th>Total</th></tr>")
    for i in range(k):
        cells = "".join(f"<td class='{'d' if i == j else ''}'>{_f(T[i, j] * ha, 1)}</td>" for j in range(k))
        p.append(f"<tr><td class='l'>{_e(classes[i])}</td>{cells}<td>{_f(T[i].sum() * ha, 1)}</td></tr>")
    p.append("<tr><td class='l'>Total</td>" + "".join(f"<td>{_f(T[:, j].sum() * ha, 1)}</td>" for j in range(k))
             + f"<td>{_f(T.sum() * ha, 1)}</td></tr></table>")
    p.append("<h2>" + L("Gains and losses by class", "Ganancias y pérdidas por clase") + f" ({unit})</h2>")
    p.append("<table><tr><th class='l'>" + L("Class", "Clase") + "</th><th>" + L("Date 1", "Fecha 1") + "</th><th>"
             + L("Date 2", "Fecha 2") + "</th><th>" + L("Loss", "Pérdida") + "</th><th>" + L("Gain", "Ganancia")
             + "</th><th>" + L("Net", "Neto") + "</th></tr>")
    for r in s["per_class"]:
        p.append(f"<tr><td class='l'>{_e(r['class'])}</td><td>{_f(r['date1'], 1)}</td><td>{_f(r['date2'], 1)}</td>"
                 f"<td>{_f(r['loss'], 1)}</td><td>{_f(r['gain'], 1)}</td><td>{_f(r['net'], 1)}</td></tr>")
    p.append("</table><p class='note'>" + L(
        "Within the comparable zone only. Loss and gain both large with a small net change often means map noise "
        "(pixels swapping class back and forth) rather than real change.",
        "Solo dentro de la zona comparable. Pérdidas y ganancias grandes con un cambio neto pequeño suelen ser ruido "
        "de los mapas (píxeles que cambian de clase en los dos sentidos) más que cambio real.") + "</p>")
    f = s.get("filtered")
    if f:
        ft = f["trans"]
        ch = int(ft.sum() - np.trace(ft))
        p.append("<p>" + L(f"Minimum change unit of {f['mmu']} pixels (change_filtered.tif): changed pixels go from "
                           f"{s['changed']} to {ch}.",
                           f"Unidad mínima de cambio de {f['mmu']} píxeles (change_filtered.tif): los píxeles con cambio "
                           f"pasan de {s['changed']} a {ch}.") + "</p>")
    if credit:
        p.append(f"<p class='note'>{_e(credit)}</p>")
    p.append("</body></html>")
    return "\n".join(p)
