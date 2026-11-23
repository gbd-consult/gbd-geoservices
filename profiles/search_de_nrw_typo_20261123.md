# Search profile -- 2026-11-23 09:51 UTC

- server http://127.0.0.1:8099, 50 queries, 3 requests each
- client linux x86_64 (dev stack, de_nrw_20261027_095445)
- default box (lon/lat): 5.85 50.32 -- 9.47 52.53; "view" queries carry a bbox of their own (intersects), "all" queries no spatial filter, "point" queries use the point mode

`cold` is the first request, `warm` the median of the rest (every request nudges `near` by a few millionths of a degree, so a response cache never answers); `count` is `/search/count` for the same body. `rank` is the position of the first result whose name or street contains `expect` (1 = top, 0 = not on the page, - = nothing expected). `total` is the server's total for the query. `ok`: rank 1-5 and warm at most 200 ms.

## phrase

| id | query | box | status | cold ms | warm ms | count ms | total | rank | ok | top result |
|---|---|---|---|---|---|---|---|---|---|---|
| typo_double_dropped | Düseldorf | all | 200 | 152 | 78 | 141 | 200 | 1 | yes | Düsseldorf |
| typo_swap | Dortmudn | all | 200 | 28 | 22 | 19 | 2 | 1 | yes | Dortmund |
| typo_drop_end | Gelsenkirchn | all | 200 | 53 | 51 | 63 | 200 | 1 | yes | Gelsenkirchen |
| typo_drop_inner | Mönchengladbch | all | 200 | 38 | 37 | 37 | 200 | 1 | yes | Mönchengladbach |
| typo_double_missing | Wupertal | all | 200 | 59 | 58 | 56 | 200 | 1 | yes | Wuppertal |
| typo_sound_d_t | Bielefelt | all | 200 | 55 | 55 | 60 | 200 | 1 | yes | Bielefeld |
| typo_sound_d_t_end | Lüdenscheit | all | 200 | 65 | 64 | 63 | 200 | 1 | yes | Lüdenscheid |
| typo_drop_e | Recklinghausn | all | 200 | 45 | 45 | 54 | 200 | 1 | yes | Recklinghausen |
| umlaut_ue | Muelheim an der Ruhr | all | 200 | 7 | 7 | 7 | 2 | 1 | yes | Mülheim an der Ruhr |
| umlaut_dropped | Gutersloh | all | 200 | 31 | 25 | 24 | 54 | 1 | yes | Gütersloh |
| umlaut_dropped_short | Koln | all | 200 | 39 | 73 | 47 | 180 | 1 | yes | Köln |
| typo_no_space | badoeynhausen | all | 200 | 39 | 32 | 34 | 43 | 1 | yes | Bad Oeynhausen |
| typo_landmark_h | Kölner Dohm | all | 200 | 74 | 69 | 64 | 200 | 4 | yes | Dohm |
| typo_landmark_n | Hermansdenkmal | all | 200 | 44 | 49 | 42 | 35 | 1 | yes | Hermannsdenkmal |
| typo_landmark_sound | Phantasieland | all | 200 | 21 | 20 | 20 | 4 | 1 | yes | Phantasialand | Berggeiststraße 31-41 | Brühl |
| typo_landmark_f_v | Zollferein | all | 200 | 24 | 23 | 23 | 10 | 1 | yes | Zollverein |
| typo_long_name | Technische Universitat Dortmund | all | 200 | 62 | 62 | 61 | 2 | 1 | yes | Technische Universität Dortmund |
| typo_street | Königsalee Düsseldorf | all | 200 | 43 | 40 | 40 | 7 | 1 | yes | Königsallee |
| typo_street_place | Schildergase Köln | all | 200 | 64 | 62 | 62 | 4 | 1 | yes | Höhe Straße, Schildergasse |
| typo_street_address | Hohe Strase 1 Köln | all | 200 | 10 | 10 | 10 | 2 | 1 | yes | Hohe Straße 1 | Köln |
| typo_category_view | Apoteke | view | 200 | 34 | 36 | 29 | 1 | 1 | yes | Apotheke |
| typo_category_place | Apoteke Bielefeld | all | 200 | 66 | 66 | 66 | 70 | 16 | **no** | Bielefeld |
| abbr_hbf | Köln Hbf | all | 200 | 25 | 25 | 25 | 11 | 0 | **no** | Dom/Hbf |
| abbr_hbf_dot | Düsseldorf Hbf. | all | 200 | 6 | 6 | 6 | 1 | 0 | **no** | Düsseldorf Hbf |
| abbr_hbf_lower | essen hbf | all | 200 | 7 | 10 | 9 | 33 | 0 | **no** | Essen Hbf |
| abbr_hbf_typo | Dortmund Hbhf | all | 200 | 49 | 48 | 53 | 200 | 0 | **no** | Dortmund |
| abbr_bhf | Bhf Dortmund | all | 200 | 54 | 53 | 119 | 200 | 0 | **no** | Dortmund |
| abbr_zob | ZOB Bonn | all | 200 | 42 | 43 | 30 | 4 | 2 | yes | Friedensplatz |
| abbr_zob_long | Zentraler Omnibusbahnhof Lünen | all | 200 | 152 | 130 | 130 | 89 | 0 | **no** | Lünen |
| abbr_uni | Uni Köln | all | 200 | 19 | 16 | 16 | 69 | 0 | **no** | SAE Institute Köln | Carlswerkstraße 11c | Köln |
| abbr_uni_bonn | Uni Bonn | all | 200 | 15 | 17 | 17 | 39 | 4 | yes | Institut für Psychologie/ Psychologische Hochschulambulanz | Dietkirchenstraße 28 | Bonn |
| abbr_rub | RUB | all | 200 | 53 | 49 | 46 | 200 | 0 | **no** | Rubinweg |
| abbr_tu | TU Dortmund | all | 200 | 35 | 34 | 34 | 2 | 0 | **no** | TU Dortmund Transferstelle |
| abbr_th | TH Köln | all | 200 | 6 | 6 | 6 | 1 | 1 | yes | TH Köln | Ubierring 40 | Köln |
| abbr_fh | FH Dortmund | all | 200 | 42 | 41 | 42 | 3 | 0 | **no** | FH-Plus | Emil-Figge-Straße 38 | Dortmund |
| abbr_uniklinik | Uniklinik Köln | all | 200 | 6 | 6 | 6 | 2 | 0 | **no** | Uniklinik Köln |
| abbr_ukm | UKM Münster | all | 200 | 13 | 14 | 12 | 1 | 0 | **no** | UKM |
| abbr_kh | KH Herne | all | 200 | 92 | 84 | 81 | 200 | 0 | **no** | Herne |
| abbr_kita_view | Kita | view | 200 | 36 | 35 | 35 | 87 | 1 | yes | Kita Mare | Mannsfelder Straße 41 |
| abbr_vhs | VHS Dortmund | all | 200 | 7 | 8 | 8 | 2 | 1 | yes | VHS Dortmund |
| abbr_vhs_long | Volkshochschule Warendorf | all | 200 | 42 | 40 | 37 | 2 | 0 | **no** | Landvolkshochschule |
| abbr_jh | JH Altena | all | 200 | 104 | 103 | 120 | 200 | 0 | **no** | Altena |
| abbr_ffw | FFW Herne | all | 200 | 76 | 117 | 105 | 200 | 0 | **no** | Herne |
| abbr_spk | Spk KölnBonn | all | 200 | 40 | 35 | 34 | 200 | 10 | **no** | Köln-Bonn | Bonn-Brühler-Straße 109 | Bornheim |
| abbr_st | St. Augustin | all | 200 | 58 | 60 | 61 | 200 | 1 | yes | Sankt Augustin |
| abbr_sankt | Sankt Tönis | all | 200 | 42 | 52 | 58 | 145 | 2 | yes | Sankt Töniser Straße |
| abbr_koe | Kö Düsseldorf | all | 200 | 61 | 61 | 62 | 12 | 4 | yes | Kö12 |
| abbr_adr | Mülheim a.d. Ruhr | all | 200 | 145 | 123 | 119 | 200 | 1 | yes | Mülheim an der Ruhr |
| abbr_iata | Flughafen DUS | all | 200 | 66 | 69 | 68 | 200 | 6 | **no** | Flughafen |
| abbr_str_address | Hohe Str 1 Köln | all | 200 | 11 | 10 | 10 | 2 | 1 | yes | Hohe Straße 1 | Köln |

## Summary

- warm ms over all successful queries: min 6 / median 42 / max 130
- expected result at rank 1: 26 of 50; on the first page: 34 of 50
- target (rank 1-5, warm at most 200 ms) met: 31 of 50; rank alone: 31 of 50

<details><summary>Top 3 per query</summary>

- **typo_double_dropped** (Düseldorf): Düsseldorf ; Düsseldorf Airport ; Düsseldorf-Hamm
- **typo_swap** (Dortmudn): Dortmund ; Dönaladn Dortmund
- **typo_drop_end** (Gelsenkirchn): Gelsenkirchen ; Gelsenkirchen Zoo ; Gelsenkirchen-Süd
- **typo_drop_inner** (Mönchengladbch): Mönchengladbach ; MGL Mönchengladbach Airport ; Flughafen Düsseldorf Mönchengladbach
- **typo_double_missing** (Wupertal): Wuppertal ; Zoo Wuppertal | Hubertusallee 30 | Wuppertal ; Wuppertal-Oehde
- **typo_sound_d_t** (Bielefelt): Bielefeld ; Flugplatz Bielefeld | Am Flugplatz 1 | Bielefeld ; Bielefeld Ost | Am Ostbahnhof 1 | Bielefeld
- **typo_sound_d_t_end** (Lüdenscheit): Lüdenscheid ; Lüdenscheid ; Lüdenscheid
- **typo_drop_e** (Recklinghausn): Recklinghausen ; Recklinghausen ; Recklinghausen-Ost
- **umlaut_ue** (Muelheim an der Ruhr): Mülheim an der Ruhr ; Mülheim an der Ruhr
- **umlaut_dropped** (Gutersloh): Gütersloh ; Gütersloh ; Gütersloh
- **umlaut_dropped_short** (Koln): Köln ; Kuhlen ; Kallen
- **typo_no_space** (badoeynhausen): Bad Oeynhausen ; Bad Oeynhausen-Ost ; Bad Oeynhausen-Ost
- **typo_landmark_h** (Kölner Dohm): Dohm ; Dohm ; Dohm
- **typo_landmark_n** (Hermansdenkmal): Hermannsdenkmal ; Waldbühne am Hermannsdenkmal | Grotenburg 50 | Detmold ; Hermannsdenkmal
- **typo_landmark_sound** (Phantasieland): Phantasialand | Berggeiststraße 31-41 | Brühl ; Phantasialand ; Phantasia
- **typo_landmark_f_v** (Zollferein): Zollverein ; Zollverein ; Zollverein
- **typo_long_name** (Technische Universitat Dortmund): Technische Universität Dortmund ; Universität | Vogelpothsweg | Dortmund
- **typo_street** (Königsalee Düsseldorf): Königsallee ; Königsallee ; Ausgang Königsallee
- **typo_street_place** (Schildergase Köln): Höhe Straße, Schildergasse ; Schildergasse ; Filmhaus Schildergasse | Schildergasse 98-100 | Köln
- **typo_street_address** (Hohe Strase 1 Köln): Hohe Straße 1 | Köln ; Hohe Straße 1 | Köln
- **typo_category_view** (Apoteke): Apotheke
- **typo_category_place** (Apoteke Bielefeld): Bielefeld ; Bielefeld ; Bielfeld
- **abbr_hbf** (Köln Hbf): Dom/Hbf ; Dom/Hbf ; Dom/Hbf
- **abbr_hbf_dot** (Düsseldorf Hbf.): Düsseldorf Hbf
- **abbr_hbf_lower** (essen hbf): Essen Hbf ; Essen Hbf ; Essen Hbf
- **abbr_hbf_typo** (Dortmund Hbhf): Dortmund ; Dortmund Hbf ; Dortmund-Hörde
- **abbr_bhf** (Bhf Dortmund): Dortmund ; Dortmund-Barop ; Dortmund-Barop
- **abbr_zob** (ZOB Bonn): Friedensplatz ; Zentraler Omnibusbahnhof Bonn ; Bonn Fernbusbahnhof
- **abbr_zob_long** (Zentraler Omnibusbahnhof Lünen): Lünen ; Zentraler Omnibusbahnhof ; Zentraler Omnibusbahnhof Bonn
- **abbr_uni** (Uni Köln): SAE Institute Köln | Carlswerkstraße 11c | Köln ; Cologne Game Lab | Schanzenstraße 18 ; Code & Context | Schanzenstraße 28 | Köln
- **abbr_uni_bonn** (Uni Bonn): Institut für Psychologie/ Psychologische Hochschulambulanz | Dietkirchenstraße 28 | Bonn ; Universitätszahnklinik Bonn - Lehrgebäude ; Philosophische Fakultät – Institut für Geschichtswissenschaft
- **abbr_rub** (RUB): Rubinweg ; Rubinweg ; Rubinweg
- **abbr_tu** (TU Dortmund): TU Dortmund Transferstelle ; TU Dortmund Übersichtsplan
- **abbr_th** (TH Köln): TH Köln | Ubierring 40 | Köln
- **abbr_fh** (FH Dortmund): FH-Plus | Emil-Figge-Straße 38 | Dortmund ; FH-Plus-3 | Emil-Figge-Straße 38b | Dortmund ; FH-Plus-2 | Emil-Figge-Straße 38a | Dortmund
- **abbr_uniklinik** (Uniklinik Köln): Uniklinik Köln ; Uniklinik Köln
- **abbr_ukm** (UKM Münster): UKM
- **abbr_kh** (KH Herne): Herne ; Herne | Konrad-Adenauer-Platz 1 | Herne ; Horn
- **abbr_kita_view** (Kita): Kita Mare | Mannsfelder Straße 41 ; Kita Quäker | Kreutzerstraße 5-9 | Köln ; KiTa der AWO
- **abbr_vhs** (VHS Dortmund): VHS Dortmund ; VHS Dortmund
- **abbr_vhs_long** (Volkshochschule Warendorf): Landvolkshochschule ; Landvolkshochschule
- **abbr_jh** (JH Altena): Altena ; Altenau ; Altenhöhe
- **abbr_ffw** (FFW Herne): Herne ; Herne | Konrad-Adenauer-Platz 1 | Herne ; Werne
- **abbr_spk** (Spk KölnBonn): Köln-Bonn | Bonn-Brühler-Straße 109 | Bornheim ; Spich ; Speck
- **abbr_st** (St. Augustin): Sankt Augustin ; St. Augustinus Krankenhaus | Renkerstraße 45 | Düren ; St. Augustinus | Pfarrweg 3 | Attendorn
- **abbr_sankt** (Sankt Tönis): Sankt Töniser Straße ; St. Tönis ; Sankt-Tönnis-Platz
- **abbr_koe** (Kö Düsseldorf): Kö12 ; Kö 21 ; Ko
- **abbr_adr** (Mülheim a.d. Ruhr): Mülheim an der Ruhr ; Mülheim ; Mülheim
- **abbr_iata** (Flughafen DUS): Flughafen ; Flughafen ; Flughafen
- **abbr_str_address** (Hohe Str 1 Köln): Hohe Straße 1 | Köln ; Hohe Straße 1 | Köln

</details>
