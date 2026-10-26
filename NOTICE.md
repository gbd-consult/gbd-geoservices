# Acknowledgements

gbd-geoservices was co-authored with Claude (Anthropic), an AI model, working in Claude Code.

It is built on the work of others. This file lists the data, assets and software it uses, with their copyright holders and licences.

## Map data

- **OpenStreetMap** -- all map and search data. © OpenStreetMap contributors, Open Database License (ODbL) 1.0: <https://www.openstreetmap.org/copyright>. Every map made from these tiles, and every use of the search results, must credit "© OpenStreetMap contributors" and make clear the data is available under the ODbL.
- **Geofabrik** -- the regional OpenStreetMap extracts the import reads, processed by Geofabrik GmbH and published at <https://download.geofabrik.de/>. The extracts are OpenStreetMap data under the ODbL 1.0.
- **OSM water polygons** -- the sea areas, from <https://osmdata.openstreetmap.de/>, a site run by FOSSGIS e.V. They are assembled from the OpenStreetMap coastline with OSMCoastline. Derived from OpenStreetMap data, © OpenStreetMap contributors, ODbL.
- **Copernicus GLO-30 digital elevation model** -- the contour lines of `topographic` and `max`, drawn by `manage.py init-elevation`. © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved. Free to use with this credit.

## Model and styles

- **iD tagging schema** (`@openstreetmap/id-tagging-schema`, version in `app/model/generated/`) -- the presets, category names, translations and search terms the category tree is generated from. © iD Contributors, ISC License: <https://github.com/openstreetmap/id-tagging-schema>.
- **OpenMapTiles** (version in `app/model/generated/`) -- the grouping of OSM tags into render classes. © MapTiler.com & OpenMapTiles contributors; code under the BSD 3-Clause License, the cartography and visual design of the schema under CC-BY 4.0: <https://github.com/openmaptiles/openmaptiles>. Maps derived from the OpenMapTiles schema must visibly credit "OpenMapTiles" with a link to <https://openmaptiles.org/>.
- **OpenStreetMap Carto** -- the colours the map palettes started from. Created by Andy Allan and contributors, based on original cartography by Steve Chilton and others; CC0 1.0: <https://github.com/gravitystorm/openstreetmap-carto>.
- **Maki icons** -- the POI icons, vendored in `app/styles/icons/maki/`. By Mapbox, CC0 1.0: <https://github.com/mapbox/maki>.
- **Noto Sans** -- the map font, installed in the image from Debian's `fonts-noto-core`. © Google Inc., Google LLC; SIL Open Font License 1.1: <https://notofonts.github.io/>.

## Software

The service runs on:

- Mapnik and its Python bindings -- LGPL 2.1 or later
- PostgreSQL -- PostgreSQL Licence; PostGIS -- GPL 2 or later
- pgbouncer -- ISC; Caddy -- Apache 2.0
- pyosmium -- BSD 2-Clause; libosmium -- Boost Software License 1.0
- Shapely, NumPy -- BSD 3-Clause; pyshp -- MIT
- psycopg 3 -- LGPL 3.0; psycopg2 (profiler only) -- LGPL with exceptions
- FastAPI, PyYAML -- MIT; Starlette, uvicorn, Jinja2 -- BSD 3-Clause

The development viewer loads Leaflet (BSD 2-Clause), Leaflet.draw (MIT), Proj4js (MIT) and Proj4Leaflet (BSD 2-Clause).
