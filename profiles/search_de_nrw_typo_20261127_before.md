# Search profile -- 2026-11-27 16:41 UTC

- server http://127.0.0.1:8099, 53 queries, 5 requests each
- client linux x86_64
- default box (lon/lat): 5.85 50.32 -- 9.47 52.53; "view" queries carry a bbox of their own (intersects), "all" queries no spatial filter, "point" queries use the point mode

`cold` is the first request, `warm` the median of the rest (every request nudges `near` by a few millionths of a degree, so a response cache never answers); `count` is `/search/count` for the same body. `rank` is the position of the first result whose name or street contains `expect` (1 = top, 0 = not on the page, - = nothing expected). `total` is the server's total for the query. `ok`: rank 1-5 and warm at most 200 ms.

## phrase

| id | query | box | status | cold ms | warm ms | count ms | total | rank | ok | top result |
|---|---|---|---|---|---|---|---|---|---|---|
| typo_double_dropped | Düseldorf | all | 200 | 848 | 123 | 117 | 200 | 1 | yes | Düsseldorf |
| typo_swap | Dortmudn | all | 200 | 595 | 54 | 68 | 2 | 1 | yes | Dortmund |
| typo_drop_end | Gelsenkirchn | all | 200 | 831 | 109 | 92 | 200 | 1 | yes | Gelsenkirchen |
| typo_drop_inner | Mönchengladbch | all | 200 | 708 | 81 | 73 | 200 | 1 | yes | Mönchengladbach |
| typo_double_missing | Wupertal | all | 200 | 1023 | 105 | 101 | 200 | 1 | yes | Wuppertal |
| typo_sound_d_t | Bielefelt | all | 200 | 939 | 101 | 113 | 200 | 1 | yes | Bielefeld |
| typo_sound_d_t_end | Lüdenscheit | all | 200 | 904 | 112 | 104 | 200 | 1 | yes | Lüdenscheid |
| typo_drop_e | Recklinghausn | all | 200 | 720 | 115 | 93 | 200 | 1 | yes | Recklinghausen |
| umlaut_ue | Muelheim an der Ruhr | all | 200 | 110 | 43 | 43 | 2 | 1 | yes | Mülheim an der Ruhr |
| umlaut_dropped | Gutersloh | all | 200 | 678 | 67 | 69 | 54 | 1 | yes | Gütersloh |
| umlaut_dropped_short | Koln | all | 200 | 1050 | 78 | 92 | 179 | 1 | yes | Köln |
| typo_no_space | badoeynhausen | all | 200 | 508 | 70 | 74 | 43 | 1 | yes | Bad Oeynhausen |
| typo_landmark_h | Kölner Dohm | all | 200 | 1109 | 121 | 115 | 200 | 2 | yes | Dohm |
| typo_landmark_n | Hermansdenkmal | all | 200 | 882 | 84 | 80 | 35 | 1 | yes | Hermannsdenkmal |
| typo_landmark_sound | Phantasieland | all | 200 | 180 | 61 | 62 | 4 | 1 | yes | Phantasialand | Berggeiststraße 31-41 | Brühl |
| typo_landmark_f_v | Zollferein | all | 200 | 561 | 64 | 60 | 10 | 1 | yes | Zollverein |
| typo_long_name | Technische Universitat Dortmund | all | 200 | 231 | 99 | 101 | 2 | 1 | yes | Technische Universität Dortmund |
| typo_street | Königsalee Düsseldorf | all | 200 | 231 | 79 | 76 | 5 | 1 | yes | Königsallee |
| typo_street_place | Schildergase Köln | all | 200 | 227 | 99 | 101 | 4 | 1 | yes | Höhe Straße, Schildergasse |
| typo_street_address | Hohe Strase 1 Köln | all | 200 | 284 | 48 | 49 | 2 | 1 | yes | Hohe Straße 1 | Köln |
| typo_category_view | Apoteke | view | 200 | 584 | 71 | 67 | 1 | 1 | yes | Apotheke |
| typo_category_place | Apoteke Bielefeld | all | 200 | 340 | 108 | 111 | 67 | 14 | **no** | Bielefeld |
| typo_category_place_kh | Krankenhauss Bochum | all | 200 | 294 | 101 | 93 | 6 | 1 | yes | Am Krankenhaus |
| typo_place_category | Apotheke Dortmnd | all | 200 | 1121 | 117 | 128 | 68 | 1 | yes | Apotheke |
| typo_place_category_city | Bäckerei Düseldorf | all | 200 | 1031 | 145 | 137 | 157 | 2 | yes | Düsseldorf |
| abbr_hbf | Köln Hbf | all | 200 | 144 | 49 | 45 | 1 | 1 | yes | Köln Hauptbahnhof | Trankgasse 11 | Köln |
| abbr_hbf_dot | Düsseldorf Hbf. | all | 200 | 45 | 44 | 48 | 7 | 1 | yes | Düsseldorf Hauptbahnhof |
| abbr_hbf_lower | essen hbf | all | 200 | 134 | 47 | 44 | 46 | 1 | yes | Essen Hauptbahnhof |
| abbr_hbf_typo | Dortmund Hbhf | all | 200 | 120 | 49 | 48 | 12 | 1 | yes | Dortmund Hauptbahnhof |
| abbr_bhf | Bhf Dortmund | all | 200 | 213 | 75 | 68 | 152 | 0 | **no** | Dortmund-Wickede |
| abbr_zob | ZOB Bonn | all | 200 | 159 | 50 | 49 | 1 | 1 | yes | Zentraler Omnibusbahnhof Bonn |
| abbr_zob_long | Zentraler Omnibusbahnhof Lünen | all | 200 | 383 | 173 | 172 | 88 | 1 | yes | ZOB Lünen |
| abbr_uni | Uni Köln | all | 200 | 173 | 63 | 57 | 78 | 0 | **no** | Universität |
| abbr_uni_bonn | Uni Bonn | all | 200 | 140 | 46 | 48 | 1 | 1 | yes | Universität Bonn | Friedrich-Ebert-Allee 144 | Bonn |
| abbr_rub | RUB | all | 200 | 1539 | 100 | 93 | 200 | 0 | **no** | Rubinweg |
| abbr_tu | TU Dortmund | all | 200 | 124 | 47 | 47 | 1 | 1 | yes | Technische Universität Dortmund |
| abbr_th | TH Köln | all | 200 | 400 | 176 | 174 | 17 | 1 | yes | TH Köln | Ubierring 40 | Köln |
| abbr_fh | FH Dortmund | all | 200 | 120 | 48 | 44 | 2 | 1 | yes | Fachhochschule Dortmund | Sonnenstraße 96 | Dortmund |
| abbr_uniklinik | Uniklinik Köln | all | 200 | 45 | 43 | 43 | 3 | 1 | yes | Universitätsklinikum Köln |
| abbr_ukm | UKM Münster | all | 200 | 161 | 51 | 58 | 1 | 0 | **no** | UKM |
| abbr_kh | KH Herne | all | 200 | 174 | 56 | 54 | 6 | 1 | yes | Evangelisches Krankenhaus Herne Mitte | Wiescherstraße 24 | Herne |
| abbr_kita_view | Kita | view | 200 | 222 | 80 | 76 | 210 | 1 | yes | Kindertagesstätte | Friesenstraße 28 | Köln |
| abbr_vhs | VHS Dortmund | all | 200 | 111 | 44 | 41 | 3 | 1 | yes | Volkshochschule Dortmund |
| abbr_vhs_long | Volkshochschule Warendorf | all | 200 | 264 | 93 | 91 | 3 | 3 | yes | Landvolkshochschule |
| abbr_jh | JH Altena | all | 200 | 114 | 58 | 54 | 2 | 1 | yes | DJH Jugendherberge Altena, Burg | Fritz-Thomee-Straße 80 | Altena |
| abbr_ffw | FFW Herne | all | 200 | 1069 | 186 | 170 | 8 | 1 | yes | Freiwillige Feuerwehr Herne LZ Röhlinghausen | Plutostraße 4 | Herne |
| abbr_spk | Spk KölnBonn | all | 200 | 150 | 53 | 53 | 51 | 1 | yes | Sparkasse KölnBonn | Dellbrücker Hauptstraße 121 | Köln |
| abbr_st | St. Augustin | all | 200 | 163 | 50 | 47 | 8 | 1 | yes | Sankt Augustin |
| abbr_sankt | Sankt Tönis | all | 200 | 1023 | 98 | 89 | 145 | 1 | yes | St. Tönis |
| abbr_koe | Kö Düsseldorf | all | 200 | 543 | 108 | 112 | 9 | 4 | yes | Kö12 |
| abbr_adr | Mülheim a.d. Ruhr | all | 200 | 153 | 53 | 48 | 2 | 1 | yes | Mülheim an der Ruhr |
| abbr_iata | Flughafen DUS | all | 200 | 331 | 116 | 125 | 199 | 5 | yes | Flughafen |
| abbr_str_address | Hohe Str 1 Köln | all | 200 | 50 | 50 | 49 | 2 | 1 | yes | Hohe Straße 1 | Köln |

## Summary

- warm ms over all successful queries: min 43 / median 75 / max 186
- expected result at rank 1: 43 of 53; on the first page: 49 of 53
- target (rank 1-5, warm at most 200 ms) met: 48 of 53; rank alone: 48 of 53

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
- **typo_landmark_h** (Kölner Dohm): Dohm ; Kölner Dom | Domkloster 4 | Köln ; Kölner Zoo | Riehler Straße 173 | Köln
- **typo_landmark_n** (Hermansdenkmal): Hermannsdenkmal ; Waldbühne am Hermannsdenkmal | Grotenburg 50 | Detmold ; Hermannsdenkmal
- **typo_landmark_sound** (Phantasieland): Phantasialand | Berggeiststraße 31-41 | Brühl ; Phantasialand ; Phantasia
- **typo_landmark_f_v** (Zollferein): Zollverein ; Zollverein ; Zollverein
- **typo_long_name** (Technische Universitat Dortmund): Technische Universität Dortmund ; Universität | Vogelpothsweg | Dortmund
- **typo_street** (Königsalee Düsseldorf): Königsallee ; Königsallee ; Ausgang Königsallee
- **typo_street_place** (Schildergase Köln): Höhe Straße, Schildergasse ; Schildergasse ; Filmhaus Schildergasse | Schildergasse 98-100 | Köln
- **typo_street_address** (Hohe Strase 1 Köln): Hohe Straße 1 | Köln ; Hohe Straße 1 | Köln
- **typo_category_view** (Apoteke): Apotheke
- **typo_category_place** (Apoteke Bielefeld): Bielefeld ; Bielefeld ; Bielfeld
- **typo_category_place_kh** (Krankenhauss Bochum): Am Krankenhaus ; Augusta-Krankenhaus ; Augusta-Krankenhaus
- **typo_place_category** (Apotheke Dortmnd): Apotheke ; Apotheke ; Apotheke
- **typo_place_category_city** (Bäckerei Düseldorf): Düsseldorf ; Bäckerei ; Bäckerei
- **abbr_hbf** (Köln Hbf): Köln Hauptbahnhof | Trankgasse 11 | Köln
- **abbr_hbf_dot** (Düsseldorf Hbf.): Düsseldorf Hauptbahnhof ; Düsseldorf Hauptbahnhof ; Düsseldorf Hauptbahnhof
- **abbr_hbf_lower** (essen hbf): Essen Hauptbahnhof ; Essen Hauptbahnhof ; Essen Hauptbahnhof
- **abbr_hbf_typo** (Dortmund Hbhf): Dortmund Hauptbahnhof ; Dortmund Hauptbahnhof ; Dortmund Hauptbahnhof
- **abbr_bhf** (Bhf Dortmund): Dortmund-Wickede ; Clarenberg ; Clarenberg
- **abbr_zob** (ZOB Bonn): Zentraler Omnibusbahnhof Bonn
- **abbr_zob_long** (Zentraler Omnibusbahnhof Lünen): ZOB Lünen ; Lünen ; Zentraler Omnibusbahnhof
- **abbr_uni** (Uni Köln): Universität ; Universität ; Universität
- **abbr_uni_bonn** (Uni Bonn): Universität Bonn | Friedrich-Ebert-Allee 144 | Bonn
- **abbr_rub** (RUB): Rubinweg ; Rubinweg ; Rubinweg
- **abbr_tu** (TU Dortmund): Technische Universität Dortmund
- **abbr_th** (TH Köln): TH Köln | Ubierring 40 | Köln ; Technische Hochschule Köln (Campus Deutz) | Betzdorfer Straße 2 | Köln ; Technische Hochschule Köln (Campus Südstadt) | Ubierring 48 | Köln
- **abbr_fh** (FH Dortmund): Fachhochschule Dortmund | Sonnenstraße 96 | Dortmund ; Fachhochschule Dortmund
- **abbr_uniklinik** (Uniklinik Köln): Universitätsklinikum Köln ; Uniklinik Köln ; Uniklinik Köln
- **abbr_ukm** (UKM Münster): UKM
- **abbr_kh** (KH Herne): Evangelisches Krankenhaus Herne Mitte | Wiescherstraße 24 | Herne ; Lukas-Hospiz | Jean-Vogel-Straße 43 | Herne ; Marienhospital Herne | Hölkeskampring 40 | Herne
- **abbr_kita_view** (Kita): Kindertagesstätte | Friesenstraße 28 | Köln ; Kindertagesstätte | Karl-Korn-Straße 7-9 | Köln ; Kindertagesstätte
- **abbr_vhs** (VHS Dortmund): Volkshochschule Dortmund ; VHS Dortmund ; VHS Dortmund
- **abbr_vhs_long** (Volkshochschule Warendorf): Landvolkshochschule ; Landvolkshochschule ; VHS Warendorf / Baudezernat | Freckenhorster Straße 43 | Warendorf
- **abbr_jh** (JH Altena): DJH Jugendherberge Altena, Burg | Fritz-Thomee-Straße 80 | Altena ; Pfadfinderheim Jung-Stilling | Horst 4 | Altena
- **abbr_ffw** (FFW Herne): Freiwillige Feuerwehr Herne LZ Röhlinghausen | Plutostraße 4 | Herne ; Freiwillige Feuerwehr Herne-Sodingen, Gerätehaus Ost | Bogenweg 1 | Herne ; Freiwillige FW Becke
- **abbr_spk** (Spk KölnBonn): Sparkasse KölnBonn | Dellbrücker Hauptstraße 121 | Köln ; Sparkasse KölnBonn | Köln ; Sparkasse KölnBonn
- **abbr_st** (St. Augustin): Sankt Augustin ; Sankt Augustin ; Sankt Augustin
- **abbr_sankt** (Sankt Tönis): St. Tönis ; St. Tönis ; St. Tönis
- **abbr_koe** (Kö Düsseldorf): Kö12 ; Kö 21 ; Ko
- **abbr_adr** (Mülheim a.d. Ruhr): Mülheim an der Ruhr ; Mülheim an der Ruhr
- **abbr_iata** (Flughafen DUS): Flughafen ; Flughafen ; Flughafen
- **abbr_str_address** (Hohe Str 1 Köln): Hohe Straße 1 | Köln ; Hohe Straße 1 | Köln

</details>
