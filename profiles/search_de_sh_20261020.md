# Search profile -- 2026-10-20 15:56 UTC

- server http://127.0.0.1:8014, 34 queries, 5 requests each
- client linux x86_64 (linux dev box, de_sh_20261009_095021, after)
- default box (lon/lat): 8.3 53.4 -- 11.3 55.0; "view" queries carry a bbox of their own (intersects), "all" queries no spatial filter, "point" queries use the point mode

`cold` is the first request, `warm` the median of the rest (every request nudges `near` by a few millionths of a degree, so a response cache never answers); `count` is `/search/count` for the same body. `rank` is the position of the first result whose name or street contains `expect` (1 = top, 0 = not on the page, - = nothing expected). `total` is the server's total for the query.

## name

| id | query | box | status | cold ms | warm ms | count ms | total | rank | top result |
|---|---|---|---|---|---|---|---|---|---|
| city | Kiel | all | 200 | 19 | 9 | 8 | 3 | 1 | Kiel |
| city_lowercase | lübeck | all | 200 | 19 | 12 | 5 | 4 | 1 | Lübeck |
| landmark | Holstentor | all | 200 | 7 | 7 | 6 | 4 | 1 | Holstentor |
| landmark_view | Rathaus | view | 200 | 11 | 9 | 9 | 2 | 1 | Rathaus |
| university | Christian-Albrechts-Universität zu Kiel | all | 200 | 7 | 6 | 5 | 1 | 1 | Christian-Albrechts-Universität zu Kiel |
| station | Hauptbahnhof | view | 200 | 12 | 11 | 8 | 12 | 1 | Hauptbahnhof |
| street_name | Holtenauer Straße | all | 200 | 7 | 7 | 5 | 2 | 1 | Holtenauer Straße |
| street_abbrev | Holtenauer Str. | all | 200 | 7 | 8 | 6 | 2 | 1 | Holtenauer Straße |
| two_words | Kieler Förde | all | 200 | 9 | 7 | 5 | 4 | 1 | Kieler Förde |
| nonsense | xqzvw plorp | all | 200 | 22 | 13 | 10 | 7 | - | Plirup |
| name_typo | Lübek | all | 200 | 51 | 53 | 37 | 950 | 1 | Lübeck |
| name_typo_street | Hautpstraße | all | 200 | 272 | 168 | 142 | 4935 | 1 | Hauptstraße |
| name_prefix | holsten | all | 200 | 54 | 60 | 47 | 759 | 1 | Holsten MC | Langwedelerfeld 8 | Langwedel |
| name_partial | flensb | all | 200 | 34 | 33 | 25 | 540 | 1 | Flensburg |
| name_typo_city | Kiell | all | 200 | 171 | 66 | 49 | 1046 | 1 | Kiel |

## address

| id | query | box | status | cold ms | warm ms | count ms | total | rank | top result |
|---|---|---|---|---|---|---|---|---|---|
| address_full | Holtenauer Straße 100 Kiel | all | 200 | 9 | 9 | 7 | 3 | 1 | Hundert | Holtenauer Straße 100 |
| address_short | Breite Straße 1 Lübeck | all | 200 | 8 | 8 | 6 | 2 | 1 | Peter Pane | Breite Straße 1-5 | Lübeck |
| address_abbrev | Holtenauer Str. 100 | all | 200 | 7 | 7 | 8 | 3 | 1 | Hundert | Holtenauer Straße 100 |
| address_postcode | Sophienblatt 25 24114 | all | 200 | 8 | 8 | 5 | 7 | 1 | Kiel Hauptbahnhof | Sophienblatt 25-27 | Kiel |
| address_many | Breite Straße 1 | all | 200 | 8 | 7 | 5 | 5 | 1 | Breite Straße 1 | Hohenlockstedt |
| address_view | Bahnhofstraße 1 | view | 200 | 9 | 8 | 5 | 4 | 1 | Bahnhofstraße 1 | Kiel |

## phrase

| id | query | box | status | cold ms | warm ms | count ms | total | rank | top result |
|---|---|---|---|---|---|---|---|---|---|
| phrase_cat_place | Restaurant Kiel | all | 200 | 34 | 31 | 26 | 196 | - | Mensa |
| phrase_cat_name | Restaurant Maxim | all | 200 | 24 | 19 | 28 | 1 | 1 | Maximilian | Schubystraße 47 | Schleswig |
| phrase_cat_street | Bäckerei Holtenauer Straße | all | 200 | 147 | 162 | 142 | 18 | 1 | Rönnau | Holtenauer Straße 36 | Kiel |
| phrase_cat_only | Apotheke | view | 200 | 15 | 17 | 17 | 71 | 1 | Adler-Apotheke | Jungfernstieg 37 | Kiel |
| phrase_address | Holtenauer Straße 100, 24105 Kiel | all | 200 | 13 | 12 | 12 | 2 | 1 | Haveli | Holtenauer Straße 100 | Kiel |
| phrase_address_city_first | Kiel Holtenauer Straße 100 | all | 200 | 12 | 13 | 13 | 3 | 1 | Hundert | Holtenauer Straße 100 |
| phrase_name_place | Universität Kiel | all | 200 | 32 | 38 | 39 | 6 | 1 | Universitätskirche |
| phrase_typo | Lübek | all | 200 | 159 | 56 | 55 | 200 | 1 | Lübeck |
| phrase_prefix | holsten | all | 200 | 175 | 65 | 63 | 200 | 1 | Holsten MC | Langwedelerfeld 8 | Langwedel |
| phrase_partial | flensb | all | 200 | 147 | 37 | 34 | 200 | 1 | Flensburg |
| phrase_typo_street | Hautpstraße | all | 200 | 267 | 194 | 174 | 200 | 1 | Hauptstraße |

## point

| id | query | box | status | cold ms | warm ms | count ms | total | rank | top result |
|---|---|---|---|---|---|---|---|---|---|
| point_kiel_hbf | 10.1319,54.3151 | point | 200 | 15 | 21 | 20 | 15 | - | Ditsch | Sophienblatt 25-27 |
| point_luebeck | 10.6866,53.8663 | point | 200 | 20 | 20 | 19 | 27 | - | Hüxstraße 18 | Lübeck |

## Summary

- warm ms over all successful queries: min 6 / median 13 / max 194
- expected result at rank 1: 30 of 30; on the first page: 30 of 30

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
- **nonsense** (xqzvw plorp): Plirup ; Plirup ; Plirup
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
- **phrase_typo** (Lübek): Lübeck ; Luebeck ; Lübeck
- **phrase_prefix** (holsten): Holsten MC | Langwedelerfeld 8 | Langwedel ; Holstenau ; Holstenau
- **phrase_partial** (flensb): Flensburg ; Flensburg ; Flensburg
- **point_kiel_hbf** (10.1319,54.3151): Ditsch | Sophienblatt 25-27 ; Ditsch | Sophienblatt 25-27 ; Ditsch
- **point_luebeck** (10.6866,53.8663): Hüxstraße 18 | Lübeck ; Hüxstraße ; Schuback
- **name_typo** (Lübek): Lübeck ; Luebeck ; Lübeck
- **name_typo_street** (Hautpstraße): Hauptstraße ; Hauptstraße ; Hauptstraße
- **name_prefix** (holsten): Holsten MC | Langwedelerfeld 8 | Langwedel ; Holstenau ; Holstenau
- **name_partial** (flensb): Flensburg ; Flensburg ; Flensburg
- **name_typo_city** (Kiell): Kiel ; Kiel ; Kiel
- **phrase_typo_street** (Hautpstraße): Hauptstraße ; Hauptstraße ; Hauptstraße

</details>
