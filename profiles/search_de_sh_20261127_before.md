# Search profile -- 2026-11-27 16:40 UTC

- server http://127.0.0.1:8099, 28 queries, 3 requests each
- client linux x86_64
- default box (lon/lat): 8.3 53.4 -- 11.3 55.0; "view" queries carry a bbox of their own (intersects), "all" queries no spatial filter, "point" queries use the point mode

`cold` is the first request, `warm` the median of the rest (every request nudges `near` by a few millionths of a degree, so a response cache never answers); `count` is `/search/count` for the same body. `rank` is the position of the first result whose name or street contains `expect` (1 = top, 0 = not on the page, - = nothing expected). `total` is the server's total for the query. `ok`: rank 1-5 and warm at most 200 ms.

## name

| id | query | box | status | cold ms | warm ms | count ms | total | rank | ok | top result |
|---|---|---|---|---|---|---|---|---|---|---|
| city | Kiel | all | 200 | 67 | 43 | 20 | 3 | 1 | yes | Kiel |
| city_lowercase | lübeck | all | 200 | 46 | 45 | 18 | 6 | 1 | yes | Lübeck |
| landmark | Holstentor | all | 200 | 130 | 44 | 18 | 4 | 1 | yes | Holstentor |
| landmark_view | Rathaus | view | 200 | 39 | 44 | 29 | 2 | 1 | yes | Rathaus |
| university | Christian-Albrechts-Universität zu Kiel | all | 200 | 132 | 48 | 18 | 1 | 1 | yes | Christian-Albrechts-Universität zu Kiel |
| station | Hauptbahnhof | view | 200 | 52 | 44 | 29 | 12 | 1 | yes | Hauptbahnhof |
| street_name | Holtenauer Straße | all | 200 | 40 | 40 | 19 | 2 | 1 | yes | Holtenauer Straße |
| street_abbrev | Holtenauer Str. | all | 200 | 43 | 40 | 18 | 2 | 1 | yes | Holtenauer Straße |
| two_words | Kieler Förde | all | 200 | 41 | 41 | 18 | 4 | 1 | yes | Kieler Förde |
| nonsense | xqzvw plorp | all | 200 | 158 | 46 | 23 | 7 | - | - | Plirup |

## address

| id | query | box | status | cold ms | warm ms | count ms | total | rank | ok | top result |
|---|---|---|---|---|---|---|---|---|---|---|
| address_full | Holtenauer Straße 100 Kiel | all | 200 | 115 | 42 | 21 | 3 | 1 | yes | Hundert | Holtenauer Straße 100 |
| address_short | Breite Straße 1 Lübeck | all | 200 | 112 | 46 | 18 | 2 | 1 | yes | Peter Pane | Breite Straße 1-5 | Lübeck |
| address_abbrev | Holtenauer Str. 100 | all | 200 | 39 | 41 | 17 | 3 | 1 | yes | Hundert | Holtenauer Straße 100 |
| address_postcode | Sophienblatt 25 24114 | all | 200 | 113 | 48 | 18 | 7 | 1 | yes | Kiel Hauptbahnhof | Sophienblatt 25-27 | Kiel |
| address_many | Breite Straße 1 | all | 200 | 110 | 52 | 17 | 5 | 1 | yes | Breite Straße 1 | Hohenlockstedt |
| address_view | Bahnhofstraße 1 | view | 200 | 166 | 44 | 29 | 4 | 1 | yes | Bahnhofstraße 1 | Kiel |

## phrase

| id | query | box | status | cold ms | warm ms | count ms | total | rank | ok | top result |
|---|---|---|---|---|---|---|---|---|---|---|
| phrase_cat_place | Restaurant Kiel | all | 200 | 188 | 66 | 62 | 194 | - | - | Mensa |
| phrase_cat_name | Restaurant Maxim | all | 200 | 159 | 62 | 54 | 1 | 1 | yes | Maximilian | Schubystraße 47 | Schleswig |
| phrase_cat_street | Bäckerei Holtenauer Straße | all | 200 | 337 | 184 | 181 | 19 | 1 | yes | Rönnau | Holtenauer Straße 36 | Kiel |
| phrase_cat_only | Apotheke | view | 200 | 149 | 51 | 49 | 71 | 1 | yes | Adler-Apotheke | Jungfernstieg 37 | Kiel |
| phrase_address | Holtenauer Straße 100, 24105 Kiel | all | 200 | 127 | 59 | 49 | 2 | 1 | yes | Haveli | Holtenauer Straße 100 | Kiel |
| phrase_address_city_first | Kiel Holtenauer Straße 100 | all | 200 | 59 | 53 | 55 | 3 | 1 | yes | Hundert | Holtenauer Straße 100 |
| phrase_name_place | Universität Kiel | all | 200 | 195 | 61 | 63 | 6 | 1 | yes | Universitätskirche |
| phrase_typo | Lübek | all | 200 | 78 | 63 | 66 | 38 | 1 | yes | Lübeck |
| phrase_prefix | holsten | all | 200 | 216 | 90 | 103 | 200 | 1 | yes | Holstendamm |
| phrase_partial | flensb | all | 200 | 188 | 79 | 75 | 200 | 1 | yes | Flensburg |

## point

| id | query | box | status | cold ms | warm ms | count ms | total | rank | ok | top result |
|---|---|---|---|---|---|---|---|---|---|---|
| point_kiel_hbf | 10.1319,54.3151 | point | 200 | 50 | 54 | 51 | 14 | - | - | Ditsch | Sophienblatt 25-27 |
| point_luebeck | 10.6866,53.8663 | point | 200 | 149 | 60 | 62 | 27 | - | - | Hüxstraße 18 | Lübeck |

## Summary

- warm ms over all successful queries: min 40 / median 48 / max 184
- expected result at rank 1: 24 of 24; on the first page: 24 of 24
- target (rank 1-5, warm at most 200 ms) met: 24 of 24; rank alone: 24 of 24

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
- **nonsense** (xqzvw plorp): Plirup ; Plirup ; Bullerbü
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
- **phrase_name_place** (Universität Kiel): Universitätskirche ; Universitätsklinikum Schleswig-Holstein - Campus Kiel | Arnold-Heller-Straße 3 - 6 | Kiel ; Universitätsbibliothek | Leibnizstraße 9
- **phrase_typo** (Lübek): Lübeck ; Luebeck ; Lehbek
- **phrase_prefix** (holsten): Holstendamm ; Holsteneck ; Holstentor
- **phrase_partial** (flensb): Flensburg ; Flensburg ; Flensburg
- **point_kiel_hbf** (10.1319,54.3151): Ditsch | Sophienblatt 25-27 ; Ditsch | Sophienblatt 25-27 ; Blumen am Gleis 2
- **point_luebeck** (10.6866,53.8663): Hüxstraße 18 | Lübeck ; Hüxstraße ; Schuback

</details>
