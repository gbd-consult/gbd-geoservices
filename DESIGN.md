# gbd-geoservices -- design

How the system is built and why. For developers; `README.md` is for the people who run it, `TODO.md` lists what is open. The values of record are in the files this document points to -- `model/parameters.yaml`, `config/options.yaml`, the style files -- and the syntax of each file is documented in the file itself; this document explains the concepts behind them.

Paths are relative to `app/` unless they start at the repository root.

## Principles

1. **Classify once, at import.** OSM tags are read in one place, the importer's classifier. It gives every object a render class and a list of search categories, and precomputes every number a query would otherwise derive: the zoom it is drawn from, the zoom it is labelled from, its draw order, its label anchor, generalized geometry per zoom band, merged streets, the address path, phonetic codes. After the import the render tables hold no tags. A render query is always `WHERE class IN (...) AND minzoom <= z AND geom && bbox`.
2. **One import, in Python.** One pyosmium pass structure writes every table, render and search alike. No osm2pgsql, no second parse of the extract.
3. **One classification for map and search.** The render class and the categories come out of the same rule evaluation, so the map and the search cannot disagree about what an object is.
4. **Styles are data.** Four YAML files compile to Mapnik XML, a fifth to the legend. No CartoCSS, no external style compiler, no Node.
5. **The sea exists.** OSM has no ocean polygons, only coastline ways. The ocean is imported from osmdata's water polygons as a second input.
6. **Refuse rather than draw something wrong.** Most failures here produce no error: a tile that renders the wrong data, a query that returns the right rows by scanning a whole table, a label placed a zoom early. The generator refuses a style it cannot compile correctly, the importer refuses rules and styles that disagree, and tests pin the silent failures -- often by reading a query plan rather than a result.
7. **Measure every step.** The import times each of its steps; the two profilers (`tools/profile_render.py`, `tools/profile_search.py`) measure the renderer and the search against a fixed tile and query set. A change to a module is profiled, not just tested.
8. **The numbers live in one file.** Sizes, zoom bands, ranking weights, place radii and pre-cache depths are in `model/parameters.yaml`; code and SQL never carry one as a literal.

## Vocabulary

- **area** -- an extract the system can import: `li` (Liechtenstein), `de_sh` (Schleswig-Holstein), `de_nrw`, `de`. The `areas` option maps a name to a Geofabrik path.
- **schema** -- one import of an area, `<area>_<yyyymmdd>_<hhmmss>` ("Schemas and imports").
- **class** -- how an object is drawn: one name per distinct appearance (`cls_road_primary_bridge`, `cls_landcover_wood`). Column `class`, `class:` in the classifier rules, keys of `styles/classes.yaml`. Ids start `cls_`.
- **category** -- what an object is, for search and for its icon: a node of the category tree (`cat_poi_food_restaurant`). Column `categories`, `category:` in the rules. Ids start `cat_`.
- **importance** -- 0-100 per category (`model/importance.yaml`): how much an object of the category matters to someone looking at the map or searching.
- **color token** -- a palette entry named in `styles/classes.yaml` (`clr_primary`). Ids start `clr_`.
- **icon** -- an SVG attached to a category, its own or inherited (`styles/icons.yaml`).
- **layer** -- one drawing step of a theme, in draw order: the classes drawn in one mode (`styles/layers.yaml`).
- **mode** -- one of the looks a class can have: `fill`, `line`, `casing`, `label`, `shield`, `number`, `marker`.
- **detail** -- what a theme draws: `min`, `nav`, `std`, `max`, `topographic`, `vegetation` (`styles/details.yaml`).
- **palette** -- a set of colors: `default`, `light`, `dark`, `hico`, `grayscale`, `sepia`, `atkis`, `flora` (`styles/palettes.yaml`).
- **theme** -- palette × detail, named `<palette>_<detail>`: `default_std`, `dark_min`, `hico_max`. Forty-eight in all. A URL names it with `default` and `std` left off (`web/serving.py` `url_name`): `std`, `max`, `dark`, `dark_min` -- one name per theme, so no palette may share a name with a detail.
- **grid** -- a tile matrix set, by its WMTS identifier: `GoogleMapsCompatible` (EPSG:3857), `DE_EPSG_25832_ADV` (EPSG:25832), `DE_EPSG_25833_ADV` (EPSG:25833) (`styles/grids.yaml`). The two UTM grids are the AdV's TileMatrixSets of the same names (basemap.de), with the same levels; DE_EPSG_25833_ADV's origin lies further west, so it holds all of Germany too. A grid's *level* is not a zoom.
- **band** -- a range of zooms served from one table with geometry generalized for that range.
- **address path** -- the administrative areas a search row lies in, from the state down (`id_places`).

## Repository and runtime layout

```
app/                mounted as /app in the container; PYTHONPATH=/app, so its directories are top-level packages
  config/           options.yaml: every option with its default
  importer/         the import: pbf passes, classifier, geometry, COPY, post-processing, water polygons
  lib/              shared: config layering, db connections, text normalisation and phonetics, timing, version
  model/            what the system knows about the world: categories, rules, importance, parameters, search rules
    generated/      generated from the iD tagging schema and OpenMapTiles; never edited by hand
  renderer/         styles -> Mapnik XML, icons, queries, Map pool, cache, pre-cache, tile grids
  scripts/          host-side shell scripts: test.sh, gen_model.sh, deploy.sh, publish.sh, manage.sh
  search/           the four request modes, the phrase rules, ranking, result shaping
  styles/           layers, classes, colors, details, icons, grids; icons/ holds the vendored SVGs
  tests/
  tools/            manage.py, gen_classifier.py, rule_stats.py, the profilers
  web/              HTTP routes only; devtools/ is the development viewer
config.example/     template of a deployment's configuration directory
config.local/       the dev stack's configuration (tracked; dev password only)
config.test/        the test stack's
profiles/           baseline profiles for further development
```

`app` itself is never imported. Entry points are `uvicorn web.main:app` and `python tools/manage.py`. A route in `web/` only translates: `/xyz/...` becomes a `renderer` call, a `/search` body a `search.api.find` call. `manage.py`, the devtools and the profilers call the same functions directly.

Everything that outlives a container is under `/data`:

```
/data/downloads/              extracts and water polygons, fetched once and reused
/data/styles/<schema>/<grid>/ compiled Mapnik XML, one file per theme
/data/styles/icons/<hash>/    the icon set, by content hash
/data/elevation/               the resampled model while init-elevation runs, removed after
/data/cache/<area>/           the tile cache, both tiers
/data/import.log              the import log, one section per run
/data/log/<service>.log       the services' logs, written by the host's rsyslog
/data/import.status           held (flock) while an import runs
```

## The model

Files in `model/`. Hand-written: `categories.yaml`, `classifier.yaml`, `importance.yaml`, `parameters.yaml`, `search_rules.yaml`. Generated by `tools/gen_classifier.py` (run through `scripts/gen_model.sh`) into `model/generated/`: `categories.yaml` and `classifier.yaml`. The generated files name their sources, with version, URL and licence, in their headers.

### Sources

- The **iD tagging schema** (`@openstreetmap/id-tagging-schema`, pinned): ~1 700 presets, each with its tags, allowed geometry, a folder-like hierarchy (`amenity/cafe/bubble_tea`) and names and search terms in `de` and `en`.
- **OpenMapTiles' layer definitions** (pinned): the grouping of tag values into render classes for the poi, landcover, landuse, transportation, water, waterway, place and aeroway layers.

### The category tree

`model/categories.yaml` is the tree anyone edits: three top levels -- `cat_geography`, `cat_built`, `cat_poi` -- about 22 second-level categories below them and ~245 leaves. Each node lists the iD presets that map into it. The generator makes it **deep**: every preset a node claims becomes a child of the node, nested the way iD nests them, with iD's names and terms -- except the node's `main` preset, which is the node itself. The deep tree keeps search precise ("Metzger" finds butchers, not every grocery shop) while the edited tree stays short. A filter on a parent still returns every descendant, because objects store their categories with all ancestors.

The generator refuses a preset id that does not exist in the pinned iD version and a preset listed at two nodes, and reports every kept preset no node claims.

A node marked `marker: true` (all of `cat_poi`, and parking, fuel, stops and a few more elsewhere) gives its presets a POI class, so they are drawn as icons.

### Classifier rules

A rule is `match`, `category`, and optionally `class`. The importer reads the hand-written `classifier.yaml` first and the generated one after it. Evaluated top-down per object:

- the first matching rule that has a class sets the class (`class: none` decides that there is none);
- the category of every matching rule is collected; the first one is the object's own (`category`);
- a bare `key=*` fallback counts only when no other matching rule names its key -- otherwise `amenity=*` would file every restaurant under "other amenity" as well.

The generated rules are one per preset, most specific first. The class comes from the OpenMapTiles grouping; a POI's class is one per second-level category (`cls_poi_food`), because what tells a cafe from a bakery on the map is its icon. A tag that is both an area and a POI kind (`amenity=hospital`) yields two rules, a landuse class for polygons and a POI class for points. The hand-written rules cover what iD cannot: bridge and tunnel variants, intermittent water, boundaries by admin level, administrative areas as search-only categories, protected areas, coastline, and the vegetation units the OpenMapTiles grouping merges (wood by leaf type, scrub, heath, bog, orchard and vineyard), which every palette colours apart for the `vegetation` detail.

`gen_classifier.py` also reads `styles/classes.yaml` and warns, both ways, where the rules and the style disagree -- before an import rather than after.

### The compiled classifier

Evaluating a thousand rules per object in Python would be too slow, so `importer/rules.py` compiles them:

1. Every `key=value` and `key=*` the rules mention gets a bit; the keys that occur are the relevant keys.
2. A conjunction is a bitmask; each mask is indexed by its rarest bit, the trigger.
3. Per object, the relevant tags are ORed into one integer, and only the rules whose trigger bit is set are tested.
4. The whole result -- class, categories with ancestors, importance -- is memoized on (bits, geometry kind). A few thousand distinct tag sets cover millions of objects, so almost every classification is a dictionary lookup.

### Importance

`model/importance.yaml` maps any node of the generated tree to 0-100: 100 essential, 80 major, 60 everyday, 40 neighbourhood, 20 incidental, 0 ignored. A node without an entry inherits its nearest listed ancestor's. Importance 0 is never found by search and never drawn as an icon: the importer writes no search row for it. It orders search results (times `ranking.importance_weight`) and decides from which zoom a theme draws an icon ("Icons"). The importer refuses a key that is not a node, so a stale id after an iD upgrade fails the import instead of doing nothing.

## Import

`tools/manage.py import <area>` → `importer/run.py` `import_area()`. Inputs: the extract (`.osm.pbf`, downloaded by `importer/extract.py`), osmdata's water polygons, the contour lines of the schema `elevation` ("Contour lines"), the model files, and `styles/classes.yaml` for the zooms each class is drawn and labelled from. The steps, each timed and logged as `[n/16]`:

1. **Schema.** A new schema `_<area>_<timestamp>`, tables `UNLOGGED`. Before anything is written, the class sets of the rules and the style are compared; drift aborts the import.
2. **Passes.** A relation pre-pass collects the ways of administrative boundaries with their lowest admin level. Then nodes, ways and areas run as separate pyosmium passes (`with_locations()`, `with_areas()`), in parallel up to `--pass-workers`. Each classifies its objects, builds the geometry (osmium WKB → shapely → EPSG:3857 by the spherical Mercator formula, vectorised per batch), computes sizes, zooms, `z_order`, label anchors and building heights, and writes with `COPY`.
3. **Water.** Both osmdata sets clipped to the extract's bbox plus `water.bbox_margin_deg`, written as `cls_ocean` polygons.
4. **Contours.** The lines of `elevation.contour` in the extract's bbox plus `contours.bbox_margin_deg`, cut at its edge, into `osm_contour`. Without the schema an area gets none and the import goes on.
5. **Merge streets.** Union-find over named road ways that share an end node *and* a normalised name; no distance fallback, so same-named streets of neighbouring villages stay apart. One search object per connected component.
6. **Merge places.** A place node is folded into the administrative area of its name that contains it: one search row with the area's polygon and the node's category, importance and centre.
7. **id_object.** Each address is linked to the named object it sits on.
8. **Places.** The address path ("Address path").
9. **Dictionaries.** `osm_category_term` from the generated tree's names and terms; `osm_street` from the merged streets.
10. **Bands.** The generalized tables ("Zoom bands"), then the water bands from the simplified osmdata set.
11. **Order.** The full render tables are rewritten in Hilbert order of their bbox centres, so a tile reads contiguous pages.
12. **Indexes**, over `import.index_workers` connections: partial GiST per layer where a layer's classes are a real subset of a table, trigram, phonetic and GIN indexes on the search tables.
13. **Cluster** the band tables on their GiST index.
14. **Drop working tables**, then **finish**: `SET LOGGED`, `VACUUM ANALYZE`, write `import_meta`, log what moved against the previous import, rename the schema without its leading `_`, and drop all but the two newest complete schemas of the area.

A way that is both a border and something else (a river along a municipal boundary) is written twice: once as the border, once as itself. Border ways tagged `maritime=yes` are not drawn, so sea borders do not cross the water.

### Contour lines

`manage.py init-elevation` → `importer/elevation.py` `init()`, run once and again only when the rasters or the `contours` parameters change. With `--download` it first fetches the GLO-30 tiles of the `elevation_tiles` option from `elevation_base` into `downloads/rasters_COP30/` (`download()`), skipping those on disk; a 404 is open sea. It mosaics the GeoTIFFs the `elevation_sources` option names (globs under `data_dir`; the Copernicus GLO-30 tiles of Germany), resamples them to `contours.cell_m` in EPSG:3857 by averaging, contours them at the finest of `contours.levels_m` with GDAL (`gdal-bin` in the image), and writes the lines into the schema `elevation`, which belongs to no import: each line in the class of the coarsest level its height is a multiple of (`cls_contour_1000` ... `cls_contour_50`), the 0 m line dropped (the coast is OSM's, and on land it is the model's noise in the marshes), closed lines shorter than `min_ring_m` dropped, simplified and cut into pieces of at most `subdivide_vertices`, so a tile reads only the pieces it touches. A run builds a new table and swaps it in, so an import copies the old lines or the new, never half. `elevation.meta` records the sources and the parameters. GLO-30 is a surface model: the averaging and the ring filter damp canopy and roofs, they do not remove them. On the map the levels come in one per zoom, coarsest first -- 1000 m from z9, then 500, 250, 100 and 50 m -- each from where its lines stay readable on steep ground, and stay (`styles/classes.yaml`); a level is a layer of its own with its own partial index, so a low zoom never reads the fine levels. The data is free on condition of its credit, which `/metadata` and the WMTS capabilities add when the served schema has contours.

### Schemas and imports

Every import writes a schema of its own, `<area>_<yyyymmdd>_<hhmmss>`, named with a leading `_` until it is complete. A schema without an `import_meta` row, or with a leading `_`, is an incomplete import; the next import of the area drops it. The two newest complete schemas are kept -- the one just written and the one still served until the reload, which is also the rollback. The server serves the newest complete schema of `serve_area`, resolved at start and on `/internal/reload` (`lib/db.py` `active_schema()`), or `force_schema` when that is set.

Compiled styles are per schema; the tile cache is per area and survives imports. Nothing empties it as a side effect -- `manage.py drop-cache` does.

`import_meta` records the area, the extract's timestamp and replication position, the duration, row counts, the bbox, the zooms each class's rows were written for (`style_zooms`), the classes each render table holds (`table_classes`), and which icon mapping was last applied (`icons_applied`). Updates are a full re-import; the replication position is kept so a diff path could be added later.

Whether an import came out sane is reported, not checked: the import log lists the counts of `row_counts` and `table_classes` that moved against the area's previous import by more than `import.report_change_pct` and at least `import.report_min_rows` rows, and every one that appeared or vanished (`importer/changes.py`). Nothing fails on it -- a model change moves counts on purpose, and OSM grows between imports. Per class, not only per table, because a broken rule takes one class to zero while its table moves by under 1 %.

The import appends to `/data/import.log` and holds `/data/import.status` locked while it runs, so a second import of any area refuses to start. Each log line is prefixed with the seconds since start and the available memory.

## Database

All render geometry is EPSG:3857, all search geometry EPSG:4326. Other grids are rendered by Mapnik reprojecting from 3857. Reprojection adds 17-36 % to a tile of the same ground and never dominates it, so there is no second geometry column per CRS.

The table definitions of record are `importer/tables.py`: column list, DDL, `COPY` column list and indexes from one declaration.

### Render tables

`osm_point`, `osm_line`, `osm_polygon`, `osm_building`, and the band tables share `osm_id` (negative for relations), `class`, `name`, `label` (road ref, house number, elevation), `z_order`, `minzoom`, `minzoom_label`, `geom`.

- `osm_point` -- POIs, place nodes, and one anchor point per area whose class is drawn as a marker, so a restaurant mapped as its building still gets its icon. Adds `category`, `icon` (set by the style run, not the import) and `importance`.
- `osm_line` -- roads, railways, waterways, boundaries. Line labels and shields read this table on `minzoom_label`, because Mapnik cannot place text along a line from a point.
- `osm_polygon` -- landcover, landuse, water, the ocean. A multipolygon is one row per part.
- `osm_building` -- buildings only, with `height` and `height_src`. Keeping millions of buildings out of `osm_polygon` keeps them out of every low-zoom query.
- `osm_contour` -- contour lines, copied from `elevation` by the import, `label` the height. Its own table so that no other layer's bbox scan reads them; no bands, since each level is its own layer and a low zoom reads only the coarse levels, which are few lines.
- `osm_label` -- one point-placed label per object with a name or a label: areas, places, buildings. Carries `category`, `icon` and `importance` like `osm_point`, for a label that yields to its icon.

### Zoom bands

A low-zoom tile covers so much ground that the full tables return hundreds of thousands of rows whatever the index. A band table holds the same data prepared for a range of zooms (`bands` in `parameters.yaml`):

| suffix | zooms | geometry |
|---|---|---|
| `_z6` | 0-6 | simplified to 0.5 px at z6; polygons unioned by class and lines merged by class, within 4° cells |
| `_z9` | 7-9 | 0.5 px at z9; unioned within 1° cells |
| `_z12` | 10-12 | 0.5 px at z12; no union |
| (full) | 13+ | as imported |

Anything under a pixel at the band's finest zoom is dropped. Polygons enter a band by their own `minzoom`, lines by their class's: OSM cuts a motorway at every junction, and no single way would pass a size test at z6, so the merge reassembles the road and the pixel filter after it is the size test. A merged run carries its class's minzoom. In `_z9` and `_z6` one row is many objects, so `osm_id` is 0 and there is no name. Grid cells bound the memory of `ST_Union`. Band tables are clustered on their GiST index.

### Sizes and zooms

Pixels are Web Mercator pixels (156 543 units/px at z0, halved per zoom); area and length are measured on the 3857 geometry, which is what a tile is drawn in, so no latitude correction applies. The thresholds are `size` in `parameters.yaml`:

- An area is drawn from the zoom where it covers `polygon_px2` (4 px²; buildings 1 px²), and not before its class's start zoom: `minzoom = max(class zoom, ceil(log2(156543 * sqrt(px2 / area))))`.
- A line is drawn from its class's start zoom, whatever its length -- a per-way length test drew main roads as dashes.
- A label needs 400 px² on an area and 100 px of length on a line, again not before the class's label zoom.
- A point has only its class zoom.

A class's start zoom is the lowest zoom key it has in `fill`, `line` or `casing` in `styles/classes.yaml`, its label zoom the lowest in `label` or `shield`. The style is the only place these are written, and the importer reads them from it. Since the rows carry the start, moving a class earlier needs a re-import: the import records what it wrote in `import_meta.style_zooms`, and the style compiler refuses a style that starts a class earlier than that. Moving one later needs only a style run. A class the style never draws as geometry (POIs, places) gets `zoom_max`, which keeps it out of the bands.

### Draw order

`z_order = layer_tag * 1000 + rank`, `layer_tag` the OSM `layer` tag clamped to -5..5, `rank` from `z_order.rank` in `parameters.yaml`, looked up by the class or the longest key that is a prefix of it. Drawn layers sort ascending, label layers descending. For places `z_order` is the population, so larger places win the label collision.

### Search tables

- `osm_search_object` -- one row per named, categorised thing, or per merged street. `id` serial (a merged street has several OSM ids, `osm_ids`). `name`, `search_name` (normalised), `search_text` (name plus address text), `phon_name` (Kölner Phonetik), `search_city`. `categories` is every matched leaf plus all ancestors, so any category query is one GIN containment test with no tree in the database. `category` is the object's own, `importance` the category's (NULL without a category; an unnamed object has no row). `addr_*`, the object's own address. Exactly one of `geom_point`, `geom_line`, `geom_polygon` -- Multi-, so one object is one row -- plus `geom_center` for ranking and distance. `tags` (jsonb, for display only). `id_places`, the address path.
- `osm_search_address` -- one row per address: street, normalised street and its phonetic code, postcode, city, house number split into `number` and `number_part` (so a street reads 1, 2, 2a, 3), the point, `osm_id` of the object it sits on, `id_object` when that object has a search row, `id_places`, and the carrier's own `category`.
- `osm_category_term` -- the phrase parser's dictionary: one row per (normalised term, category, language) from the generated tree's names and terms, with a phonetic code.
- `osm_street` -- distinct normalised street names with a count; the phrase parser finds streets here.

Distance is ranked in metres through a functional GiST on `(geom_center::geography)`: `<->` on a 4326 geometry returns degrees, and at 54° N a degree of longitude is 0.59 of one of latitude.

## Address path

`importer/places.py`. `id_places` on `osm_search_object` and `osm_search_address` holds the ids of the administrative areas a row lies in, from the state down: every `boundary=administrative` area of `places.levels` the row intersects, tested against the areas after `ST_Subdivide`.

- A point lies in one area per level; a line in every area it touches.
- An area object lies in an area holding at least `places.area_share` of it. A park split across a border is in both municipalities; a district is not in the Ortsteile it contains, nor in a neighbour its boundary misses by a sliver.
- An administrative area lies only in areas of a lower admin level.
- Only objects of `places.categories` get a path -- a river would collect every municipality it passes. Every address gets one.
- A place mapped as a node has no border, so nothing lies in it. The path stops at the finest area, and the phrase search finds names near such a place by radius instead.

`places.levels` is German: what a level means differs per country. A result carries its path as `places`, largest first.

## Rendering

### Style files

`styles/`, one file per concern and no file per theme:

- `layers.yaml` -- draw order. Each entry is a mode and the classes (globs) drawn in it. The table a layer reads follows from the mode and from which tables actually hold the layer's classes (`import_meta.table_classes`), so one entry can become several Mapnik layers.
- `classes.yaml` -- appearance per class, mode and zoom, with colors only as tokens. A section per mode, keyed `"<class> <zoom>"` (from that zoom on) or `"<class>"` (every zoom); `defaults` per mode and `templates` (YAML anchors) for sharing. `*` on the class part is refused: sharing goes through templates and tokens, not cascading.
- `palettes.yaml` -- palettes: token → color, plus the few numbers that differ per palette (`halo_radius`, `casing_scale`). A token set to `none` leaves out what is painted with it: the rule is not compiled, a layer left without rules is not either, and the legend does not show it (`resolve.Styles.omits`).
- `details.yaml` -- per detail, the class globs it draws, optionally restricted to modes (buildings with their house numbers but not their names), and `symbols`, which importance draws icons and icon labels from which zoom. `min` is the least a map needs, water, settlement areas and the connected road network down to the residential streets, without buildings, landcover or POIs; `nav` holds only what navigation needs, every street with its name, buildings with house numbers, the rest reduced and no POIs; `std` is the full map, `max` draws everything, contours included; `topographic` is `std` with the contours, `vegetation` every vegetation unit with only the main roads, rail, borders and places for orientation.
- `icons.yaml` -- category → icon, color token and `draw`, each inherited down the tree on its own.
- `legend.yaml` -- what the legend shows: groups of classes and category icons, and the zoom whose style it shows ("Legend").
- `grids.yaml` -- the tile grids: CRS, origin, level-0 span, level count, and the latitude its units are compared with Web Mercator at.

Resolving one (class, mode, zoom) (`renderer/resolve.py`): the mode's defaults, then every entry of the class whose mode is `*` or the mode and whose zoom is at most the zoom, in ascending zoom, `*` before the specific mode; later entries override single properties. Tokens are then replaced from the palette, and every casing width is multiplied by `casing_scale`.

### Compiling

`renderer/styles.py`, run by `manage.py compile-styles` and by the app at every start for the schema it serves. One XML per theme and per served grid, into `/data/styles/<schema>/<grid>/<theme>.xml`. One Mapnik `<Layer>` per (layer, table, band), one `<Rule>` per (class, zoom key) with a class filter and a scale-denominator range, the symbolizer type following from the property names. Datasources carry only `table`, `geometry_field`, `srid` and `extent`; the connection comes from libpq's environment, so the XML holds no credentials and is the same on every deployment.

Before writing anything the compiler checks: every class styled exists in the rules and every class classified is styled (else a warning); every glob matches a class of the model; every token resolves in every palette, including `land` and `casing_scale`; no color literal in `classes.yaml`; every font named is installed; no class starts earlier than its rows were imported for; icon mappings where a more important icon starts later are refused. A failed compile at app start is logged and the XML already on disk is served.

Two details of the XML are load-bearing:

- **Rule boundaries lie between zooms.** Mapnik's scale denominator and ours differ in the last bits, in either direction, so a boundary exactly on a zoom's denominator falls on either side of it. Each boundary is at the geometric mean of two zooms' denominators.
- **One file per grid.** Mapnik reports `!scale_denominator!` in the units of the Map's own srs. For EPSG:3857 those are Web Mercator units, in which every `minzoom` is written; for a metre grid they are ground metres, 1/cos(lat) times larger. The grid's `metres_factor` (cos of its declared latitude) converts a level's denominator into the Web Mercator zoom, and it is baked into both the rule ranges and the query, so a file compiled for one grid cannot serve another. DE_EPSG_25832_ADV level 8 (19 m/px) therefore reads the `_z12` tables, as Web Mercator z12 does.

### Queries

`renderer/queries.py` generates each datasource's SQL; there is no hand-written SQL in the styles.

```sql
select class, geom from de_sh_20260930_101500.osm_polygon_z12
where class in ('cls_landcover_wood', ...) and minzoom <= <zoom from !scale_denominator!> and geom && !bbox!
order by z_order
```

The band decides the table, fixed per `<Layer>`, and the layer's scale range is bounded to the band's zooms; `minzoom <= z` is evaluated per tile. No `!pixel_width!`, no area expressions, no `CASE` over tags. The only `CASE`s are the marker layer's importance floors, step functions of the zoom alone, which Postgres folds to a constant per query.

### Icons

Icons are attached to categories, not classes. `renderer/icons.py`, run with every style compile:

- resolves `styles/icons.yaml` (Maki icons, CC0, vendored under `styles/icons/maki/`, and a generic POI icon of our own);
- writes one SVG per (icon, color) pair actually used and per palette, from `styles/icons/template.svg`: a white disc, a colored disc, the icon in white. The color is baked into the file, because a marker's `fill` would recolor the white parts too. The set goes into a directory named by its content hash, so a reloaded Map is never served a stale SVG from Mapnik's marker cache;
- sets `osm_point.icon` and `osm_label.icon` to the pair's key for every row whose category is drawn, NULL for the rest. The marker query skips NULL, so an undrawn category is never fetched. The update is skipped when the mapping has not changed since the last compile (`import_meta.icons_applied`).

Changing an icon, a color or whether a category is drawn is therefore a style run, never a re-import.

Which icons a theme draws is not a class list: `symbols.icons` in `details.yaml` maps importance to the zoom icons of at least that importance start at, `symbols.labels` the same for their names. The marker query carries both as `importance >= CASE <zoom> ...`. An icon and its name are one Mapnik `ShieldSymbolizer`, placed together or not at all: a name never stands where its icon lost the collision, at the cost that an icon whose name does not fit is dropped too. An area with a marker class (airport, hospital, zoo) is labelled as an area below its icon's zoom, and by its icon from there on.

### Legend

`renderer/legend.py`, run with every style compile after the XML. `styles/legend.yaml` says only what the legend shows -- groups of class entries with a message id, and groups of icons -- never what an entry looks like. A class entry is drawn by Mapnik with the symbolizers the theme's own XML carries for that class at the legend's zoom (`styles.symbolizer` over `Styles.paint`), on a short line or, for a filled class, a box; a class with no geometry, a place, is its entry's text written in the class's label style. A changed color or width therefore reaches the legend with the next style run, and a legend cannot drift from its map.

The legend shows everything the map draws, and the compiler refuses one that does not: every class drawn in a mode other than `marker` must be named by an entry -- classes that look alike share one, drawn as the first of them the theme draws -- and every icon a detail draws must lie under an icons group. An icons group names category subtrees and is filled by the compiler: one row per icon (`<icon>.<colour>`) a theme draws for a category under them, named as the most general of those categories other than the group's own, in alphabetical order; a category entry renames an icon. Which icons the map can draw at all comes from the classifier: those of categories a rule gives a class with a marker (a city has an icon, but on the map it is a name).

A theme shows what its detail draws: a class the detail does not list, or lists only in other modes, or its palette paints `none`, is left out, and an icon only where the detail's `symbols.icons` reach the category's importance at some zoom. One PNG per theme and language of `languages`, into `/data/styles/<schema>/legend/<theme>.<lang>.png`; with every icon, `max`'s is some 6 700 px tall, and a client scrolls it (the devtools panel fits the map's height). The legend is itself a Mapnik Map in pixel units with an inline GeoJSON datasource; it is rendered once without a background to measure how wide its texts are, then at that width on the palette's `clr_land`, so a dark palette's light text stays readable in a client's white legend panel.

The compiler also refuses a legend entry whose classes do not exist or draw nothing at its zoom, an unknown category or one without an icon, and a text id missing from `lib/messages.yaml`. `/legend/{theme}.png` serves the file (`web/legend.py`), and the WMTS capabilities name it as each layer's `LegendURL`, which QGIS and GWS follow on their own; an XYZ client has no such mechanism.

### Symbols at tile seams

Each 256 px tile is rendered on its own, with its own collision detection. A symbol near a seam lies in both tiles' buffers; one tile places it, the other may drop it in a collision only it sees, and the seam shows half an icon. So symbols are drawn with `avoid-edges`, which Mapnik measures against the Map extent plus the *Map* buffer: the Map buffer is 0 and each `<Layer>` carries the buffer (`buffer_px`) instead, which widens only the query. Lines and outlines at the seams still come from features beyond the tile; a symbol that would cross the seam is not drawn in either tile. That is a missing icon rather than half of one. Metatiling -- rendering several tiles as one image and cutting it -- would keep them ("TODO.md").

### Map pool

`renderer/core.py` `MapRegistry`: per (theme, grid) a pool of `map_pool_size` Mapnik Map objects, loaded at process start and reused, never loaded per request. `render_tile(theme, bbox, fmt, grid)` takes a bbox already in the grid's CRS, and a `size` for a WMS map. Mapnik's PostGIS plugin opens a connection per layer while loading a Map and keeps its own connection pool while rendering, one for the whole process, sized by `db.mapnik_pool_size` (`max_size` in the XML): a render that finds it full fails instead of waiting, so it is at least the number of concurrent renders. A render that fails on a lost connection (after a Postgres restart) is retried, evicting one dead pooled connection per attempt; any other error is not.

Postgres is reached through pgbouncer in session mode, trusting its clients: a Map load is a fresh backend and a SCRAM exchange per layer otherwise, ~0.95 s per Map against ~0.06 s through pgbouncer.

PNG tiles are encoded as 8-bit palette images; Mapnik spells JPEG `jpeg`, the API `jpg`.

### Cache and pre-cache

`renderer/cache.py`: two filesystem tiers under `/data/cache/<area>/`, keyed `theme/grid/format/z/x/y`. The pre-cache tier holds each grid up to its `precache` depth (`GoogleMapsCompatible: 12`, `DE_EPSG_25832_ADV` and `DE_EPSG_25833_ADV: 8` -- about the same ground resolution), seeded offline by `manage.py pre-cache`; it is never evicted. The on-demand tier holds everything deeper, bounded by `ondemand_cache_max_mb`: the serve path counts the bytes it writes and walks the tier only after a quarter of the limit, then evicts to 90 % (`web/serving.py`). From a grid's `nocache_from` level on (`GoogleMapsCompatible: 20`, `DE_EPSG_25832_ADV` and `DE_EPSG_25833_ADV: 16`) nothing is cached: such a tile renders as fast as a z16 one but is rarely asked for twice, and caching it would evict tiles that are. `nocache` replaces both tiers with nothing, for style work.

For a non-3857 grid the pre-cache is where the reprojection is paid, once.

## Search

`search/`, entry points in `search/api.py`: `find`, `count`, `categories`. One request body for four modes; every result is a GeoJSON Feature with the same flat properties.

### Modes

- **name** -- a name the client knows: the text normalised the way the importer normalised `search_name` (case, umlauts, "Str."), compared by equality, one btree probe. Only when that finds nothing, the fuzzy name search (below) at `ranking.relevance.name_fuzzy`, unless the request's `relevance` is above it. `/search/fuzzy` runs that fuzzy name search alone, without the exact pass; the devtools' fuzzy box switches the name mode to it. With `categories` and no text, the category browse.
- **address** -- `street`, `housenumber`, optionally `postcode` and `city`, as fields, each an exact condition: the street after normalisation, the house number with its suffix ("12" is not "12a"), the postcode, and the city against the folded `addr:city` or any place on the address path. What matches is returned, what does not is not. Without postcode or city every match is returned, nearest first when the request has a point.
- **phrase** -- free text: any mix of name, category, place, street and address, typos included in the last step ("Phrase").
- **point** -- what lies at a point: the nearest address first, then points and lines within the radius (50 m and 25 m by default, `radius` replaces both), interleaved by distance, then the areas that contain the point, smallest first. Areas are where the point is, not what was clicked.

Common to all: `bbox` or `area` as a spatial filter (`within` requires containment, the default is intersection, so a river crossing the view is found), `near` for distance, `categories` (a category and its whole subtree), paging, `/count`, and on every result its address path and a `relevance`.

### Relevance and score

`match_relevance` is 0-100 and says how literally a result matched, comparable across modes: an exactly matched address 100, an exact name or a point hit 99, the name mode's fuzzy fallback 20, the phrase steps below that (`model/search_rules.yaml`). The request's `relevance` drops results below it; in the phrase mode the steps below it are not run. `match_score` orders within a mode and is not comparable across modes.

The score of a fuzzy name match (`search/rank.py`) combines three channels, because a typing mistake fails each differently: trigram similarity (transposed or dropped letters), word similarity (a fragment of the name), and the Kölner Phonetik code (what the word sounds like), with bonuses for an exact and a prefix match, and `ranking.inside_view_bonus` for a centre inside the view. The floors (`min_score`, the phrase mode's strict ones) judge that text score; importance × `ranking.importance_weight` is added after them (`rank.build_sql`), so it orders what matched and lets nothing in. The weights are bound as parameters from `ranking` in `parameters.yaml`, never written into the SQL. `similarity` (1-10) maps onto pg_trgm's thresholds, which are also the latency knob. A fuzzy query that finds nothing retries once with relaxed thresholds.

Equal scores are ordered by distance from `near` or the view's centre, so the nearest of 400 equal Hauptstraßen comes first.

### Phrase

"restaurant Kiel" and "restaurant Maxim" have the same shape and mean different things, and nothing in the string says which. So the parser does not decide (`search/phrase.py`): it produces every reading the dictionaries support -- category terms (`osm_category_term`, longest match first), places (search objects of the place and admin categories, at either end of the query), streets (`osm_street`, anywhere), address readings ("street number postcode/city", "city street number") -- and the rules of `model/search_rules.yaml` are matched against them.

A rule is quasi-SQL over a closed set of atoms -- `category = query.category AND location IN query.place` -- compiled per reading into one indexed statement (`search/rules.py`). A rule the grammar or the atom set does not allow is refused when the file is loaded. Rules come in **steps**, each with its relevance. A step runs all its rules on every reading that has exactly the rules' parts; the first step that returns rows is the answer, and the steps below it do not run. Step 1 reads the whole query as a name or a category term and needs no parsing; the full parse runs only when step 1 finds nothing. The last step, the fuzzy one (`name LIKE query.text`, typos and prefixes), runs without the near-miss phonetic probe, which nothing narrows there (`search/name.py`); the step before it (`name_nearest_place`, `address_like`) is disabled.

- `name = query.name` beside a place -- the name, or the name with the place before or after it ("Hauptbahnhof Kiel" is mapped as "Kiel Hauptbahnhof").
- `name LIKE` with another part runs strict: at `phrase_strict_min_score`, and no lower than `phrase_strict_best_share` of the rule's best row.
- `location IN query.place` -- the place's id on the address path, or, for a place with a border that is no administrative area (a region), containment in its polygon.
- `location NEAR query.place` -- within `place_radius_km` of a place mapped as a node only.
- `location NEAR query.street` -- within `near_street_distance_m` of the street of that name nearest the request's location, plus the rows of that name within `near_street_group_m` of it.

Each rule is capped; `total` is the size of the merged list, not a true count. The response reports every rule that ran as `interpretation`: its id, its quasi-SQL, its row count, and the reading's parts.

### Shape

`search/shape.py`. The response is `{page, limit, count, total, has_more, interpretation?, results}`, `results` a plain FeatureCollection. Every feature has the same properties, in the same order, null where they do not apply: `name` (`''` when unnamed -- a display title is the client's to build), `category`, `category_name`, `categories` (`{id, name}` from the root down), `icon` (URL), `center`, `places`, `match_relevance`, `match_score`, `match_rule`, `match_distance`, `address_street`, `address_housenumber`, `address_postcode`, `address_city`, `osm_ids`, `osm_tags`. `geometry` is the highlight: the point, the merged street, the simplified polygon. Feature ids are `o<id>` for objects and `a<id>` for addresses, whose serials overlap.

An address hit with an object behind it is that object, with the matched address in `address_*` and the address point as `center`. Without one it is a pure address, shown as the category of what it sits on ("Wohnhaus"), or "Adresse" for an address node.

Names follow `lang`. Responses are cached per request for `search.cache_ttl_s`; the tables change only with an import.

### Two traps

- psycopg binds `%(name)s`, so pg_trgm's `%` and `<%` are written `%%` and `<%%` in every SQL string with parameters. A single `%` raises only when the statement runs. `tests/test_rank.py` checks the module's SQL.
- A CTE without `MATERIALIZED` is not a fence: Postgres inlines it and pushes an outer `WHERE score >= x` down into the base scan, scoring the whole table before the join that was meant to narrow it. The scored CTEs are `MATERIALIZED`, and a test counts the subplan's loops in the plan. The view (`bbox`/`area`) is the opposite case: it is written in place as a constant geometry, not read from a CTE, so the planner can estimate it from the table's statistics.

## Web

`web/`, FastAPI, one uvicorn worker per container: the Map pool and the search cache are per process, and concurrency comes from `map_pool_size` threads. Tile routes are synchronous functions, run in worker threads, because a render is blocking C++.

### Routes

| route | |
|---|---|
| `GET /xyz/{theme}/{z}/{x}/{y}.{png,jpg}` | raster tile, GoogleMapsCompatible |
| `GET /wmts/{theme}/{grid}/{level}/{col}/{row}.{fmt}` | raster tile in any served grid |
| `GET /wmts?SERVICE=WMTS&REQUEST=GetCapabilities` | the served grids and themes; ResourceURLs carry the caller's key, each layer's `LegendURL` the `?lang=` asked for |
| `GET /wmts?...&REQUEST=GetTile&...` | KVP GetTile, same handler |
| `GET /wms?SERVICE=WMS&REQUEST=GetCapabilities` | WMS 1.3.0: one layer per theme, every served CRS; OnlineResources carry the caller's key |
| `GET /wms?...&REQUEST=GetMap&...` | a map of any bbox and size, uncached |
| `POST /search`, `POST /search/count` | the four modes; the total for the same body |
| `POST /search/fuzzy`, `POST /search/fuzzy/count` | the fuzzy name search alone; its total |
| `GET /icons/{category}.svg` | a category's icon; no key |
| `GET /legend/{theme}.png` | a theme's legend (`?lang=de\|en`); no key |
| `GET /metadata` | what a client needs, one document; no key |
| `GET /status` | what an operator needs; any valid key |
| `GET /`, `/health` | landing page (`?lang=de\|en`), liveness; no key |
| `POST /internal/reload` | loopback only: re-resolve the schema, load the compiled XML |
| `/devtools` | the viewer, only with the `devtools` option |

`{theme}` and a WMTS layer are a theme's URL name. A tile outside the pyramid, an unknown theme or an unserved grid is 404, never an on-demand render. A request while the area has no complete import is 503. Tile routes answer `HEAD`.

WMS (`web/wms.py`) renders a GetMap as one image on a pooled Map, resized to WIDTH x HEIGHT and back by the next tile, with the bbox kept exactly (`aspect_fix_mode` RESPECT). A CRS renders with the compiled XML of its grid, so it is offered only when that grid is served; EPSG:4326 uses the GoogleMapsCompatible file, since Mapnik turns a geographic scale into metres at the equator's metres per degree, the unit the `minzoom` columns are written in. In 1.3.0 an EPSG:4326 BBOX is lat/lon. A map has no tile address, so it is not cached; `wms_max_px` caps each side. Errors are the API's JSON, not a ServiceExceptionReport.

### Metadata and status

`web/meta.py`. `/metadata` is the one document a client reads first, the same for every caller:

- `version`, `area`, `date` (the extract's), `bounds` (WGS 84, from `import_meta.bbox_3857`), `attribution` (OpenStreetMap's, and Copernicus's where the schema has contours);
- `themes`: `{id, palette, detail}`, `id` the URL name;
- `grids`: `{id, crs, minzoom, maxzoom}`;
- `categories`: the generated tree, `{id, names: {<lang>: name}, icon, subcategories}`, names in every language of the `languages` option, without the search terms;
- `services`: links `{rel, href, templated?, method?, formats?}` -- `tiles`, `wmts-tiles`, `wmts`, `search`, `search-count`, `icon`, `legend`, `status` -- absolute, with RFC 6570 placeholders (`{theme}`, `{z}`, `{format}`) where `templated` is true. Tile links need `?key=` added.

Field names follow TileJSON where it has one (`bounds`, `minzoom`, `maxzoom`, `attribution`). `/status` takes a key of any scope and reports the build, the served schema, whether keys are configured, the import (`import_meta`'s extract, replication position, time and row counts) and each theme's generation, the Map pool's reload counter that tile URLs carry as `?v=`. Both answers are held for 30 s.

### Authentication

`web/auth.py`. Keys are records in the deployment's `options.yaml`: `{key, scopes: [search, tiles], referrers, rate}`. Two carriers, in order: `Authorization: Bearer <key>` (web clients) and `?key=<key>` (the only form an `<img>`, a tile template, QGIS or a WMTS client can send). No key or a wrong one is 401, a key without the scope or from a referrer not on its list 403, over its rate (per minute, per process) 429. Keys are compared with `secrets.compare_digest` over UTF-8 bytes. A referrer pattern is matched against `Origin` and `Referer`, with and without a trailing slash. No keys configured means open, with a warning at start and `"auth": "open"` on `/status`.

`key` is stripped from every log line: the app writes its own access log, uvicorn's is off (`--no-access-log`), and Caddy filters both its access and its error log.

### Startup

The lifespan resolves the served schema, compiles its styles, loads the Map pools for every served theme and grid, and warms the model YAML the search reads lazily. None of it is fatal: a server that cannot load still answers `/health`, `/metadata` and `/status`, and `/status` says why.

### Languages

`lib/i18n.py`. The texts a person reads are in `lib/messages.yaml`, one entry per message id with a text per language. A request picks its language with `?lang=`, one of the `languages` option that the catalogue covers; without one, or with one not served, it gets the first. The language is in the URL, not taken from `Accept-Language`, so that each language of a page is its own URL: a link keeps its language and a cache needs no `Vary`. Nothing a client parses is translated -- JSON keys, mode, parameter, theme and grid names, URLs. The landing page and the devtools are translated; the API's messages are not yet. The devtools' scripts get their texts (`devtools.js.*`) rendered into the page as a `<meta>`, like the formats, and carry `lang` in the URL state and in the search requests, so the category names follow the page.

### Devtools

`web/devtools/`, mounted only with the `devtools` option. A viewer, no editing: tiles in all three request forms and both grids, a debug grid, the legend of the theme on the map, every search mode with its interpretation, "what's here" by click, the server status. The key is typed into the page and kept in the viewer's `localStorage`, never rendered into it. State is in the URL, so a view is a link. With `devtools_watch`, a change under `styles/` recompiles the styles and clears the cache, and the page redraws.

## Configuration

Three layers (`lib/config.py`):

1. `config/options.yaml` -- every option with its default; the complete list.
2. `/config/options.yaml` -- the deployment. A key that is no option is refused, so a typo cannot silently fall back to a default.
3. `GEOSERVICES_<OPTION>` environment variables; each option path has exactly one variable name.

The deployment's configuration is a directory at the repository root, mounted into the stack: `config.local/` for the dev stack (tracked, dev password only), `config/` in production (git-ignored, copied to the server by `deploy.sh`), `config.example/` the template. Each holds `options.yaml`, `postgres.env`, `postgresql.conf`, `pg_hba.conf`, `pgbouncer.ini` and `Caddyfile`, and each service mounts only its own files.

The database credentials are in `postgres.env` only, given to postgres, pgbouncer and the app by compose. `lib/config.py` exports them with `db.host`/`db.port` to libpq's environment, so psycopg and Mapnik connect without parameters, and no credential is in the repository, the image, a compose file or the compiled XML.

## Deployment

The production stack (`docker-compose.yml`): postgres (PostGIS 17-3.5), pgbouncer, the app, Caddy. Postgres and pgbouncer are on an internal network Caddy is not on, because pgbouncer trusts its clients. No database port is published. Caddy terminates TLS and proxies to the app.

- `scripts/deploy.sh <ssh-host>` checks `config/`, copies the build context to the server, builds the image there (no registry, the server's own architecture) and copies `docker-compose.yml`, `manage.sh`, `setup.sh` and `config/`. It does not touch the running stack.
- Every service logs to the host's syslog, tagged with its container name (`logging:` in `docker-compose.yml`); Docker's own copy is capped at 1 MB per container. `scripts/setup.sh`, run once on the server as root, adds an rsyslog rule that writes each service's lines to `data/log/<service>.log` as `date | message`, and a logrotate rule. Without it the lines go to `/var/log/syslog`.
- `manage.sh reload` recreates the app: new image, new `options.yaml`, newest import. `manage.sh restart` restarts the whole stack, for the other config files. Both return once the containers are started; the app then compiles the styles and loads its Map pool.
- `manage.sh import <area>` starts an import detached in the app container; `manage.sh update <area>` imports in the foreground and reloads on success, for cron.
- `scripts/publish.sh` builds for `linux/amd64` and pushes to Docker Hub; no deploy needs it.

The version is `lib/version.py` `__version__`; the build id (the commit) is passed as a build argument and reported by `/status`.

The dev stack is `docker-compose.local.yml` (postgres on loopback 7778, pgbouncer, the app with `app/` bind-mounted and `--reload`); the test stack `docker-compose.test.yml`.

## Testing and measuring

- `scripts/test.sh` runs the suite and ruff in the test stack. Tests that need Postgres skip when it is not up; tests that read real rows skip unless `li` is imported. A test's docstring says what it caught; most of them pin a failure that produces no error.
- `tools/profile_render.py` renders a fixed pseudo-random tile set per theme, zoom and grid over HTTP, then renders one tile per zoom layer by layer with `EXPLAIN ANALYZE` of the query of each layer Mapnik queries at that scale. It keeps only tiles that hold a building: open-sea and empty tiles render in milliseconds and pull every median down.
- `tools/profile_search.py` sends a fixed query set for Schleswig-Holstein, cold and warm, and reports at which rank the expected result appears; typos and fragments go to the phrase mode.
- `tools/measure_reprojection.py` renders the same ground natively and reprojected.

Both profilers are standalone (stdlib, `mapnik`, `psycopg2`; no `app.*` imports) and document their invocation in their docstrings. Baselines go into `profiles/`, run on `de_sh` with every theme and grid served and the tile cache on: `render_<area>_<yyyymmdd>_<grid>.md`, one per grid, and `search_<area>_<yyyymmdd>.md`.

`de_sh` is the test area: small enough that an import and a full profile take minutes, with everything the design has to get right -- two coasts and tidal flats, a national border, a city state, rural land use, and two real cities. `li` is the development area (an import in under a minute).
