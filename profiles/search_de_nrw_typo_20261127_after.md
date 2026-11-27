# Search profile -- 2026-11-27 19:36 UTC

- server http://127.0.0.1:8099, 53 queries, 5 requests each
- client linux x86_64
- default box (lon/lat): 5.85 50.32 -- 9.47 52.53; "view" queries carry a bbox of their own (intersects), "all" queries no spatial filter, "point" queries use the point mode

`cold` is the first request, `warm` the median of the rest (every request nudges `near` by a few millionths of a degree, so a response cache never answers); `count` is `/search/count` for the same body. `rank` is the position of the first result whose name or street contains `expect` (1 = top, 0 = not on the page, - = nothing expected). `total` is the server's total for the query. `ok`: rank 1-5 and warm at most 200 ms.

## phrase

| id | query | box | status | cold ms | warm ms | count ms | total | rank | ok | top result |
|---|---|---|---|---|---|---|---|---|---|---|
| typo_double_dropped | Düseldorf | all | 200 | 152 | 113 | 108 | 200 | 1 | yes | Düsseldorf |
| typo_swap | Dortmudn | all | 200 | 57 | 56 | 57 | 2 | 1 | yes | Dortmund |
| typo_drop_end | Gelsenkirchn | all | 200 | 93 | 108 | 90 | 200 | 1 | yes | Gelsenkirchen |
| typo_drop_inner | Mönchengladbch | all | 200 | 81 | 78 | 79 | 200 | 1 | yes | Mönchengladbach |
| typo_double_missing | Wupertal | all | 200 | 103 | 103 | 100 | 200 | 1 | yes | Wuppertal |
| typo_sound_d_t | Bielefelt | all | 200 | 97 | 97 | 95 | 200 | 1 | yes | Bielefeld |
| typo_sound_d_t_end | Lüdenscheit | all | 200 | 102 | 105 | 108 | 200 | 1 | yes | Lüdenscheid |
| typo_drop_e | Recklinghausn | all | 200 | 83 | 86 | 81 | 200 | 1 | yes | Recklinghausen |
| umlaut_ue | Muelheim an der Ruhr | all | 200 | 49 | 43 | 46 | 2 | 1 | yes | Mülheim an der Ruhr |
| umlaut_dropped | Gutersloh | all | 200 | 128 | 77 | 73 | 200 | 1 | yes | Gütersloh |
| umlaut_dropped_short | Koln | all | 200 | 101 | 103 | 97 | 200 | 1 | yes | Köln |
| typo_no_space | badoeynhausen | all | 200 | 85 | 77 | 73 | 71 | 1 | yes | Bad Oeynhausen |
| typo_landmark_h | Kölner Dohm | all | 200 | 127 | 126 | 119 | 200 | 4 | yes | Dohm |
| typo_landmark_n | Hermansdenkmal | all | 200 | 88 | 87 | 92 | 35 | 1 | yes | Hermannsdenkmal |
| typo_landmark_sound | Phantasieland | all | 200 | 63 | 59 | 66 | 7 | 1 | yes | Phantasialand | Berggeiststraße 31-41 | Brühl |
| typo_landmark_f_v | Zollferein | all | 200 | 74 | 73 | 71 | 114 | 1 | yes | Zollverein |
| typo_long_name | Technische Universitat Dortmund | all | 200 | 122 | 116 | 114 | 2 | 1 | yes | Technische Universität Dortmund |
| typo_street | Königsalee Düsseldorf | all | 200 | 90 | 98 | 96 | 27 | 1 | yes | Königsallee |
| typo_street_place | Schildergase Köln | all | 200 | 112 | 116 | 116 | 4 | 1 | yes | Höhe Straße, Schildergasse |
| typo_street_address | Hohe Strase 1 Köln | all | 200 | 49 | 51 | 58 | 2 | 1 | yes | Hohe Straße 1 | Köln |
| typo_category_view | Apoteke | view | 200 | 89 | 94 | 91 | 62 | 1 | yes | Apotheke |
| typo_category_place | Apoteke Bielefeld | all | 200 | 69 | 75 | 84 | 61 | 1 | yes | Apotheke am Meilenstein | Gütersloher Straße 324 | Bielefeld |
| typo_category_place_kh | Krankenhauss Bochum | all | 200 | 63 | 61 | 62 | 13 | 1 | yes | Universitätsklinikum Knappschaftskrankenhaus Bochum | In der Schornau 23-25 | Bochum |
| typo_place_category | Apotheke Dortmnd | all | 200 | 63 | 65 | 62 | 110 | 1 | yes | Eichholz-Apotheke | Dortmund |
| typo_place_category_city | Bäckerei Düseldorf | all | 200 | 71 | 73 | 69 | 200 | 3 | yes | Unterbacher Backtreff | Gerresheimer Landstraße 76 | Düsseldorf |
| abbr_hbf | Köln Hbf | all | 200 | 49 | 49 | 49 | 1 | 1 | yes | Köln Hauptbahnhof | Trankgasse 11 | Köln |
| abbr_hbf_dot | Düsseldorf Hbf. | all | 200 | 45 | 49 | 43 | 7 | 1 | yes | Düsseldorf Hauptbahnhof |
| abbr_hbf_lower | essen hbf | all | 200 | 51 | 49 | 46 | 46 | 1 | yes | Essen Hauptbahnhof |
| abbr_hbf_typo | Dortmund Hbhf | all | 200 | 49 | 49 | 51 | 12 | 1 | yes | Dortmund Hauptbahnhof |
| abbr_bhf | Bhf Dortmund | all | 200 | 77 | 78 | 73 | 152 | 0 | **no** | Dortmund-Wickede |
| abbr_zob | ZOB Bonn | all | 200 | 48 | 49 | 47 | 1 | 1 | yes | Zentraler Omnibusbahnhof Bonn |
| abbr_zob_long | Zentraler Omnibusbahnhof Lünen | all | 200 | 185 | 190 | 188 | 89 | 1 | yes | ZOB Lünen |
| abbr_uni | Uni Köln | all | 200 | 62 | 66 | 67 | 78 | 0 | **no** | Universität |
| abbr_uni_bonn | Uni Bonn | all | 200 | 61 | 49 | 49 | 1 | 1 | yes | Universität Bonn | Friedrich-Ebert-Allee 144 | Bonn |
| abbr_rub | RUB | all | 200 | 108 | 105 | 109 | 200 | 0 | **no** | Rubinweg |
| abbr_tu | TU Dortmund | all | 200 | 49 | 49 | 54 | 1 | 1 | yes | Technische Universität Dortmund |
| abbr_th | TH Köln | all | 200 | 200 | 203 | 191 | 19 | 1 | **no** | TH Köln | Ubierring 40 | Köln |
| abbr_fh | FH Dortmund | all | 200 | 42 | 46 | 47 | 2 | 1 | yes | Fachhochschule Dortmund | Sonnenstraße 96 | Dortmund |
| abbr_uniklinik | Uniklinik Köln | all | 200 | 43 | 46 | 44 | 3 | 1 | yes | Universitätsklinikum Köln |
| abbr_ukm | UKM Münster | all | 200 | 55 | 51 | 50 | 1 | 0 | **no** | UKM |
| abbr_kh | KH Herne | all | 200 | 57 | 55 | 56 | 6 | 1 | yes | Evangelisches Krankenhaus Herne Mitte | Wiescherstraße 24 | Herne |
| abbr_kita_view | Kita | view | 200 | 77 | 78 | 75 | 210 | 1 | yes | Kindertagesstätte | Friesenstraße 28 | Köln |
| abbr_vhs | VHS Dortmund | all | 200 | 46 | 44 | 46 | 3 | 1 | yes | Volkshochschule Dortmund |
| abbr_vhs_long | Volkshochschule Warendorf | all | 200 | 65 | 68 | 63 | 2 | 2 | yes | Katholische Landvolkshochschule Schorlemer Alst | Am Hagen 1 | Warendorf |
| abbr_jh | JH Altena | all | 200 | 65 | 62 | 62 | 2 | 1 | yes | DJH Jugendherberge Altena, Burg | Fritz-Thomee-Straße 80 | Altena |
| abbr_ffw | FFW Herne | all | 200 | 209 | 206 | 204 | 8 | 1 | **no** | Freiwillige Feuerwehr Herne LZ Röhlinghausen | Plutostraße 4 | Herne |
| abbr_spk | Spk KölnBonn | all | 200 | 50 | 53 | 54 | 51 | 1 | yes | Sparkasse KölnBonn | Dellbrücker Hauptstraße 121 | Köln |
| abbr_st | St. Augustin | all | 200 | 47 | 47 | 49 | 8 | 1 | yes | Sankt Augustin |
| abbr_sankt | Sankt Tönis | all | 200 | 101 | 101 | 98 | 146 | 1 | yes | St. Tönis |
| abbr_koe | Kö Düsseldorf | all | 200 | 126 | 133 | 126 | 12 | 4 | yes | Kö12 |
| abbr_adr | Mülheim a.d. Ruhr | all | 200 | 52 | 50 | 56 | 2 | 1 | yes | Mülheim an der Ruhr |
| abbr_iata | Flughafen DUS | all | 200 | 126 | 127 | 121 | 79 | 6 | **no** | Flughafen |
| abbr_str_address | Hohe Str 1 Köln | all | 200 | 50 | 50 | 51 | 2 | 1 | yes | Hohe Straße 1 | Köln |

## Summary

- warm ms over all successful queries: min 43 / median 73 / max 206
- expected result at rank 1: 44 of 53; on the first page: 49 of 53
- target (rank 1-5, warm at most 200 ms) met: 46 of 53; rank alone: 48 of 53

<details><summary>Top 3 per query</summary>

- **typo_double_dropped** (Düseldorf): Düsseldorf ; Düsseldorf Airport ; Segelfluggelände Düsseldorf-Wolfsaap
- **typo_swap** (Dortmudn): Dortmund ; Dönaladn Dortmund
- **typo_drop_end** (Gelsenkirchn): Gelsenkirchen ; Gelsenkirchen Zoo ; Gelsenkirchen-Süd
- **typo_drop_inner** (Mönchengladbch): Mönchengladbach ; MGL Mönchengladbach Airport ; Flughafen Düsseldorf Mönchengladbach
- **typo_double_missing** (Wupertal): Wuppertal ; Zoo Wuppertal | Hubertusallee 30 | Wuppertal ; Wuppertal-Nord
- **typo_sound_d_t** (Bielefelt): Bielefeld ; Flugplatz Bielefeld | Am Flugplatz 1 | Bielefeld ; Bielefeld Ost | Am Ostbahnhof 1 | Bielefeld
- **typo_sound_d_t_end** (Lüdenscheit): Lüdenscheid ; Lüdenscheid ; Lüdenscheid
- **typo_drop_e** (Recklinghausn): Recklinghausen ; Recklinghausen ; Recklingsen
- **umlaut_ue** (Muelheim an der Ruhr): Mülheim an der Ruhr ; Mülheim an der Ruhr
- **umlaut_dropped** (Gutersloh): Gütersloh ; Gütersloh ; Gütersloh
- **umlaut_dropped_short** (Koln): Köln ; Flughafen Köln/Bonn | Heinrich-Steinmann-Straße 12 | Köln ; Flughafen Köln/Bonn Militärischer Teil
- **typo_no_space** (badoeynhausen): Bad Oeynhausen ; Bad Oeynhausen-Ost ; Bad Oeynhausen-Ost
- **typo_landmark_h** (Kölner Dohm): Dohm ; Dohm ; Dohm
- **typo_landmark_n** (Hermansdenkmal): Hermannsdenkmal ; Waldbühne am Hermannsdenkmal | Grotenburg 50 | Detmold ; Hermannsdenkmal
- **typo_landmark_sound** (Phantasieland): Phantasialand | Berggeiststraße 31-41 | Brühl ; Phantasialand ; Phantasialand Appartement
- **typo_landmark_f_v** (Zollferein): Zollverein ; Zollverein ; pact zollverein | Bullmannaue 20a | Essen
- **typo_long_name** (Technische Universitat Dortmund): Technische Universität Dortmund ; Universität | Vogelpothsweg | Dortmund
- **typo_street** (Königsalee Düsseldorf): Königsallee ; Königsallee ; Ausgang Königsallee
- **typo_street_place** (Schildergase Köln): Höhe Straße, Schildergasse ; Schildergasse ; Filmhaus Schildergasse | Schildergasse 98-100 | Köln
- **typo_street_address** (Hohe Strase 1 Köln): Hohe Straße 1 | Köln ; Hohe Straße 1 | Köln
- **typo_category_view** (Apoteke): Apotheke ; Goten-Apotheke | Deutzer Freiheit 114 | Köln ; Kosmas-Apotheke | Apostelnstraße 10 | Köln
- **typo_category_place** (Apoteke Bielefeld): Apotheke am Meilenstein | Gütersloher Straße 324 | Bielefeld ; Apotheke in Eckardtsheim | Verler Straße 210 | Bielefeld ; Apotheke am Marktplatz | Windelsbleicher Straße 235 | Bielefeld
- **typo_category_place_kh** (Krankenhauss Bochum): Universitätsklinikum Knappschaftskrankenhaus Bochum | In der Schornau 23-25 | Bochum ; St. Maria-Hilf-Krankenhaus ; Hospiz St. Hildegard | Königsallee 135 | Bochum
- **typo_place_category** (Apotheke Dortmnd): Eichholz-Apotheke | Dortmund ; Merkur Apotheke | Jasminstraße 5 ; Heide-Apotheke | Heideweg 14 | Dortmund
- **typo_place_category_city** (Bäckerei Düseldorf): Unterbacher Backtreff | Gerresheimer Landstraße 76 | Düsseldorf ; Oehme | Blanckertzstraße 2 | Düsseldorf ; Bäckerei Behmer | Gerresheimer Landstraße 110
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
- **abbr_vhs_long** (Volkshochschule Warendorf): Katholische Landvolkshochschule Schorlemer Alst | Am Hagen 1 | Warendorf ; VHS Warendorf / Baudezernat | Freckenhorster Straße 43 | Warendorf
- **abbr_jh** (JH Altena): DJH Jugendherberge Altena, Burg | Fritz-Thomee-Straße 80 | Altena ; Pfadfinderheim Jung-Stilling | Horst 4 | Altena
- **abbr_ffw** (FFW Herne): Freiwillige Feuerwehr Herne LZ Röhlinghausen | Plutostraße 4 | Herne ; Freiwillige Feuerwehr Herne-Sodingen, Gerätehaus Ost | Bogenweg 1 | Herne ; Freiwillige Feuerwehr Herrath | Herrather Linde 92 | Mönchengladbach
- **abbr_spk** (Spk KölnBonn): Sparkasse KölnBonn | Dellbrücker Hauptstraße 121 | Köln ; Sparkasse KölnBonn | Köln ; Sparkasse KölnBonn
- **abbr_st** (St. Augustin): Sankt Augustin ; Sankt Augustin ; Sankt Augustin
- **abbr_sankt** (Sankt Tönis): St. Tönis ; St. Tönis ; St. Tönis
- **abbr_koe** (Kö Düsseldorf): Kö12 ; Kö 21 ; Ko
- **abbr_adr** (Mülheim a.d. Ruhr): Mülheim an der Ruhr ; Mülheim an der Ruhr
- **abbr_iata** (Flughafen DUS): Flughafen ; Flughafen ; Flughafen
- **abbr_str_address** (Hohe Str 1 Köln): Hohe Straße 1 | Köln ; Hohe Straße 1 | Köln

</details>
