# Search profile -- 2026-09-30 12:20 UTC

- server http://127.0.0.1:8003, 28 queries, 3 requests each
- client darwin arm64 (dev stack, Docker Desktop on macOS)
- default box (lon/lat): 8.3 53.4 -- 11.3 55.0; "view" queries carry a bbox of their own (intersects), "all" queries no spatial filter, "point" queries use the point mode

`cold` is the first request, `warm` the median of the rest (every request nudges `near` by a few millionths of a degree, so a response cache never answers); `count` is `/search/count` for the same body. `rank` is the position of the first result whose name or street contains `expect` (1 = top, 0 = not on the page, - = nothing expected). `total` is the server's total for the query.

## name

| id | query | box | status | cold ms | warm ms | count ms | total | rank | top result |
|---|---|---|---|---|---|---|---|---|---|
| city | Kiel | all | 200 | 169 | 6 | 7 | 3 | 1 | Kiel |
| city_lowercase | lübeck | all | 200 | 27 | 8 | 4 | 4 | 1 | Lübeck |
| landmark | Holstentor | all | 200 | 9 | 5 | 4 | 4 | 1 | Holstentor |
| landmark_view | Rathaus | view | 200 | 19 | 8 | 7 | 2 | 1 | Rathaus |
| university | Christian-Albrechts-Universität zu Kiel | all | 200 | 4 | 5 | 4 | 1 | 1 | Christian-Albrechts-Universität zu Kiel |
| station | Hauptbahnhof | view | 200 | 10 | 7 | 5 | 12 | 1 | Hauptbahnhof |
| street_name | Holtenauer Straße | all | 200 | 5 | 5 | 3 | 2 | 1 | Holtenauer Straße |
| street_abbrev | Holtenauer Str. | all | 200 | 5 | 5 | 4 | 2 | 1 | Holtenauer Straße |
| two_words | Kieler Förde | all | 200 | 5 | 5 | 4 | 4 | 1 | Kieler Förde |
| nonsense | xqzvw plorp | all | 200 | 6 | 4 | 4 | 0 | - |  |

## address

| id | query | box | status | cold ms | warm ms | count ms | total | rank | top result |
|---|---|---|---|---|---|---|---|---|---|
| address_full | Holtenauer Straße 100 Kiel | all | 200 | 16 | 5 | 5 | 3 | 1 | Hundert | Holtenauer Straße 100 |
| address_short | Breite Straße 1 Lübeck | all | 200 | 8 | 5 | 4 | 2 | 1 | Peter Pane | Breite Straße 1-5 | Lübeck |
| address_abbrev | Holtenauer Str. 100 | all | 200 | 5 | 5 | 4 | 3 | 1 | Hundert | Holtenauer Straße 100 |
| address_postcode | Sophienblatt 25 24114 | all | 200 | 7 | 5 | 4 | 7 | 1 | Kiel Hauptbahnhof | Sophienblatt 25-27 | Kiel |
| address_many | Breite Straße 1 | all | 200 | 7 | 4 | 4 | 5 | 1 | Breite Straße 1 | Hohenlockstedt |
| address_view | Bahnhofstraße 1 | view | 200 | 15 | 5 | 4 | 4 | 1 | Bahnhofstraße 1 | Kiel |

## phrase

| id | query | box | status | cold ms | warm ms | count ms | total | rank | top result |
|---|---|---|---|---|---|---|---|---|---|
| phrase_cat_place | Restaurant Kiel | all | 200 | 42 | 16 | 17 | 196 | - | Mensa |
| phrase_cat_name | Restaurant Maxim | all | 200 | 37 | 15 | 16 | 1 | 1 | Maximilian | Schubystraße 47 | Schleswig |
| phrase_cat_street | Bäckerei Holtenauer Straße | all | 200 | 196 | 142 | 142 | 18 | 1 | Rönnau | Holtenauer Straße 36 | Kiel |
| phrase_cat_only | Apotheke | view | 200 | 19 | 14 | 13 | 71 | 1 | Adler-Apotheke | Jungfernstieg 37 | Kiel |
| phrase_address | Holtenauer Straße 100, 24105 Kiel | all | 200 | 12 | 9 | 11 | 2 | 1 | Haveli | Holtenauer Straße 100 | Kiel |
| phrase_address_city_first | Kiel Holtenauer Straße 100 | all | 200 | 12 | 11 | 10 | 3 | 1 | Hundert | Holtenauer Straße 100 |
| phrase_name_place | Universität Kiel | all | 200 | 28 | 29 | 29 | 6 | 1 | Universitätskirche |
| phrase_typo | Lübek | all | 200 | 5 | 5 | 5 | 0 | 0 |  |
| phrase_prefix | holsten | all | 200 | 6 | 5 | 5 | 0 | 0 |  |
| phrase_partial | flensb | all | 200 | 6 | 5 | 5 | 0 | 0 |  |

## point

| id | query | box | status | cold ms | warm ms | count ms | total | rank | top result |
|---|---|---|---|---|---|---|---|---|---|
| point_kiel_hbf | 10.1319,54.3151 | point | 200 | 18 | 15 | 11 | 15 | - | Ditsch | Sophienblatt 25-27 |
| point_luebeck | 10.6866,53.8663 | point | 200 | 17 | 12 | 11 | 27 | - | Hüxstraße 18 | Lübeck |

## Summary

- warm ms over all successful queries: min 4 / median 5 / max 142
- expected result at rank 1: 21 of 24; on the first page: 21 of 24

<details><summary>Top 3 per query</summary>

- **city** (Kiel): Kiel ; Kiel ; Kiel
- **city_lowercase** (lübeck): Lübeck ; Luebeck ; Lübeck
- **landmark** (Holstentor): Holstentor ; Holstentor ; Holstentor
- **landmark_view** (Rathaus): Rathaus ; Rathaus
- **university** (Christian-Albrechts-Universität zu Kiel): Christian-Albrechts-Universität zu Kiel
- **station** (Hauptbahnhof): Hauptbahnhof ; Hauptbahnhof ; Hauptbahnhof
- **street_name** (Holtenauer Straße): Holtenauer Straße ; Holtenauer Straße
- **street_abbrev** (Holtenauer Str.): Holtenauer Straße ; Holtenauer Straße
- **two_words** (Kieler Förde): Kieler Förde ; Kieler Förde ; Kieler Förde
- **nonsense** (xqzvw plorp): no results
- **address_full** (Holtenauer Straße 100 Kiel): Hundert | Holtenauer Straße 100 ; Haveli | Holtenauer Straße 100 | Kiel ; Holtenauer Straße 100 | Kiel
- **address_short** (Breite Straße 1 Lübeck): Peter Pane | Breite Straße 1-5 | Lübeck ; Breite Straße 1-5 | Lübeck
- **address_abbrev** (Holtenauer Str. 100): Hundert | Holtenauer Straße 100 ; Haveli | Holtenauer Straße 100 | Kiel ; Holtenauer Straße 100 | Kiel
- **address_postcode** (Sophienblatt 25 24114): Kiel Hauptbahnhof | Sophienblatt 25-27 | Kiel ; REWE City | Sophienblatt 25-27 | Kiel ; REWE City | Sophienblatt 25-27 | Kiel
- **address_many** (Breite Straße 1): Breite Straße 1 | Hohenlockstedt ; Breite Straße 1 | Stapel ; Breite Straße 1 | Wöhrden
- **address_view** (Bahnhofstraße 1): Bahnhofstraße 1 | Kiel ; Bahnhofstraße 1 | Melsdorf ; Bahnhofstraße 1 | Neuwittenbek
- **phrase_cat_place** (Restaurant Kiel): Mensa ; Glückspilz | Hamburger Chaussee 352 | Kiel ; Meraki | Hamburger Chaussee 349 | Kiel
- **phrase_cat_name** (Restaurant Maxim): Maximilian | Schubystraße 47 | Schleswig
- **phrase_cat_street** (Bäckerei Holtenauer Straße): Rönnau | Holtenauer Straße 36 | Kiel ; Bäcker Andresen | Holtenauer Straße 78 | Kiel ; Steiskal | Holtenauer Straße 120
- **phrase_cat_only** (Apotheke): Adler-Apotheke | Jungfernstieg 37 | Kiel ; Neptun-Apotheke ; Medica-Apotheke | Prüner Gang 15 | Kiel
- **phrase_address** (Holtenauer Straße 100, 24105 Kiel): Haveli | Holtenauer Straße 100 | Kiel ; Holtenauer Straße 100 | Kiel
- **phrase_address_city_first** (Kiel Holtenauer Straße 100): Hundert | Holtenauer Straße 100 ; Haveli | Holtenauer Straße 100 | Kiel ; Holtenauer Straße 100 | Kiel
- **phrase_name_place** (Universität Kiel): Universitätskirche ; Universitätsbibliothek | Leibnizstraße 9 ; Universitätsklinikum Schleswig-Holstein - Campus Kiel | Arnold-Heller-Straße 3 - 6 | Kiel
- **phrase_typo** (Lübek): no results
- **phrase_prefix** (holsten): no results
- **phrase_partial** (flensb): no results
- **point_kiel_hbf** (10.1319,54.3151): Ditsch | Sophienblatt 25-27 ; Ditsch | Sophienblatt 25-27 ; Ditsch
- **point_luebeck** (10.6866,53.8663): Hüxstraße 18 | Lübeck ; Hüxstraße ; Schuback

</details>
