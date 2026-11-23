# Search profile -- 2026-11-23 10:23 UTC

- server http://127.0.0.1:8099, 50 queries, 3 requests each
- client linux x86_64 (dev stack, de_nrw_20261027_095445)
- default box (lon/lat): 5.85 50.32 -- 9.47 52.53; "view" queries carry a bbox of their own (intersects), "all" queries no spatial filter, "point" queries use the point mode

`cold` is the first request, `warm` the median of the rest (every request nudges `near` by a few millionths of a degree, so a response cache never answers); `count` is `/search/count` for the same body. `rank` is the position of the first result whose name or street contains `expect` (1 = top, 0 = not on the page, - = nothing expected). `total` is the server's total for the query. `ok`: rank 1-5 and warm at most 200 ms.

## phrase

| id | query | box | status | cold ms | warm ms | count ms | total | rank | ok | top result |
|---|---|---|---|---|---|---|---|---|---|---|
| typo_double_dropped | Düseldorf | all | 200 | 90 | 120 | 4 | 200 | 1 | yes | Düsseldorf |
| typo_swap | Dortmudn | all | 200 | 26 | 23 | 4 | 2 | 1 | yes | Dortmund |
| typo_drop_end | Gelsenkirchn | all | 200 | 64 | 55 | 2 | 200 | 1 | yes | Gelsenkirchen |
| typo_drop_inner | Mönchengladbch | all | 200 | 39 | 43 | 5 | 200 | 1 | yes | Mönchengladbach |
| typo_double_missing | Wupertal | all | 200 | 72 | 63 | 3 | 200 | 1 | yes | Wuppertal |
| typo_sound_d_t | Bielefelt | all | 200 | 62 | 58 | 3 | 200 | 1 | yes | Bielefeld |
| typo_sound_d_t_end | Lüdenscheit | all | 200 | 65 | 78 | 3 | 200 | 1 | yes | Lüdenscheid |
| typo_drop_e | Recklinghausn | all | 200 | 54 | 48 | 3 | 200 | 1 | yes | Recklinghausen |
| umlaut_ue | Muelheim an der Ruhr | all | 200 | 8 | 9 | 5 | 2 | 1 | yes | Mülheim an der Ruhr |
| umlaut_dropped | Gutersloh | all | 200 | 28 | 24 | 2 | 54 | 1 | yes | Gütersloh |
| umlaut_dropped_short | Koln | all | 200 | 40 | 39 | 3 | 180 | 1 | yes | Köln |
| typo_no_space | badoeynhausen | all | 200 | 37 | 36 | 3 | 43 | 1 | yes | Bad Oeynhausen |
| typo_landmark_h | Kölner Dohm | all | 200 | 72 | 72 | 3 | 200 | 4 | yes | Dohm |
| typo_landmark_n | Hermansdenkmal | all | 200 | 45 | 96 | 3 | 35 | 1 | yes | Hermannsdenkmal |
| typo_landmark_sound | Phantasieland | all | 200 | 23 | 22 | 2 | 4 | 1 | yes | Phantasialand | Berggeiststraße 31-41 | Brühl |
| typo_landmark_f_v | Zollferein | all | 200 | 26 | 25 | 3 | 10 | 1 | yes | Zollverein |
| typo_long_name | Technische Universitat Dortmund | all | 200 | 63 | 66 | 2 | 2 | 1 | yes | Technische Universität Dortmund |
| typo_street | Königsalee Düsseldorf | all | 200 | 41 | 43 | 3 | 7 | 1 | yes | Königsallee |
| typo_street_place | Schildergase Köln | all | 200 | 65 | 76 | 2 | 4 | 1 | yes | Höhe Straße, Schildergasse |
| typo_street_address | Hohe Strase 1 Köln | all | 200 | 11 | 12 | 3 | 2 | 1 | yes | Hohe Straße 1 | Köln |
| typo_category_view | Apoteke | view | 200 | 36 | 44 | 3 | 1 | 1 | yes | Apotheke |
| typo_category_place | Apoteke Bielefeld | all | 200 | 81 | 72 | 3 | 70 | 16 | **no** | Bielefeld |
| abbr_hbf | Köln Hbf | all | 200 | 32 | 30 | 2 | 12 | 1 | yes | Köln Hauptbahnhof | Trankgasse 11 | Köln |
| abbr_hbf_dot | Düsseldorf Hbf. | all | 200 | 9 | 11 | 3 | 7 | 1 | yes | Düsseldorf Hauptbahnhof |
| abbr_hbf_lower | essen hbf | all | 200 | 14 | 13 | 3 | 46 | 1 | yes | Essen Hauptbahnhof |
| abbr_hbf_typo | Dortmund Hbhf | all | 200 | 61 | 53 | 2 | 212 | 1 | yes | Dortmund Hauptbahnhof |
| abbr_bhf | Bhf Dortmund | all | 200 | 75 | 84 | 3 | 346 | 0 | **no** | Dortmund-Wickede |
| abbr_zob | ZOB Bonn | all | 200 | 16 | 15 | 3 | 4 | 1 | yes | Zentraler Omnibusbahnhof Bonn |
| abbr_zob_long | Zentraler Omnibusbahnhof Lünen | all | 200 | 141 | 139 | 2 | 90 | 1 | yes | ZOB Lünen |
| abbr_uni | Uni Köln | all | 200 | 22 | 28 | 3 | 76 | 0 | **no** | Universität |
| abbr_uni_bonn | Uni Bonn | all | 200 | 21 | 20 | 4 | 39 | 1 | yes | Universität Bonn | Friedrich-Ebert-Allee 144 | Bonn |
| abbr_rub | RUB | all | 200 | 59 | 54 | 3 | 200 | 0 | **no** | Rubinweg |
| abbr_tu | TU Dortmund | all | 200 | 37 | 43 | 3 | 3 | 1 | yes | Technische Universität Dortmund |
| abbr_th | TH Köln | all | 200 | 155 | 139 | 2 | 17 | 1 | yes | TH Köln | Ubierring 40 | Köln |
| abbr_fh | FH Dortmund | all | 200 | 44 | 45 | 2 | 5 | 1 | yes | Fachhochschule Dortmund | Sonnenstraße 96 | Dortmund |
| abbr_uniklinik | Uniklinik Köln | all | 200 | 8 | 11 | 3 | 3 | 1 | yes | Universitätsklinikum Köln |
| abbr_ukm | UKM Münster | all | 200 | 16 | 15 | 3 | 1 | 0 | **no** | UKM |
| abbr_kh | KH Herne | all | 200 | 98 | 85 | 4 | 206 | 1 | yes | Evangelisches Krankenhaus Herne Mitte | Wiescherstraße 24 | Herne |
| abbr_kita_view | Kita | view | 200 | 67 | 60 | 3 | 264 | 1 | yes | Kindertagesstätte | Friesenstraße 28 | Köln |
| abbr_vhs | VHS Dortmund | all | 200 | 9 | 9 | 3 | 3 | 1 | yes | Volkshochschule Dortmund |
| abbr_vhs_long | Volkshochschule Warendorf | all | 200 | 61 | 57 | 2 | 3 | 3 | yes | Landvolkshochschule |
| abbr_jh | JH Altena | all | 200 | 115 | 121 | 3 | 202 | 1 | yes | DJH Jugendherberge Altena, Burg | Fritz-Thomee-Straße 80 | Altena |
| abbr_ffw | FFW Herne | all | 200 | 198 | 178 | 3 | 208 | 1 | yes | Freiwillige Feuerwehr Herne LZ Röhlinghausen | Plutostraße 4 | Herne |
| abbr_spk | Spk KölnBonn | all | 200 | 47 | 41 | 3 | 203 | 1 | yes | Sparkasse KölnBonn | Dellbrücker Hauptstraße 121 | Köln |
| abbr_st | St. Augustin | all | 200 | 69 | 68 | 4 | 205 | 1 | yes | Sankt Augustin |
| abbr_sankt | Sankt Tönis | all | 200 | 52 | 53 | 3 | 145 | 1 | yes | St. Tönis |
| abbr_koe | Kö Düsseldorf | all | 200 | 62 | 72 | 3 | 12 | 4 | yes | Kö12 |
| abbr_adr | Mülheim a.d. Ruhr | all | 200 | 136 | 192 | 3 | 200 | 1 | yes | Mülheim an der Ruhr |
| abbr_iata | Flughafen DUS | all | 200 | 70 | 77 | 2 | 200 | 6 | **no** | Flughafen |
| abbr_str_address | Hohe Str 1 Köln | all | 200 | 13 | 12 | 2 | 2 | 1 | yes | Hohe Straße 1 | Köln |

## Summary

- warm ms over all successful queries: min 9 / median 50 / max 192
- expected result at rank 1: 41 of 50; on the first page: 46 of 50
- target (rank 1-5, warm at most 200 ms) met: 44 of 50; rank alone: 44 of 50

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
- **abbr_hbf** (Köln Hbf): Köln Hauptbahnhof | Trankgasse 11 | Köln ; Dom/Hbf ; Dom/Hbf
- **abbr_hbf_dot** (Düsseldorf Hbf.): Düsseldorf Hauptbahnhof ; Düsseldorf Hauptbahnhof ; Düsseldorf Hauptbahnhof
- **abbr_hbf_lower** (essen hbf): Essen Hauptbahnhof ; Essen Hauptbahnhof ; Essen Hauptbahnhof
- **abbr_hbf_typo** (Dortmund Hbhf): Dortmund Hauptbahnhof ; Dortmund Hauptbahnhof ; Dortmund Hauptbahnhof
- **abbr_bhf** (Bhf Dortmund): Dortmund-Wickede ; Clarenberg ; Clarenberg
- **abbr_zob** (ZOB Bonn): Zentraler Omnibusbahnhof Bonn ; Friedensplatz ; Bonn Fernbusbahnhof
- **abbr_zob_long** (Zentraler Omnibusbahnhof Lünen): ZOB Lünen ; Lünen ; Zentraler Omnibusbahnhof
- **abbr_uni** (Uni Köln): Universität ; Universität ; Universität
- **abbr_uni_bonn** (Uni Bonn): Universität Bonn | Friedrich-Ebert-Allee 144 | Bonn ; Institut für Psychologie/ Psychologische Hochschulambulanz | Dietkirchenstraße 28 | Bonn ; Universitätszahnklinik Bonn - Lehrgebäude
- **abbr_rub** (RUB): Rubinweg ; Rubinweg ; Rubinweg
- **abbr_tu** (TU Dortmund): Technische Universität Dortmund ; TU Dortmund Transferstelle ; TU Dortmund Übersichtsplan
- **abbr_th** (TH Köln): TH Köln | Ubierring 40 | Köln ; Technische Hochschule Köln (Campus Deutz) | Betzdorfer Straße 2 | Köln ; Technische Hochschule Köln (Campus Südstadt) | Ubierring 48 | Köln
- **abbr_fh** (FH Dortmund): Fachhochschule Dortmund | Sonnenstraße 96 | Dortmund ; Fachhochschule Dortmund ; FH-Plus | Emil-Figge-Straße 38 | Dortmund
- **abbr_uniklinik** (Uniklinik Köln): Universitätsklinikum Köln ; Uniklinik Köln ; Uniklinik Köln
- **abbr_ukm** (UKM Münster): UKM
- **abbr_kh** (KH Herne): Evangelisches Krankenhaus Herne Mitte | Wiescherstraße 24 | Herne ; Lukas-Hospiz | Jean-Vogel-Straße 43 | Herne ; Marienhospital Herne | Hölkeskampring 40 | Herne
- **abbr_kita_view** (Kita): Kindertagesstätte | Friesenstraße 28 | Köln ; Kindertagesstätte | Karl-Korn-Straße 7-9 | Köln ; Kindertagesstätte
- **abbr_vhs** (VHS Dortmund): Volkshochschule Dortmund ; VHS Dortmund ; VHS Dortmund
- **abbr_vhs_long** (Volkshochschule Warendorf): Landvolkshochschule ; Landvolkshochschule ; VHS Warendorf / Baudezernat | Freckenhorster Straße 43 | Warendorf
- **abbr_jh** (JH Altena): DJH Jugendherberge Altena, Burg | Fritz-Thomee-Straße 80 | Altena ; Pfadfinderheim Jung-Stilling | Horst 4 | Altena ; Altena
- **abbr_ffw** (FFW Herne): Freiwillige Feuerwehr Herne LZ Röhlinghausen | Plutostraße 4 | Herne ; Freiwillige Feuerwehr Herne-Sodingen, Gerätehaus Ost | Bogenweg 1 | Herne ; Freiwillige FW Becke
- **abbr_spk** (Spk KölnBonn): Sparkasse KölnBonn | Dellbrücker Hauptstraße 121 | Köln ; Sparkasse KölnBonn | Köln ; Sparkasse KölnBonn
- **abbr_st** (St. Augustin): Sankt Augustin ; Sankt Augustin ; Sankt Augustin
- **abbr_sankt** (Sankt Tönis): St. Tönis ; St. Tönis ; St. Tönis
- **abbr_koe** (Kö Düsseldorf): Kö12 ; Kö 21 ; Ko
- **abbr_adr** (Mülheim a.d. Ruhr): Mülheim an der Ruhr ; Mülheim an der Ruhr ; Mülheim
- **abbr_iata** (Flughafen DUS): Flughafen ; Flughafen ; Flughafen
- **abbr_str_address** (Hohe Str 1 Köln): Hohe Straße 1 | Köln ; Hohe Straße 1 | Köln

</details>
