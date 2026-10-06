# GLUB (GIS Looking Under the Blue)

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23186099.svg)](https://doi.org/10.5281/zenodo.23186099)

Seagrass and shallow seabed mapping for QGIS. One window with tabs (menu *GLUB*,
its toolbar button, or *Raster > GLUB*), in Spanish and English. Every tool is
also in the Processing Toolbox for models and batch runs.

GLUB is the companion of **StarShoal** (satellite-derived bathymetry): StarShoal's
depth and trust rasters tell GLUB where the satellite sees the bottom.

Tabs (version 1.0.1):

1. **Download Sentinel-2** from the Copernicus Data Space Ecosystem (free account).
2. **Prepare**: Sentinel-2 L2A (Sen2Cor), **Landsat 4-9 Collection 2 Level-2** (USGS, 30 m,
   from 1984; .tar as downloaded from EarthExplorer) or an **ACOLITE** output (Sentinel-2
   or Landsat), or **any reflectance raster** with blue, green, red and NIR (band order,
   scale and offset given by the user; PlanetScope, drones...), clipped by extent and/or
   polygon, with cloud mask (SCL or QA_PIXEL; none for the generic raster) and NDWI water
   mask.
3. **Sunglint correction (Hedley et al., 2005)** from a deep-water sample polygon.
4. **Median composite** of several dates (deglint each date first). The date of each
   scene is read and a warning is given when they span too long (45 days by default),
   several seasons or several years; nothing is removed automatically.
   **Water clarity ranking** of the scenes in the list: deep-water red and noise and, with a
   polygon over a bright bottom, the bottom contrast (median R minus deep mean, in deep sd:
   the same as the bottom-signal test). Higher contrast = the bottom is seen deeper that
   day. Doubtful scenes are flagged (contrast below half of the best, cloud over the bottom
   polygon, noisy deep water) and only removed if you ask. Saves `scene_clarity.csv`.
5. **Water column**: Lyzenga (1981) depth-invariant bottom index for each band pair,
   from a polygon over one bottom type (usually sand) seen at several depths. The log
   gives the attenuation ratio and the correlation of each pair. Where R <= R_inf,
   R - R_inf is floored at one deep-water sd (no holes) and those pixels are flagged
   in `_floored.tif`: there the index does not measure the bottom.
6. **Classification** with reference points or polygons (one class field):
   - Features: reflectance bands and/or the depth-invariant indices. Depth can be
     added as a feature but it is off by default and not recommended (the error of
     an SDB depends on bottom colour, so it is tied to the classes).
   - **Three-state depth mask**: bottom visible (classified), bottom not visible
     (code 250, no data) and too deep for seagrass (code 251). The optical limit
     comes from a depth raster (StarShoal's limit is read from its metadata) and,
     optionally, the StarShoal trust raster. The ecological limit (35 m by default)
     needs an independent bathymetry (EMODnet, chart, multibeam); with only an SDB,
     everything past the optical limit stays "not visible".
   - **Bottom-signal test** (advised): with a polygon of optically deep water, a pixel
     is visible only if it differs from that water by more than n standard deviations
     in some band, so dark meadows drop out at shallower depth than sand.
   - Reference samples in the hidden or too-deep zone are dropped, with a warning.
     Polygons can be shrunk (inward buffer) to leave out mixed edge pixels.
   - Random Forest (scikit-learn) or Gaussian maximum likelihood (numpy only).
     Class balance is off by default: balancing finds rare classes more often but
     inflates their mapped area.
   - Validation with spatial blocks by class, common spatial blocks (full spatial
     separation) or random by feature; the pixels of one polygon always stay
     together. With polygons, accuracy is given by polygon (majority vote, the honest
     figure) and by pixel (optimistic). Accuracy by depth uses the independent
     bathymetry when given.
   - Optional clean-up of the final map: majority filter (3 x 3 or 5 x 5) and minimum
     mapping unit, saved as `classes_filtered.tif` (the raw map is kept; only class
     pixels change; the report checks both maps on the same validation samples).
   - Outputs: `classes.tif` (+ `.qml` style), `probability.tif` (max and per class),
     `legend.csv` (areas), `samples.csv` and `report.html` (confusion matrix,
     producer's and user's accuracy, F1, accuracy by depth range and Olofsson et al.
     (2014) error-corrected areas with 95 % intervals).
   - Optional export to polygons (GeoPackage: class, area_ha, perimeter_m per patch); also
     for change maps, and in Processing (`glub:polygonize_map`).
   - Optional bottom texture: local standard deviation in 3 x 3 or 5 x 5 windows of the
     water-column indices (else of blue and green) added as features; it helps with
     patchy versus smooth bottoms of similar colour (with 10 m pixels it may add little).
   - Optional minimum probability: if no class reaches it, the pixel is left
     unclassified (code 252) instead of forcing a class. The report gives the share of
     validation samples that fall there; the corrected areas treat that zone as one
     more stratum.
   - Depth sign: read from StarShoal's metadata; for other rasters, "automatic" looks
     at the values (mostly negative = elevation, as in EMODnet) and says so in the log.
7. **Validation** (for figures to publish):
   - **Generate points**: stratified random points by map class (Olofsson et al.,
     2014). Sample size by hand or from a target standard error of overall accuracy
     and an expected user's accuracy, n = (sum W_i S_i / S(OA))^2; allocation
     proportional to area with a minimum per class, or equal; the low-confidence zone
     is one more stratum; optional mask-check points in the hidden and too-deep zones.
     The minimum distance applies within a class only (map errors gather at class
     edges, and keeping points of different classes apart biased the areas in tests).
     Output: a GeoPackage with an empty `ref_class` field and lon/lat, plus a strata CSV.
   - **Assess the map** with the labelled points: confusion matrix, overall and
     user's accuracy with 95 % intervals, producer's accuracy weighted by area,
     estimated area of each class with its 95 % interval, and a mask-check table
     (`assessment.html`).

8. **Change** between two class maps of the same place (date 1 -> date 2): classes
   matched by name; only pixels classified on both dates are compared (not visible,
   too deep or low confidence on either date = not comparable). Outputs `change.tif`
   (one code per transition; seagrass loss in red, gain in green), `change_matrix.csv`
   (hectares), `change_report.html` and, with a minimum change unit,
   `change_filtered.tif`. Mapped change is indicative (the errors of both maps add up;
   the report gives 1 - OA1 x OA2 from the stored validation accuracies). For change
   areas to publish, draw stratified points on `change.tif` in tab 7 and label them
   on both dates.

**Simple and advanced mode** (Home tab): simple shows only the essential options of each tab,
advanced shows them all; hidden options keep their value. **?** buttons open the HTML manual
(`docs/html`) at the section of each tab or group.

Every tab can **save and load its settings** as JSON; classification, validation and
change also save them next to their outputs (`glub_settings_<tab>.json`).

## Language and QGIS versions

The window, the log and the HTML report follow the language chosen in the Home tab
(Spanish or English); the Processing tools use the same saved choice. Enum names
that changed between QGIS 3.28 and QGIS 4 are taken from `compat.py`, so the
plugin runs on 3.28+ without deprecation warnings (tested on 3.34; QGIS 4 and
Windows not tested yet).

## Memory

Every step works strip by strip (about 4 million pixels per strip, or whole blocks of
the source image); the classification keeps one byte per pixel for the whole raster.
On a synthetic 6000 x 6000 scene (36 million pixels) the peak memory was 0.5 to
0.85 GB, including the GDAL cache. Preparing a whole synthetic 10980 x 10980 tile
peaked at 0.9 GB (4.4 GB before strips), with identical output.

## What to expect

With Sentinel-2 the realistic target is seagrass / not seagrass in clear, shallow
water. Separating species, or live meadow from dead matte, is much less reliable.
The lower edge of a meadow usually lies deeper than the optical limit, so the map
does not show where meadows end in depth. The corrected areas assume a probability
sample of reference data; with points taken where it was possible they are
indicative.

## Manual

User manual in Spanish and English in `docs/` (also opened from the Home tab).

## Install (development)

Copy the `glub` folder into your QGIS profile plugins folder
(`Settings > User Profiles > Open Active Profile Folder > python/plugins`),
restart QGIS and enable it in the Plugin Manager.

## CDSE credentials

`Settings > Options > Authentication`, add a configuration of type **Basic**
with your CDSE username and password, and choose it in the download tool.

## Dependencies

GDAL and numpy (shipped with QGIS). Random Forest needs scikit-learn (on Windows,
from the OSGeo4W Shell: `python -m pip install scikit-learn`); without it, maximum
likelihood is used.

## Tests

`python tests/test_core.py` from the source repository (synthetic scene; the plugin
zip does not ship the tests).

## Authors

Daniel Ibarra-Marinas¹, Alejandro Fenollar-Rueda², Ana Mónica de Jhesú García-García¹,
Ángela Bellido-Solano³, Dulce Mata-Chacón⁴, Marta Serrano-Vicente⁵, Arturo Mora-Olivo¹

¹ Facultad de Ingeniería y Ciencias, Universidad Autónoma de Tamaulipas, Mexico ·
² Universidad de Alicante, Spain · ³ Universidad Complutense de Madrid, Spain ·
⁴ Instituto Español de Oceanografía (IEO-CSIC), Spain · ⁵ Universidad de Murcia, Spain

Contact: Daniel Ibarra-Marinas, daniel.ibarra@uat.edu.mx · ORCID 0000-0003-3683-4456 ·
[Google Scholar](https://scholar.google.com/citations?user=5JgVP2MAAAAJ&hl=en) ·
[ResearchGate](https://www.researchgate.net/profile/Daniel-Ibarra-Marinas) ·
GitHub [adanielibarra](https://github.com/adanielibarra)

## How to cite

Ibarra-Marinas, D., Fenollar-Rueda, A., García-García, A. M. de J., Bellido-Solano, Á.,
Mata-Chacón, D., Serrano-Vicente, M. and Mora-Olivo, A. (2026). GLUB (GIS Looking Under the
Blue) (version 1.0.0) [QGIS plugin]. Zenodo. https://doi.org/10.5281/zenodo.23186099

See also `CITATION.cff` (GitHub shows it as "Cite this repository").

## License

GPL-2.0-or-later (see `LICENSE`).
