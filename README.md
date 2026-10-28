# GBD GeoServices

A self-hosted map service built from OpenStreetMap data: raster map tiles and place search for a region, served over HTTP.

- **Map tiles** as XYZ and WMTS, in Web Mercator and in UTM zones 32N and 33N (EPSG:25832, EPSG:25833), and **maps** as WMS in these and EPSG:4326, in eight color schemes (`default`, `light`, `dark`, `hico`, `grayscale`, `sepia`, `atkis` (SK25 colours, for `topographic`), `flora` (for `vegetation`)) and six levels of detail (`min`, `nav`, `std`, `max`, `topographic`, `vegetation`).
- **Search** by name, by address, by free text ("restaurant Kiel", "Holtenauer Straße 100, Kiel"), and by point ("what is here").
- **One import** of a Geofabrik extract builds everything, including the sea, which OSM itself does not contain as areas.
- **Configurable OSM mapping**: which OSM tags become which map class and which search category, which categories get an icon, and from which zoom they appear. The category tree and its search terms are derived from the iD editor's tagging schema.
- **API keys** with scopes (`tiles`, `search`), referrer allowlists and rate limits.

The map styles are this project's own, built on open sources: the palettes started from the colours of OpenStreetMap Carto (CC0), the grouping of OSM tags into render classes follows the OpenMapTiles schema (CC-BY 4.0), and the POI icons are Maki (CC0).

Operation within your own network, for example on an intranet, is available on request.

How it works inside is in `DESIGN.md`; open issues are in `TODO.md`; data sources and licences are in `NOTICE.md`.

## Requirements

A Linux server with Docker and the Compose plugin, `rsync`, and SSH access from the machine you deploy from. Memory and disk depend on the area:

| area | extract | import |
|---|---|---|
| `li` (Liechtenstein) | 3 MB | under a minute |
| `de_sh` (Schleswig-Holstein) | 160 MB | 5-10 minutes |
| `de` (Germany) | 4 GB | ~6 hours; ~53 GB per import in the database, and two imports are kept |

The stack is PostgreSQL 17 with PostGIS 3.5, pgbouncer, the app (Python, Mapnik) and Caddy for TLS.

## Setup

1. On the deploying machine, in this repository, create the deployment's configuration from the template:

   ```sh
   cp -r config.example config
   chmod 600 config/options.yaml config/postgres.env
   ```

   `config/` is git-ignored: it holds the database password. Fill in:

   - `config/options.yaml` -- `host` (the public host name), and `serve_area` (which area this server serves).
   - `config/postgres.env` -- a strong `POSTGRES_PASSWORD`.
   - `config/Caddyfile` -- the same host name, and an e-mail address for the TLS certificate.
   - `config/postgresql.conf` -- memory settings (`shared_buffers` and the like) for the host.

   Every `CHANGEME` has to go. `config.example/README.md` describes each file.

2. On the server, once: `sudo mkdir -p /opt/gbd-geoservices/v0.3 && sudo chown $USER /opt/gbd-geoservices/v0.3`.

3. Deploy, with an SSH host name from `~/.ssh/config`:

   ```sh
   app/scripts/deploy.sh <ssh-host>
   ```

   This checks `config/`, builds the image on the server, and copies `docker-compose.yml`, `manage.sh`, `setup.sh` and `config/` to `/opt/gbd-geoservices/v0.3/`. It does not start or restart anything.

4. On the server, in `/opt/gbd-geoservices/v0.3`, once: `sudo ./setup.sh`. It has the host's rsyslog write the services' logs to `data/log/` and rotate them, and adds the cron job that updates the data. Without it the stack runs all the same, logs to `/var/log/syslog` and is not updated. Run it again when a deploy brings a changed `setup.sh`.

5. On the server, in `/opt/gbd-geoservices/v0.3`, start the stack and import the area:

   ```sh
   ./manage.sh restart
   ./manage.sh update <area>
   ```

   Until the first import is complete, tiles and search answer 503.

## Operating

All commands run on the server, in `/opt/gbd-geoservices/v0.3`.

| command | |
|---|---|
| `./manage.sh reload` | recreate the app: takes up a new image, a changed `options.yaml`, and the newest import |
| `./manage.sh restart` | stop and start the whole stack: for changes to `postgres.env`, `postgresql.conf`, `pg_hba.conf`, `pgbouncer.ini` or the `Caddyfile` |
| `./manage.sh import <area>` | import an area in the background; follow it with `tail -f data/import.log` |
| `./manage.sh update <area>` | import in the foreground; if it succeeded, reload, empty the tile cache and pre-cache again -- the form for cron |
| `./manage.sh pre-cache [--fast]` | render the low zoom levels of every theme ahead of time |
| `./manage.sh drop-cache` | empty the tile cache |
| `./manage.sh compile-styles` | recompile the map styles (the app also does this at every start) |
| `./manage.sh init-elevation` | download the missing elevation tiles (`elevation_tiles`) and draw the contour lines once; the next import of an area takes its share |

**Updating the data.** An import writes a new copy of the data beside the one being served; the served one is untouched until the next `reload`. `setup.sh` installs a cron job (`/etc/cron.d/gbd-geoservices-v03`) that runs `./manage.sh update` for `serve_area` on Monday, Wednesday and Friday at 02:00 and appends to `data/cron.log`.

The two newest complete imports of an area are kept. Only one import runs at a time. At its end, an import logs the counts that moved against the previous one (`against <schema>: ...` in `data/import.log`); a class that vanished there is worth a look before the reload. `update` empties the tile cache and pre-caches again; after an `import` and `reload` by hand the cache is kept until `drop-cache` (and `pre-cache`).

**Contour lines.** The `topographic` and `max` levels of detail draw contour lines from the Copernicus GLO-30 elevation model. Run `./manage.sh init-elevation` once: it fetches the tiles of `elevation_tiles` (Germany) that are not yet under `data/downloads/rasters_COP30/` and draws the lines (own GeoTIFFs: put them there, or set `elevation_sources`, and run `manage.py init-elevation` without `--download`) -- for all of Germany it runs for a long while and needs several GB of disk for the intermediate raster -- and import the areas again. An area imported before has no contour lines.

**Rolling back.** Set `force_schema` in `config/options.yaml` to the previous import's schema (its name is `<area>_<date>_<time>`; `GET /status` shows the current one), deploy, and `./manage.sh reload`. Remove the option again to return to the newest import.

**Updating the software.** `app/scripts/deploy.sh <ssh-host>` from the new checkout, then `./manage.sh reload` on the server. The app takes a few minutes to start: it compiles the styles and loads its renderers (`docker compose logs -f app`).

**Logs.** `data/log/app.log`, `postgres.log`, `pgbouncer.log`, `caddy.log`, one line each as `date | message`, rotated daily and kept for a week. `docker compose logs` shows only the last megabyte of each service.

**Request log and load figures.** Every API request (tiles, WMS, search) is written to the table `service.request_log` with its time, key, status, duration, tile cache hit or miss, client IP and, for a search, its search terms. Once a minute the host's CPU, RAM and disk are sampled. The cron job from `setup.sh` runs `./manage.sh stats-daily` every night: it counts the finished days into `service.daily_stats` (no IPs, no search terms; kept) and drops the request log older than 7 days, IP addresses and search terms with it. `./manage.sh stats-export 2026-10 > load-2026-10.csv` writes one line per day: requests by kind, errors, cache hit rate, 95th percentile durations, distinct IPs, CPU, RAM and disk; the totals with the cost per 1000 requests (option `monthly_cost_eur`) go to the terminal. `request_log: false` turns the log off.

**Status.** `GET /health` answers when the app is up; `GET /status` (with any valid key) shows the version, the build, the served import, and whether keys are registered (`"auth": "open"` means no keys and no protection).

**Database shell.** `docker compose exec postgres psql -U geoservices geoservices`.

**Changing the database password.** The password in `postgres.env` is applied only when the database is first created. Change the role as well: `docker compose exec postgres psql -U geoservices -c "ALTER ROLE geoservices PASSWORD '...'"`, then `./manage.sh restart`.

## Configuration

`config/options.yaml` sets only what differs from the defaults in `app/config/options.yaml`, which lists every option with its meaning. A key that is not an option is refused, so a typo stops the app instead of being ignored. The most used:

| option | |
|---|---|
| `serve_area` | the area this server serves |
| `force_schema` | serve this import instead of the newest (rollback) |
| `serve_palettes`, `serve_details` | which color schemes and levels of detail are served |
| `serve_grids` | which tile grids are served (`GoogleMapsCompatible`, `DE_EPSG_25832_ADV`, `DE_EPSG_25833_ADV`) |
| `precache` | per grid, the deepest level `pre-cache` renders |
| `ondemand_cache_max_mb` | size limit of the cache for tiles rendered on request |
| `map_pool_size` | concurrent renders per theme |
| `wms_max_px` | the largest WMS map, per side |
| `monthly_cost_eur` | the server's monthly cost, for `stats-export` |
| `request_log` | write the request log and host samples (default on) |
| `areas` | the importable areas: name -> Geofabrik path |
| `operator` | `name` and `url` of who runs the service, named on the landing page |
| `source_url` | the source code the landing page links to (AGPL-3.0); a modified version sets its own |
| `devtools` | the viewer at `/devtools/`; its data needs a key with the `devtools` scope |

Any option can also be set with an environment variable `GEOSERVICES_<OPTION>`.

### Legal texts

The landing page links the imprint, the privacy policy and the terms of use, from HTML files in `config/legal/`: `impressum.html`, `datenschutz.html`, `nutzungsbedingungen.html`, served at `/impressum`, `/datenschutz` and `/nutzungsbedingungen`. Each file is the page's body (headings, paragraphs, no `<html>` or `<head>`). A missing file has no link and its page is a 404. `deploy.sh` copies them; they take effect without a reload.

### API keys

API keys are in the database, stored only as their SHA-256; a key cannot be read back. Keys are generated only by `vaultwarden-send.sh`, which hands each one to its customer as a Vaultwarden Send: `key-add` runs it, registers the key and prints the Send link -- never the key. It needs the Bitwarden CLI `bw` on the server and `VAULTWARDEN_SERVER` (for a run without prompts also `BW_CLIENTID`, `BW_CLIENTSECRET`, `BW_PASSWORD`; see `./vaultwarden-send.sh --help`). On the server:

```sh
./manage.sh key-add stadt-kiel --customer "Stadt Kiel" --scopes tiles search
./manage.sh key-add demo --scopes tiles --referrers 'https://maps.example.org/*' --rate 600 --trial
echo "$KEY" | ./manage.sh key-register old-client   # a key a client already has
./manage.sh key-list
./manage.sh key-disable demo                               # and key-enable
./manage.sh usage-export 2026-10 > usage-2026-10.csv
```

- `--scopes`: `tiles`, `search` and/or `devtools`; none means `tiles` and `search`. `devtools` opens the viewer's data and is given only by name, to our own keys. `--referrers`: only from these pages (matched against `Origin` and `Referer`). `--rate`: requests per minute.
- `--trial` makes a key valid for 30 days, `--expires YYYY-MM-DD` until that day. An expired or disabled key is refused with 403. Changes take effect within 30 seconds, without a reload.
- Every request with a key is counted per month: successful tile requests (XYZ, WMTS, WMS) and search requests apart, and every request answered with an error (status 400 or above, the key's own refusals included) as `errors`. A WMS map counts as one request, whatever its size up to `wms_max_px`. `usage-export` writes `key;customer;month;tiles;search;errors` for every key.

A client sends the key as `Authorization: Bearer <key>` or as `?key=<key>` (the only form tile URLs in map libraries, QGIS and other WMTS clients can use). Keys never appear in the logs. With no keys registered the server is open to everyone.

## Raster API

Map tiles need a key with the `tiles` scope. A theme is a color scheme (`default`, `light`, `dark`, `hico`, `grayscale`, `sepia`, `atkis`, `flora`) and a level of detail (`min`, `nav`, `std`, `max`, `topographic`, `vegetation`). In a URL it is `<color>_<detail>`, leaving out `default` and `std`: `std` (the default map), `max`, `dark`, `dark_min`. `default` and `std` are never spelled out, so `default_max` and `dark_std` are not names. `/metadata` lists the themes and grids a server serves.

| URL | |
|---|---|
| `GET /xyz/{theme}/{z}/{x}/{y}.{format}` | a tile in Web Mercator, the usual `{z}/{x}/{y}` scheme of web maps; `format` is `png` or `jpg` |
| `GET /wmts?SERVICE=WMTS&REQUEST=GetCapabilities&key=...` | the WMTS capabilities: add this URL to QGIS or any other WMTS client |
| `GET /wmts/{theme}/{grid}/{level}/{col}/{row}.{format}` | a tile in any served grid (`GoogleMapsCompatible`, `DE_EPSG_25832_ADV`, `DE_EPSG_25833_ADV`), as the capabilities advertise it |
| `GET /wmts?SERVICE=WMTS&REQUEST=GetTile&...` | the same tile in WMTS key-value form |
| `GET /wms?SERVICE=WMS&REQUEST=GetCapabilities&key=...` | the WMS capabilities (1.3.0): add this URL to QGIS or any other WMS client |
| `GET /wms?SERVICE=WMS&REQUEST=GetMap&...` | a map of any bbox and size in EPSG:3857, 4326, 25832 or 25833, one layer per request; rendered on every request, not cached |

Every map built from these tiles must show "© OpenStreetMap contributors".

## Search API

Search needs a key with the `search` scope. Both endpoints take the same JSON body.

| URL | |
|---|---|
| `POST /search` | one page of results, as GeoJSON |
| `POST /search/count` | `{"total": n}`: the number of results for the same body |
| `POST /search/fuzzy`, `POST /search/fuzzy/count` | the fuzzy name search alone, for a name-mode body with `text`; its total |

The `mode` field chooses how the request is read:

- **name** -- a name the client knows, matched exactly after normalisation (case, umlauts, "Str." for "Straße"); if nothing matches exactly, typos and fragments are matched (relevance 20). With `categories` and no `text`, all objects of those categories in the view.
- **address** -- street, house number and optionally postcode and city, as separate fields, each matched exactly.
- **phrase** -- free text: any mix of name, category, place, street and address ("restaurant Kiel", "Bäckerei Holtenauer Straße", "Holtenauer Straße 100, 24105 Kiel"). The response reports how the text was read.
- **point** -- what lies at a point: its nearest address, then objects nearby, nearest first, then the areas that contain it.

Request fields. `mode` is required, and so are `text` or `categories` in the name and phrase modes, `street` and `housenumber` in the address mode, and `near` in the point mode. A field outside its modes is refused with 422.

| name | type | modes | description |
|---|---|---|---|
| `mode` | string | all | `name`, `address`, `phrase` or `point` |
| `text` | string | name, phrase | the name, or the free text |
| `categories` | array of string | name, phrase, point | category ids; a category includes everything below it |
| `street` | string | address | street name |
| `housenumber` | string | address | house number with its suffix: `12a` is not `12` |
| `postcode` | string | address | optional |
| `city` | string | address | optional; matches the address's city or any place it lies in |
| `bbox` | [lon1, lat1, lon2, lat2] | name, address, phrase | the view, in WGS 84 |
| `area` | string | name, address, phrase | a WKT polygon in WGS 84, instead of `bbox` |
| `within` | boolean | name, address, phrase | `true`: only objects entirely inside the view; default `false`, touching it is enough |
| `near` | [lon, lat] | all | where distances are measured from; defaults to the centre of `bbox`. In the point mode, the point |
| `radius` | number | point | metres around `near`, up to 10 000; default 50 for points, 25 for lines |
| `address` | boolean | point | include the nearest address; default `true` |
| `sort` | string | name, address, phrase | `score` (default), `distance`, `name`, `address` |
| `similarity` | integer | name, phrase | 1 (very fuzzy) to 10 (near exact), default 7 |
| `relevance` | integer | name, address, phrase | 0-100: drop results that matched less literally; default 0 |
| `page` | integer | name, address, phrase | from 0 |
| `limit` | integer | all | results per page, 1-100, default 50 |
| `lang` | string | all | language of category names, `de` (default) or `en` |

Examples:

```json
{"mode": "name", "text": "Holstentor", "bbox": [10.5, 53.8, 10.8, 53.9]}
{"mode": "name", "categories": ["cat_poi_food_restaurant"], "bbox": [10.1, 54.3, 10.2, 54.4]}
{"mode": "address", "street": "Holtenauer Straße", "housenumber": "100", "city": "Kiel"}
{"mode": "phrase", "text": "restaurant Kiel"}
{"mode": "point", "near": [10.1395, 54.3233], "radius": 30}
```

Response fields:

| name | type | description |
|---|---|---|
| `page` | integer | the page returned |
| `limit` | integer | the page size |
| `count` | integer | results on this page |
| `total` | integer | results in all; in the phrase mode, of the capped candidate list |
| `has_more` | boolean | whether another page follows |
| `interpretation` | array | phrase mode only: every rule that ran, with its condition, its row count and the parts of the text it used |
| `results` | FeatureCollection | the results, as GeoJSON in WGS 84; each feature's `geometry` is what to highlight -- the point, the whole street, the outline |

Every feature has the same properties, `null` where one does not apply. Its `id` is a string, `o…` for an object and `a…` for an address.

| property | type | description |
|---|---|---|
| `name` | string | the name; `''` when the object has none |
| `category` | string | the object's category id |
| `category_name` | string | its name in `lang` |
| `categories` | array of {id, name} | the category and its ancestors, from the root down |
| `icon` | string | URL of the category's icon |
| `center` | [lon, lat] | a point on the object, for a marker or a label |
| `places` | array of {id, name, category, category_name} | the administrative areas the object lies in, largest first |
| `match_relevance` | integer | 0-100, how literally it matched: 100 an exact address, 99 an exact name or a point hit, 20 a name mode typo match, less for looser phrase readings |
| `match_score` | number | the ranking score within this request; not comparable across requests |
| `match_rule` | string | phrase mode: the rule that found it |
| `match_distance` | number | metres from `near` or the view's centre |
| `address_street`, `address_housenumber`, `address_postcode`, `address_city` | string | the address: the one matched, or the object's own |
| `osm_ids` | array of integer | the OSM ids behind the result (several for a street); relations are negative |
| `osm_tags` | object | the OSM tags |

## Metadata API

| URL | |
|---|---|
| `GET /metadata` | what a client needs to start: version, area, data date and bounds, themes, grids, the category tree with names and icons, and every service URL as a template. No key |
| `GET /icons/{category}.svg` | a category's icon. No key |
| `GET /legend/{theme}.png?lang=de` | a theme's legend as an image; WMTS clients such as QGIS find it in the capabilities on their own. No key |
| `GET /status` | for operators: build, the served import, whether keys are registered. Any valid key |
| `GET /health` | answers when the app is up. No key |
| `GET /` | the landing page, in German, or in English with `?lang=en`. No key |

## Development

```sh
docker compose -f docker-compose.local.yml up -d
docker compose -f docker-compose.local.yml exec app python tools/manage.py import li
```

The dev server is on http://localhost:8003, with a viewer for tiles and search at http://localhost:8003/devtools (open on the dev stack, which has no keys; with keys it needs one with the `devtools` scope). It is configured from `config.local/`. `sh app/scripts/test.sh` runs the tests. `DESIGN.md` is the developer documentation.

## License

GBD GeoServices is licensed under the GNU Affero General Public License, version 3 or (at your option) any later version (AGPL-3.0-or-later); the text is in `LICENSE`. Whoever runs a modified version as a network service must offer its users that version's source. The data, styles and software it builds on keep their own licences, listed in `NOTICE.md`.
