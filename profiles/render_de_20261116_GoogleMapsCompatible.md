# Render profile -- 2026-11-16 14:10 UTC

- server http://127.0.0.1:8000, styles `/data/styles/de_20261116_020109/GoogleMapsCompatible`, mapnik 4.3.2, PostgreSQL 17.5 (Debian 17.5-1.pgdg110+1)
- postgres: effective_cache_size=10GB, jit=off, max_parallel_workers_per_gather=4, random_page_cost=4, shared_buffers=4GB, work_mem=64MB
- hardware: AMD EPYC-Rome Processor x 8, 15.2 GB RAM, linux 5.15.0-202-generic x86_64 (geoservices server, production stack under live traffic)
- tile box (lon/lat, inner half of the data extent): 8.160 49.242 -- 12.748 53.220, seed 42, up to 5 tiles with buildings per zoom
- themes: atkis_max, atkis_min, atkis_nav, atkis_std, atkis_topographic, atkis_vegetation, dark_max, dark_min, dark_nav, dark_std, dark_topographic, dark_vegetation, default_max, default_min, default_nav, default_std, default_topographic, default_vegetation, flora_max, flora_min, flora_nav, flora_std, flora_topographic, flora_vegetation, grayscale_max, grayscale_min, grayscale_nav, grayscale_std, grayscale_topographic, grayscale_vegetation, hico_max, hico_min, hico_nav, hico_std, hico_topographic, hico_vegetation, light_max, light_min, light_nav, light_std, light_topographic, light_vegetation, sepia_max, sepia_min, sepia_nav, sepia_std, sepia_topographic, sepia_vegetation
- crs: EPSG:3857 (GoogleMapsCompatible)

## 1. HTTP: uncached render vs cache hit

Render ms are min / median / max over all themes and tiles at that zoom; hit ms and KB are medians. For a non-3857 CRS "zoom" is the 3857 zoom the tile was picked for; the level actually requested is the closest scale of that TileMatrixSet (in parentheses). The picks are distinct tiles of that grid; where the box holds fewer tiles with buildings at a level, `tiles` is smaller. The first render after a cache clear is consistently slow, so unreported warm-up tiles per CRS are fetched first.

### EPSG:3857

| zoom | level | tiles | render ms | hit ms | KB |
|---|---|---|---|---|---|
| 8 | 8 | 240 | 85 / 208 / 5827 | 8.3 | 41 |
| 10 | 10 | 240 | 102 / 197 / 969 | 8.4 | 32 |
| 12 | 12 | 240 | 34 / 71 / 169 | 8.9 | 18 |
| 13 | 13 | 240 | 29 / 60 / 567 | 9.0 | 10 |
| 14 | 14 | 240 | 21 / 53 / 352 | 9.2 | 7 |
| 16 | 16 | 240 | 28 / 53 / 229 | 9.2 | 8 |
| 18 | 18 | 240 | 26 / 49 / 163 | 9.1 | 2 |

| theme | crs | tiles | render ms | z<=12 render ms | z>12 render ms |
|---|---|---|---|---|---|
| atkis_max | EPSG:3857 | 35 | 100 / 215 / 1932 | 100 / 578 / 1932 | 131 / 180 / 567 |
| atkis_min | EPSG:3857 | 35 | 29 / 48 / 5827 | 47 / 110 / 5827 | 29 / 43 / 77 |
| atkis_nav | EPSG:3857 | 35 | 38 / 57 / 277 | 45 / 138 / 277 | 38 / 51 / 84 |
| atkis_std | EPSG:3857 | 35 | 56 / 74 / 472 | 59 / 214 / 472 | 56 / 62 / 103 |
| atkis_topographic | EPSG:3857 | 35 | 51 / 79 / 356 | 66 / 212 / 356 | 51 / 68 / 97 |
| atkis_vegetation | EPSG:3857 | 35 | 37 / 63 / 362 | 63 / 196 / 362 | 37 / 51 / 97 |
| dark_max | EPSG:3857 | 35 | 51 / 68 / 402 | 51 / 191 / 402 | 53 / 64 / 82 |
| dark_min | EPSG:3857 | 35 | 21 / 36 / 269 | 35 / 102 / 269 | 21 / 29 / 41 |
| dark_nav | EPSG:3857 | 35 | 26 / 43 / 284 | 35 / 125 / 284 | 26 / 34 / 51 |
| dark_std | EPSG:3857 | 35 | 41 / 51 / 379 | 51 / 161 / 379 | 41 / 46 / 78 |
| dark_topographic | EPSG:3857 | 35 | 47 / 60 / 320 | 51 / 187 / 320 | 47 / 54 / 71 |
| dark_vegetation | EPSG:3857 | 35 | 45 / 60 / 397 | 49 / 205 / 397 | 45 / 54 / 74 |
| default_max | EPSG:3857 | 35 | 61 / 84 / 441 | 77 / 218 / 441 | 61 / 77 / 119 |
| default_min | EPSG:3857 | 35 | 29 / 43 / 283 | 40 / 98 / 283 | 29 / 38 / 59 |
| default_nav | EPSG:3857 | 35 | 30 / 43 / 309 | 39 / 120 / 309 | 30 / 37 / 52 |
| default_std | EPSG:3857 | 35 | 41 / 61 / 373 | 50 / 197 / 373 | 41 / 50 / 85 |
| default_topographic | EPSG:3857 | 35 | 45 / 65 / 337 | 64 / 169 / 337 | 45 / 58 / 88 |
| default_vegetation | EPSG:3857 | 35 | 42 / 56 / 349 | 61 / 184 / 349 | 42 / 49 / 82 |
| flora_max | EPSG:3857 | 35 | 63 / 84 / 416 | 67 / 218 / 416 | 63 / 76 / 123 |
| flora_min | EPSG:3857 | 35 | 35 / 48 / 284 | 45 / 117 / 284 | 35 / 42 / 66 |
| flora_nav | EPSG:3857 | 35 | 35 / 54 / 286 | 46 / 127 / 286 | 35 / 47 / 69 |
| flora_std | EPSG:3857 | 35 | 52 / 69 / 431 | 63 / 220 / 431 | 52 / 61 / 103 |
| flora_topographic | EPSG:3857 | 35 | 46 / 61 / 337 | 53 / 173 / 337 | 46 / 55 / 73 |
| flora_vegetation | EPSG:3857 | 35 | 30 / 61 / 386 | 56 / 187 / 386 | 30 / 50 / 85 |
| grayscale_max | EPSG:3857 | 35 | 48 / 63 / 358 | 61 / 168 / 358 | 48 / 59 / 82 |
| grayscale_min | EPSG:3857 | 35 | 31 / 41 / 259 | 34 / 92 / 259 | 31 / 36 / 48 |
| grayscale_nav | EPSG:3857 | 35 | 36 / 56 / 334 | 43 / 144 / 334 | 36 / 45 / 70 |
| grayscale_std | EPSG:3857 | 35 | 50 / 69 / 409 | 63 / 217 / 409 | 50 / 59 / 93 |
| grayscale_topographic | EPSG:3857 | 35 | 58 / 76 / 335 | 60 / 185 / 335 | 58 / 65 / 93 |
| grayscale_vegetation | EPSG:3857 | 35 | 41 / 61 / 378 | 56 / 195 / 378 | 41 / 49 / 75 |
| hico_max | EPSG:3857 | 35 | 56 / 83 / 430 | 68 / 209 / 430 | 56 / 80 / 110 |
| hico_min | EPSG:3857 | 35 | 27 / 48 / 251 | 45 / 115 / 251 | 27 / 42 / 63 |
| hico_nav | EPSG:3857 | 35 | 41 / 57 / 287 | 41 / 128 / 287 | 42 / 52 / 78 |
| hico_std | EPSG:3857 | 35 | 41 / 57 / 414 | 48 / 208 / 414 | 41 / 49 / 81 |
| hico_topographic | EPSG:3857 | 35 | 60 / 77 / 328 | 63 / 194 / 328 | 60 / 71 / 93 |
| hico_vegetation | EPSG:3857 | 35 | 42 / 54 / 385 | 49 / 173 / 385 | 42 / 48 / 72 |
| light_max | EPSG:3857 | 35 | 59 / 81 / 427 | 59 / 203 / 427 | 60 / 75 / 111 |
| light_min | EPSG:3857 | 35 | 33 / 50 / 253 | 43 / 109 / 253 | 33 / 44 / 63 |
| light_nav | EPSG:3857 | 35 | 27 / 45 / 318 | 42 / 142 / 318 | 27 / 38 / 64 |
| light_std | EPSG:3857 | 35 | 51 / 67 / 406 | 62 / 208 / 406 | 51 / 61 / 91 |
| light_topographic | EPSG:3857 | 35 | 53 / 78 / 333 | 64 / 195 / 333 | 53 / 67 / 93 |
| light_vegetation | EPSG:3857 | 35 | 38 / 62 / 414 | 57 / 216 / 414 | 38 / 49 / 78 |
| sepia_max | EPSG:3857 | 35 | 61 / 83 / 403 | 81 / 206 / 403 | 61 / 77 / 102 |
| sepia_min | EPSG:3857 | 35 | 32 / 53 / 260 | 48 / 109 / 260 | 32 / 45 / 56 |
| sepia_nav | EPSG:3857 | 35 | 37 / 55 / 297 | 46 / 141 / 297 | 37 / 48 / 70 |
| sepia_std | EPSG:3857 | 35 | 48 / 74 / 434 | 58 / 206 / 434 | 48 / 64 / 108 |
| sepia_topographic | EPSG:3857 | 35 | 47 / 73 / 354 | 62 / 191 / 354 | 47 / 65 / 95 |
| sepia_vegetation | EPSG:3857 | 35 | 39 / 65 / 384 | 65 / 204 / 384 | 39 / 50 / 90 |

Total render time for the 1680 tiles: 185.9 s.

<details><summary>Every tile</summary>

| theme | crs | zoom | level | col | row | render ms | hit ms | KB |
|---|---|---|---|---|---|---|---|---|
| atkis_max | EPSG:3857 | 8 | 8 | 135 | 87 | 1416 | 10.9 | 43.4 |
| atkis_max | EPSG:3857 | 8 | 8 | 134 | 86 | 1106 | 8.6 | 43.5 |
| atkis_max | EPSG:3857 | 8 | 8 | 136 | 84 | 1932 | 9.2 | 41.5 |
| atkis_max | EPSG:3857 | 8 | 8 | 136 | 87 | 749 | 8.2 | 43.4 |
| atkis_max | EPSG:3857 | 8 | 8 | 134 | 85 | 870 | 8.5 | 41.3 |
| atkis_max | EPSG:3857 | 10 | 10 | 535 | 347 | 584 | 8.9 | 36.2 |
| atkis_max | EPSG:3857 | 10 | 10 | 543 | 340 | 405 | 8.9 | 30.5 |
| atkis_max | EPSG:3857 | 10 | 10 | 538 | 340 | 578 | 8.9 | 34.3 |
| atkis_max | EPSG:3857 | 10 | 10 | 545 | 350 | 334 | 8.6 | 36.8 |
| atkis_max | EPSG:3857 | 10 | 10 | 545 | 338 | 969 | 11.5 | 32.0 |
| atkis_max | EPSG:3857 | 12 | 12 | 2158 | 1391 | 118 | 10.3 | 26.3 |
| atkis_max | EPSG:3857 | 12 | 12 | 2190 | 1378 | 134 | 10.7 | 31.8 |
| atkis_max | EPSG:3857 | 12 | 12 | 2145 | 1395 | 169 | 10.2 | 24.7 |
| atkis_max | EPSG:3857 | 12 | 12 | 2185 | 1359 | 100 | 10.2 | 22.7 |
| atkis_max | EPSG:3857 | 12 | 12 | 2182 | 1350 | 110 | 9.7 | 14.3 |
| atkis_max | EPSG:3857 | 13 | 13 | 4337 | 2664 | 292 | 10.7 | 14.1 |
| atkis_max | EPSG:3857 | 13 | 13 | 4321 | 2726 | 567 | 10.2 | 21.6 |
| atkis_max | EPSG:3857 | 13 | 13 | 4368 | 2716 | 195 | 10.6 | 9.9 |
| atkis_max | EPSG:3857 | 13 | 13 | 4371 | 2722 | 246 | 12.4 | 15.6 |
| atkis_max | EPSG:3857 | 13 | 13 | 4355 | 2798 | 294 | 9.0 | 26.6 |
| atkis_max | EPSG:3857 | 14 | 14 | 8610 | 5528 | 214 | 8.7 | 14.5 |
| atkis_max | EPSG:3857 | 14 | 14 | 8580 | 5544 | 352 | 9.3 | 26.7 |
| atkis_max | EPSG:3857 | 14 | 14 | 8584 | 5531 | 140 | 8.9 | 12.7 |
| atkis_max | EPSG:3857 | 14 | 14 | 8640 | 5551 | 144 | 9.1 | 12.4 |
| atkis_max | EPSG:3857 | 14 | 14 | 8619 | 5339 | 131 | 8.9 | 13.0 |
| atkis_max | EPSG:3857 | 16 | 16 | 34794 | 21746 | 164 | 9.5 | 10.3 |
| atkis_max | EPSG:3857 | 16 | 16 | 34396 | 21605 | 165 | 14.0 | 8.1 |
| atkis_max | EPSG:3857 | 16 | 16 | 34718 | 21657 | 225 | 14.3 | 17.7 |
| atkis_max | EPSG:3857 | 16 | 16 | 34429 | 21350 | 215 | 11.0 | 12.7 |
| atkis_max | EPSG:3857 | 16 | 16 | 34985 | 22085 | 229 | 9.7 | 20.0 |
| atkis_max | EPSG:3857 | 18 | 18 | 137317 | 89546 | 133 | 10.4 | 2.0 |
| atkis_max | EPSG:3857 | 18 | 18 | 137380 | 86898 | 149 | 13.2 | 7.5 |
| atkis_max | EPSG:3857 | 18 | 18 | 140341 | 87356 | 141 | 12.7 | 2.6 |
| atkis_max | EPSG:3857 | 18 | 18 | 137052 | 86460 | 163 | 11.0 | 10.3 |
| atkis_max | EPSG:3857 | 18 | 18 | 137079 | 85468 | 135 | 10.5 | 8.8 |
| atkis_min | EPSG:3857 | 8 | 8 | 135 | 87 | 152 | 9.8 | 22.4 |
| atkis_min | EPSG:3857 | 8 | 8 | 134 | 86 | 5827 | 9.3 | 26.1 |
| atkis_min | EPSG:3857 | 8 | 8 | 136 | 84 | 99 | 9.4 | 20.7 |
| atkis_min | EPSG:3857 | 8 | 8 | 136 | 87 | 101 | 9.4 | 19.8 |
| atkis_min | EPSG:3857 | 8 | 8 | 134 | 85 | 110 | 7.8 | 23.2 |
| atkis_min | EPSG:3857 | 10 | 10 | 535 | 347 | 286 | 8.0 | 27.2 |
| atkis_min | EPSG:3857 | 10 | 10 | 543 | 340 | 125 | 8.6 | 17.1 |
| atkis_min | EPSG:3857 | 10 | 10 | 538 | 340 | 175 | 7.5 | 22.9 |
| atkis_min | EPSG:3857 | 10 | 10 | 545 | 350 | 115 | 8.0 | 17.8 |
| atkis_min | EPSG:3857 | 10 | 10 | 545 | 338 | 131 | 7.9 | 21.7 |
| atkis_min | EPSG:3857 | 12 | 12 | 2158 | 1391 | 47 | 9.6 | 8.2 |
| atkis_min | EPSG:3857 | 12 | 12 | 2190 | 1378 | 59 | 8.7 | 16.8 |
| atkis_min | EPSG:3857 | 12 | 12 | 2145 | 1395 | 96 | 11.2 | 15.4 |
| atkis_min | EPSG:3857 | 12 | 12 | 2185 | 1359 | 62 | 8.1 | 14.2 |
| atkis_min | EPSG:3857 | 12 | 12 | 2182 | 1350 | 47 | 8.0 | 7.8 |
| atkis_min | EPSG:3857 | 13 | 13 | 4337 | 2664 | 43 | 12.0 | 5.1 |
| atkis_min | EPSG:3857 | 13 | 13 | 4321 | 2726 | 77 | 9.2 | 10.3 |
| atkis_min | EPSG:3857 | 13 | 13 | 4368 | 2716 | 38 | 8.8 | 5.5 |
| atkis_min | EPSG:3857 | 13 | 13 | 4371 | 2722 | 58 | 9.9 | 7.6 |
| atkis_min | EPSG:3857 | 13 | 13 | 4355 | 2798 | 50 | 8.8 | 10.0 |
| atkis_min | EPSG:3857 | 14 | 14 | 8610 | 5528 | 41 | 10.6 | 4.8 |
| atkis_min | EPSG:3857 | 14 | 14 | 8580 | 5544 | 48 | 14.1 | 8.1 |
| atkis_min | EPSG:3857 | 14 | 14 | 8584 | 5531 | 39 | 8.2 | 0.3 |
| atkis_min | EPSG:3857 | 14 | 14 | 8640 | 5551 | 29 | 8.6 | 0.1 |
| atkis_min | EPSG:3857 | 14 | 14 | 8619 | 5339 | 40 | 9.5 | 4.9 |
| atkis_min | EPSG:3857 | 16 | 16 | 34794 | 21746 | 44 | 10.3 | 4.1 |
| atkis_min | EPSG:3857 | 16 | 16 | 34396 | 21605 | 43 | 9.9 | 5.2 |
| atkis_min | EPSG:3857 | 16 | 16 | 34718 | 21657 | 51 | 14.4 | 10.0 |
| atkis_min | EPSG:3857 | 16 | 16 | 34429 | 21350 | 46 | 8.7 | 6.3 |
| atkis_min | EPSG:3857 | 16 | 16 | 34985 | 22085 | 47 | 9.3 | 9.8 |
| atkis_min | EPSG:3857 | 18 | 18 | 137317 | 89546 | 37 | 10.2 | 0.1 |
| atkis_min | EPSG:3857 | 18 | 18 | 137380 | 86898 | 40 | 9.3 | 2.6 |
| atkis_min | EPSG:3857 | 18 | 18 | 140341 | 87356 | 44 | 11.3 | 0.3 |
| atkis_min | EPSG:3857 | 18 | 18 | 137052 | 86460 | 43 | 9.1 | 3.3 |
| atkis_min | EPSG:3857 | 18 | 18 | 137079 | 85468 | 47 | 11.5 | 4.9 |
| atkis_nav | EPSG:3857 | 8 | 8 | 135 | 87 | 251 | 7.8 | 24.2 |
| atkis_nav | EPSG:3857 | 8 | 8 | 134 | 86 | 167 | 8.7 | 28.2 |
| atkis_nav | EPSG:3857 | 8 | 8 | 136 | 84 | 144 | 8.7 | 23.8 |
| atkis_nav | EPSG:3857 | 8 | 8 | 136 | 87 | 142 | 19.8 | 21.0 |
| atkis_nav | EPSG:3857 | 8 | 8 | 134 | 85 | 135 | 7.7 | 24.4 |
| atkis_nav | EPSG:3857 | 10 | 10 | 535 | 347 | 277 | 10.3 | 29.0 |
| atkis_nav | EPSG:3857 | 10 | 10 | 543 | 340 | 133 | 7.8 | 17.6 |
| atkis_nav | EPSG:3857 | 10 | 10 | 538 | 340 | 175 | 8.6 | 23.3 |
| atkis_nav | EPSG:3857 | 10 | 10 | 545 | 350 | 138 | 8.5 | 18.0 |
| atkis_nav | EPSG:3857 | 10 | 10 | 545 | 338 | 163 | 9.5 | 23.4 |
| atkis_nav | EPSG:3857 | 12 | 12 | 2158 | 1391 | 45 | 8.3 | 8.3 |
| atkis_nav | EPSG:3857 | 12 | 12 | 2190 | 1378 | 60 | 10.4 | 16.8 |
| atkis_nav | EPSG:3857 | 12 | 12 | 2145 | 1395 | 95 | 8.9 | 15.7 |
| atkis_nav | EPSG:3857 | 12 | 12 | 2185 | 1359 | 60 | 9.3 | 14.7 |
| atkis_nav | EPSG:3857 | 12 | 12 | 2182 | 1350 | 46 | 10.1 | 8.3 |
| atkis_nav | EPSG:3857 | 13 | 13 | 4337 | 2664 | 52 | 12.1 | 5.2 |
| atkis_nav | EPSG:3857 | 13 | 13 | 4321 | 2726 | 84 | 10.0 | 11.5 |
| atkis_nav | EPSG:3857 | 13 | 13 | 4368 | 2716 | 47 | 9.1 | 6.1 |
| atkis_nav | EPSG:3857 | 13 | 13 | 4371 | 2722 | 52 | 10.0 | 8.9 |
| atkis_nav | EPSG:3857 | 13 | 13 | 4355 | 2798 | 57 | 10.7 | 10.3 |
| atkis_nav | EPSG:3857 | 14 | 14 | 8610 | 5528 | 51 | 10.6 | 5.4 |
| atkis_nav | EPSG:3857 | 14 | 14 | 8580 | 5544 | 64 | 9.2 | 15.9 |
| atkis_nav | EPSG:3857 | 14 | 14 | 8584 | 5531 | 42 | 10.2 | 0.3 |
| atkis_nav | EPSG:3857 | 14 | 14 | 8640 | 5551 | 38 | 10.7 | 0.1 |
| atkis_nav | EPSG:3857 | 14 | 14 | 8619 | 5339 | 46 | 9.9 | 6.2 |
| atkis_nav | EPSG:3857 | 16 | 16 | 34794 | 21746 | 50 | 9.5 | 4.9 |
| atkis_nav | EPSG:3857 | 16 | 16 | 34396 | 21605 | 53 | 10.1 | 5.7 |
| atkis_nav | EPSG:3857 | 16 | 16 | 34718 | 21657 | 59 | 9.4 | 17.4 |
| atkis_nav | EPSG:3857 | 16 | 16 | 34429 | 21350 | 52 | 13.3 | 10.5 |
| atkis_nav | EPSG:3857 | 16 | 16 | 34985 | 22085 | 68 | 9.1 | 20.4 |
| atkis_nav | EPSG:3857 | 18 | 18 | 137317 | 89546 | 50 | 10.2 | 1.3 |
| atkis_nav | EPSG:3857 | 18 | 18 | 137380 | 86898 | 51 | 9.3 | 4.8 |
| atkis_nav | EPSG:3857 | 18 | 18 | 140341 | 87356 | 48 | 8.6 | 0.9 |
| atkis_nav | EPSG:3857 | 18 | 18 | 137052 | 86460 | 53 | 10.6 | 8.2 |
| atkis_nav | EPSG:3857 | 18 | 18 | 137079 | 85468 | 49 | 8.9 | 8.9 |
| atkis_std | EPSG:3857 | 8 | 8 | 135 | 87 | 258 | 8.6 | 43.4 |
| atkis_std | EPSG:3857 | 8 | 8 | 134 | 86 | 288 | 8.3 | 43.5 |
| atkis_std | EPSG:3857 | 8 | 8 | 136 | 84 | 271 | 7.7 | 41.5 |
| atkis_std | EPSG:3857 | 8 | 8 | 136 | 87 | 214 | 8.6 | 43.4 |
| atkis_std | EPSG:3857 | 8 | 8 | 134 | 85 | 232 | 8.4 | 41.3 |
| atkis_std | EPSG:3857 | 10 | 10 | 535 | 347 | 472 | 35.6 | 36.2 |
| atkis_std | EPSG:3857 | 10 | 10 | 543 | 340 | 230 | 9.1 | 32.0 |
| atkis_std | EPSG:3857 | 10 | 10 | 538 | 340 | 268 | 12.3 | 34.3 |
| atkis_std | EPSG:3857 | 10 | 10 | 545 | 350 | 201 | 11.9 | 33.0 |
| atkis_std | EPSG:3857 | 10 | 10 | 545 | 338 | 203 | 7.4 | 32.0 |
| atkis_std | EPSG:3857 | 12 | 12 | 2158 | 1391 | 69 | 9.9 | 20.4 |
| atkis_std | EPSG:3857 | 12 | 12 | 2190 | 1378 | 99 | 9.3 | 29.3 |
| atkis_std | EPSG:3857 | 12 | 12 | 2145 | 1395 | 126 | 9.3 | 21.0 |
| atkis_std | EPSG:3857 | 12 | 12 | 2185 | 1359 | 72 | 9.2 | 22.6 |
| atkis_std | EPSG:3857 | 12 | 12 | 2182 | 1350 | 59 | 8.8 | 14.3 |
| atkis_std | EPSG:3857 | 13 | 13 | 4337 | 2664 | 59 | 11.1 | 14.1 |
| atkis_std | EPSG:3857 | 13 | 13 | 4321 | 2726 | 103 | 12.3 | 20.3 |
| atkis_std | EPSG:3857 | 13 | 13 | 4368 | 2716 | 59 | 10.0 | 9.6 |
| atkis_std | EPSG:3857 | 13 | 13 | 4371 | 2722 | 70 | 9.9 | 13.8 |
| atkis_std | EPSG:3857 | 13 | 13 | 4355 | 2798 | 82 | 8.5 | 22.4 |
| atkis_std | EPSG:3857 | 14 | 14 | 8610 | 5528 | 57 | 9.4 | 13.1 |
| atkis_std | EPSG:3857 | 14 | 14 | 8580 | 5544 | 89 | 8.6 | 26.5 |
| atkis_std | EPSG:3857 | 14 | 14 | 8584 | 5531 | 74 | 11.1 | 11.0 |
| atkis_std | EPSG:3857 | 14 | 14 | 8640 | 5551 | 63 | 9.4 | 10.3 |
| atkis_std | EPSG:3857 | 14 | 14 | 8619 | 5339 | 59 | 10.2 | 11.1 |
| atkis_std | EPSG:3857 | 16 | 16 | 34794 | 21746 | 56 | 8.1 | 8.8 |
| atkis_std | EPSG:3857 | 16 | 16 | 34396 | 21605 | 63 | 9.6 | 7.9 |
| atkis_std | EPSG:3857 | 16 | 16 | 34718 | 21657 | 85 | 11.2 | 17.7 |
| atkis_std | EPSG:3857 | 16 | 16 | 34429 | 21350 | 67 | 13.9 | 12.7 |
| atkis_std | EPSG:3857 | 16 | 16 | 34985 | 22085 | 81 | 10.7 | 20.0 |
| atkis_std | EPSG:3857 | 18 | 18 | 137317 | 89546 | 61 | 9.3 | 2.0 |
| atkis_std | EPSG:3857 | 18 | 18 | 137380 | 86898 | 59 | 10.8 | 5.2 |
| atkis_std | EPSG:3857 | 18 | 18 | 140341 | 87356 | 58 | 8.2 | 2.6 |
| atkis_std | EPSG:3857 | 18 | 18 | 137052 | 86460 | 59 | 8.8 | 10.3 |
| atkis_std | EPSG:3857 | 18 | 18 | 137079 | 85468 | 58 | 9.2 | 8.8 |
| atkis_topographic | EPSG:3857 | 8 | 8 | 135 | 87 | 232 | 8.2 | 41.7 |
| atkis_topographic | EPSG:3857 | 8 | 8 | 134 | 86 | 212 | 8.5 | 41.5 |
| atkis_topographic | EPSG:3857 | 8 | 8 | 136 | 84 | 243 | 12.1 | 40.4 |
| atkis_topographic | EPSG:3857 | 8 | 8 | 136 | 87 | 204 | 8.0 | 41.7 |
| atkis_topographic | EPSG:3857 | 8 | 8 | 134 | 85 | 227 | 8.9 | 41.4 |
| atkis_topographic | EPSG:3857 | 10 | 10 | 535 | 347 | 356 | 10.0 | 34.3 |
| atkis_topographic | EPSG:3857 | 10 | 10 | 543 | 340 | 233 | 8.0 | 29.8 |
| atkis_topographic | EPSG:3857 | 10 | 10 | 538 | 340 | 217 | 9.1 | 34.6 |
| atkis_topographic | EPSG:3857 | 10 | 10 | 545 | 350 | 200 | 12.4 | 36.4 |
| atkis_topographic | EPSG:3857 | 10 | 10 | 545 | 338 | 223 | 12.1 | 32.1 |
| atkis_topographic | EPSG:3857 | 12 | 12 | 2158 | 1391 | 88 | 10.5 | 25.8 |
| atkis_topographic | EPSG:3857 | 12 | 12 | 2190 | 1378 | 96 | 7.5 | 29.3 |
| atkis_topographic | EPSG:3857 | 12 | 12 | 2145 | 1395 | 145 | 9.4 | 24.4 |
| atkis_topographic | EPSG:3857 | 12 | 12 | 2185 | 1359 | 76 | 7.8 | 22.3 |
| atkis_topographic | EPSG:3857 | 12 | 12 | 2182 | 1350 | 66 | 9.1 | 13.7 |
| atkis_topographic | EPSG:3857 | 13 | 13 | 4337 | 2664 | 77 | 9.5 | 9.0 |
| atkis_topographic | EPSG:3857 | 13 | 13 | 4321 | 2726 | 97 | 9.0 | 20.0 |
| atkis_topographic | EPSG:3857 | 13 | 13 | 4368 | 2716 | 63 | 9.0 | 8.7 |
| atkis_topographic | EPSG:3857 | 13 | 13 | 4371 | 2722 | 78 | 8.9 | 14.5 |
| atkis_topographic | EPSG:3857 | 13 | 13 | 4355 | 2798 | 84 | 8.7 | 21.2 |
| atkis_topographic | EPSG:3857 | 14 | 14 | 8610 | 5528 | 72 | 10.0 | 9.6 |
| atkis_topographic | EPSG:3857 | 14 | 14 | 8580 | 5544 | 96 | 10.2 | 23.7 |
| atkis_topographic | EPSG:3857 | 14 | 14 | 8584 | 5531 | 66 | 10.9 | 5.7 |
| atkis_topographic | EPSG:3857 | 14 | 14 | 8640 | 5551 | 71 | 9.4 | 8.7 |
| atkis_topographic | EPSG:3857 | 14 | 14 | 8619 | 5339 | 60 | 9.7 | 11.7 |
| atkis_topographic | EPSG:3857 | 16 | 16 | 34794 | 21746 | 66 | 10.1 | 7.1 |
| atkis_topographic | EPSG:3857 | 16 | 16 | 34396 | 21605 | 59 | 8.5 | 7.9 |
| atkis_topographic | EPSG:3857 | 16 | 16 | 34718 | 21657 | 83 | 8.3 | 17.4 |
| atkis_topographic | EPSG:3857 | 16 | 16 | 34429 | 21350 | 79 | 8.5 | 11.9 |
| atkis_topographic | EPSG:3857 | 16 | 16 | 34985 | 22085 | 73 | 9.6 | 20.0 |
| atkis_topographic | EPSG:3857 | 18 | 18 | 137317 | 89546 | 57 | 8.9 | 1.2 |
| atkis_topographic | EPSG:3857 | 18 | 18 | 137380 | 86898 | 63 | 10.8 | 7.4 |
| atkis_topographic | EPSG:3857 | 18 | 18 | 140341 | 87356 | 60 | 7.4 | 1.9 |
| atkis_topographic | EPSG:3857 | 18 | 18 | 137052 | 86460 | 51 | 8.2 | 8.5 |
| atkis_topographic | EPSG:3857 | 18 | 18 | 137079 | 85468 | 60 | 9.6 | 8.8 |
| atkis_vegetation | EPSG:3857 | 8 | 8 | 135 | 87 | 209 | 7.8 | 41.6 |
| atkis_vegetation | EPSG:3857 | 8 | 8 | 134 | 86 | 271 | 8.2 | 41.5 |
| atkis_vegetation | EPSG:3857 | 8 | 8 | 136 | 84 | 249 | 7.2 | 40.4 |
| atkis_vegetation | EPSG:3857 | 8 | 8 | 136 | 87 | 176 | 7.7 | 41.7 |
| atkis_vegetation | EPSG:3857 | 8 | 8 | 134 | 85 | 218 | 7.0 | 41.3 |
| atkis_vegetation | EPSG:3857 | 10 | 10 | 535 | 347 | 362 | 6.7 | 35.3 |
| atkis_vegetation | EPSG:3857 | 10 | 10 | 543 | 340 | 196 | 8.6 | 31.1 |
| atkis_vegetation | EPSG:3857 | 10 | 10 | 538 | 340 | 228 | 8.6 | 34.2 |
| atkis_vegetation | EPSG:3857 | 10 | 10 | 545 | 350 | 174 | 8.2 | 33.2 |
| atkis_vegetation | EPSG:3857 | 10 | 10 | 545 | 338 | 204 | 8.3 | 32.0 |
| atkis_vegetation | EPSG:3857 | 12 | 12 | 2158 | 1391 | 70 | 8.6 | 17.9 |
| atkis_vegetation | EPSG:3857 | 12 | 12 | 2190 | 1378 | 94 | 12.9 | 26.9 |
| atkis_vegetation | EPSG:3857 | 12 | 12 | 2145 | 1395 | 130 | 12.5 | 17.3 |
| atkis_vegetation | EPSG:3857 | 12 | 12 | 2185 | 1359 | 79 | 9.7 | 20.9 |
| atkis_vegetation | EPSG:3857 | 12 | 12 | 2182 | 1350 | 63 | 9.8 | 13.1 |
| atkis_vegetation | EPSG:3857 | 13 | 13 | 4337 | 2664 | 64 | 11.7 | 8.0 |
| atkis_vegetation | EPSG:3857 | 13 | 13 | 4321 | 2726 | 97 | 8.6 | 16.7 |
| atkis_vegetation | EPSG:3857 | 13 | 13 | 4368 | 2716 | 53 | 10.0 | 7.1 |
| atkis_vegetation | EPSG:3857 | 13 | 13 | 4371 | 2722 | 58 | 9.5 | 10.9 |
| atkis_vegetation | EPSG:3857 | 13 | 13 | 4355 | 2798 | 54 | 9.6 | 14.3 |
| atkis_vegetation | EPSG:3857 | 14 | 14 | 8610 | 5528 | 51 | 10.1 | 6.4 |
| atkis_vegetation | EPSG:3857 | 14 | 14 | 8580 | 5544 | 69 | 9.9 | 18.2 |
| atkis_vegetation | EPSG:3857 | 14 | 14 | 8584 | 5531 | 52 | 10.5 | 2.6 |
| atkis_vegetation | EPSG:3857 | 14 | 14 | 8640 | 5551 | 44 | 9.8 | 5.7 |
| atkis_vegetation | EPSG:3857 | 14 | 14 | 8619 | 5339 | 50 | 9.8 | 8.5 |
| atkis_vegetation | EPSG:3857 | 16 | 16 | 34794 | 21746 | 52 | 9.0 | 5.7 |
| atkis_vegetation | EPSG:3857 | 16 | 16 | 34396 | 21605 | 52 | 8.0 | 6.4 |
| atkis_vegetation | EPSG:3857 | 16 | 16 | 34718 | 21657 | 42 | 7.9 | 5.9 |
| atkis_vegetation | EPSG:3857 | 16 | 16 | 34429 | 21350 | 40 | 11.0 | 5.3 |
| atkis_vegetation | EPSG:3857 | 16 | 16 | 34985 | 22085 | 51 | 10.3 | 6.1 |
| atkis_vegetation | EPSG:3857 | 18 | 18 | 137317 | 89546 | 45 | 9.8 | 0.3 |
| atkis_vegetation | EPSG:3857 | 18 | 18 | 137380 | 86898 | 48 | 9.0 | 2.3 |
| atkis_vegetation | EPSG:3857 | 18 | 18 | 140341 | 87356 | 46 | 8.5 | 1.6 |
| atkis_vegetation | EPSG:3857 | 18 | 18 | 137052 | 86460 | 51 | 7.8 | 0.7 |
| atkis_vegetation | EPSG:3857 | 18 | 18 | 137079 | 85468 | 37 | 8.2 | 0.6 |
| dark_max | EPSG:3857 | 8 | 8 | 135 | 87 | 198 | 6.7 | 42.8 |
| dark_max | EPSG:3857 | 8 | 8 | 134 | 86 | 228 | 7.6 | 43.5 |
| dark_max | EPSG:3857 | 8 | 8 | 136 | 84 | 222 | 8.7 | 44.9 |
| dark_max | EPSG:3857 | 8 | 8 | 136 | 87 | 172 | 8.5 | 40.0 |
| dark_max | EPSG:3857 | 8 | 8 | 134 | 85 | 201 | 8.0 | 42.2 |
| dark_max | EPSG:3857 | 10 | 10 | 535 | 347 | 402 | 8.5 | 42.2 |
| dark_max | EPSG:3857 | 10 | 10 | 543 | 340 | 222 | 11.7 | 34.2 |
| dark_max | EPSG:3857 | 10 | 10 | 538 | 340 | 289 | 11.1 | 37.8 |
| dark_max | EPSG:3857 | 10 | 10 | 545 | 350 | 191 | 8.4 | 36.7 |
| dark_max | EPSG:3857 | 10 | 10 | 545 | 338 | 187 | 7.7 | 34.5 |
| dark_max | EPSG:3857 | 12 | 12 | 2158 | 1391 | 64 | 8.0 | 29.2 |
| dark_max | EPSG:3857 | 12 | 12 | 2190 | 1378 | 74 | 7.7 | 32.9 |
| dark_max | EPSG:3857 | 12 | 12 | 2145 | 1395 | 108 | 7.6 | 26.1 |
| dark_max | EPSG:3857 | 12 | 12 | 2185 | 1359 | 73 | 7.3 | 23.5 |
| dark_max | EPSG:3857 | 12 | 12 | 2182 | 1350 | 51 | 7.3 | 15.2 |
| dark_max | EPSG:3857 | 13 | 13 | 4337 | 2664 | 53 | 7.5 | 14.9 |
| dark_max | EPSG:3857 | 13 | 13 | 4321 | 2726 | 82 | 7.9 | 24.0 |
| dark_max | EPSG:3857 | 13 | 13 | 4368 | 2716 | 60 | 7.7 | 10.3 |
| dark_max | EPSG:3857 | 13 | 13 | 4371 | 2722 | 64 | 7.3 | 16.3 |
| dark_max | EPSG:3857 | 13 | 13 | 4355 | 2798 | 77 | 7.7 | 27.6 |
| dark_max | EPSG:3857 | 14 | 14 | 8610 | 5528 | 61 | 7.8 | 15.2 |
| dark_max | EPSG:3857 | 14 | 14 | 8580 | 5544 | 75 | 8.0 | 29.1 |
| dark_max | EPSG:3857 | 14 | 14 | 8584 | 5531 | 54 | 8.8 | 13.0 |
| dark_max | EPSG:3857 | 14 | 14 | 8640 | 5551 | 55 | 10.5 | 9.0 |
| dark_max | EPSG:3857 | 14 | 14 | 8619 | 5339 | 68 | 8.0 | 13.8 |
| dark_max | EPSG:3857 | 16 | 16 | 34794 | 21746 | 66 | 8.0 | 10.8 |
| dark_max | EPSG:3857 | 16 | 16 | 34396 | 21605 | 62 | 7.6 | 8.0 |
| dark_max | EPSG:3857 | 16 | 16 | 34718 | 21657 | 67 | 8.0 | 17.9 |
| dark_max | EPSG:3857 | 16 | 16 | 34429 | 21350 | 61 | 7.2 | 12.8 |
| dark_max | EPSG:3857 | 16 | 16 | 34985 | 22085 | 71 | 8.3 | 19.2 |
| dark_max | EPSG:3857 | 18 | 18 | 137317 | 89546 | 61 | 7.3 | 1.8 |
| dark_max | EPSG:3857 | 18 | 18 | 137380 | 86898 | 65 | 7.0 | 6.5 |
| dark_max | EPSG:3857 | 18 | 18 | 140341 | 87356 | 59 | 7.8 | 2.7 |
| dark_max | EPSG:3857 | 18 | 18 | 137052 | 86460 | 67 | 7.4 | 8.7 |
| dark_max | EPSG:3857 | 18 | 18 | 137079 | 85468 | 65 | 8.1 | 7.5 |
| dark_min | EPSG:3857 | 8 | 8 | 135 | 87 | 104 | 8.1 | 21.6 |
| dark_min | EPSG:3857 | 8 | 8 | 134 | 86 | 160 | 8.0 | 24.7 |
| dark_min | EPSG:3857 | 8 | 8 | 136 | 84 | 110 | 8.3 | 20.9 |
| dark_min | EPSG:3857 | 8 | 8 | 136 | 87 | 85 | 8.0 | 19.3 |
| dark_min | EPSG:3857 | 8 | 8 | 134 | 85 | 93 | 7.5 | 22.5 |
| dark_min | EPSG:3857 | 10 | 10 | 535 | 347 | 269 | 7.8 | 27.4 |
| dark_min | EPSG:3857 | 10 | 10 | 543 | 340 | 102 | 8.4 | 17.4 |
| dark_min | EPSG:3857 | 10 | 10 | 538 | 340 | 135 | 8.0 | 22.8 |
| dark_min | EPSG:3857 | 10 | 10 | 545 | 350 | 106 | 8.7 | 17.6 |
| dark_min | EPSG:3857 | 10 | 10 | 545 | 338 | 116 | 8.1 | 22.0 |
| dark_min | EPSG:3857 | 12 | 12 | 2158 | 1391 | 35 | 7.3 | 8.2 |
| dark_min | EPSG:3857 | 12 | 12 | 2190 | 1378 | 45 | 7.1 | 17.2 |
| dark_min | EPSG:3857 | 12 | 12 | 2145 | 1395 | 84 | 8.0 | 15.2 |
| dark_min | EPSG:3857 | 12 | 12 | 2185 | 1359 | 49 | 8.0 | 14.3 |
| dark_min | EPSG:3857 | 12 | 12 | 2182 | 1350 | 37 | 8.6 | 7.7 |
| dark_min | EPSG:3857 | 13 | 13 | 4337 | 2664 | 36 | 7.7 | 4.7 |
| dark_min | EPSG:3857 | 13 | 13 | 4321 | 2726 | 41 | 7.4 | 10.1 |
| dark_min | EPSG:3857 | 13 | 13 | 4368 | 2716 | 29 | 7.0 | 4.7 |
| dark_min | EPSG:3857 | 13 | 13 | 4371 | 2722 | 33 | 7.1 | 6.3 |
| dark_min | EPSG:3857 | 13 | 13 | 4355 | 2798 | 36 | 6.6 | 9.5 |
| dark_min | EPSG:3857 | 14 | 14 | 8610 | 5528 | 28 | 6.8 | 4.0 |
| dark_min | EPSG:3857 | 14 | 14 | 8580 | 5544 | 34 | 6.8 | 7.1 |
| dark_min | EPSG:3857 | 14 | 14 | 8584 | 5531 | 25 | 6.4 | 0.3 |
| dark_min | EPSG:3857 | 14 | 14 | 8640 | 5551 | 21 | 6.6 | 0.1 |
| dark_min | EPSG:3857 | 14 | 14 | 8619 | 5339 | 26 | 6.5 | 3.1 |
| dark_min | EPSG:3857 | 16 | 16 | 34794 | 21746 | 30 | 7.1 | 3.7 |
| dark_min | EPSG:3857 | 16 | 16 | 34396 | 21605 | 29 | 6.7 | 3.6 |
| dark_min | EPSG:3857 | 16 | 16 | 34718 | 21657 | 33 | 6.4 | 9.9 |
| dark_min | EPSG:3857 | 16 | 16 | 34429 | 21350 | 28 | 6.4 | 5.7 |
| dark_min | EPSG:3857 | 16 | 16 | 34985 | 22085 | 38 | 8.2 | 7.1 |
| dark_min | EPSG:3857 | 18 | 18 | 137317 | 89546 | 26 | 7.5 | 0.1 |
| dark_min | EPSG:3857 | 18 | 18 | 137380 | 86898 | 27 | 8.0 | 1.2 |
| dark_min | EPSG:3857 | 18 | 18 | 140341 | 87356 | 27 | 8.0 | 0.3 |
| dark_min | EPSG:3857 | 18 | 18 | 137052 | 86460 | 33 | 8.5 | 2.6 |
| dark_min | EPSG:3857 | 18 | 18 | 137079 | 85468 | 35 | 9.3 | 3.9 |
| dark_nav | EPSG:3857 | 8 | 8 | 135 | 87 | 129 | 9.0 | 23.7 |
| dark_nav | EPSG:3857 | 8 | 8 | 134 | 86 | 170 | 8.0 | 27.6 |
| dark_nav | EPSG:3857 | 8 | 8 | 136 | 84 | 124 | 8.3 | 24.3 |
| dark_nav | EPSG:3857 | 8 | 8 | 136 | 87 | 135 | 9.5 | 21.3 |
| dark_nav | EPSG:3857 | 8 | 8 | 134 | 85 | 133 | 8.2 | 24.2 |
| dark_nav | EPSG:3857 | 10 | 10 | 535 | 347 | 284 | 8.8 | 29.2 |
| dark_nav | EPSG:3857 | 10 | 10 | 543 | 340 | 132 | 8.7 | 17.9 |
| dark_nav | EPSG:3857 | 10 | 10 | 538 | 340 | 150 | 8.0 | 23.5 |
| dark_nav | EPSG:3857 | 10 | 10 | 545 | 350 | 116 | 7.8 | 17.8 |
| dark_nav | EPSG:3857 | 10 | 10 | 545 | 338 | 125 | 9.0 | 23.6 |
| dark_nav | EPSG:3857 | 12 | 12 | 2158 | 1391 | 40 | 8.4 | 8.3 |
| dark_nav | EPSG:3857 | 12 | 12 | 2190 | 1378 | 48 | 8.0 | 17.1 |
| dark_nav | EPSG:3857 | 12 | 12 | 2145 | 1395 | 82 | 7.5 | 15.4 |
| dark_nav | EPSG:3857 | 12 | 12 | 2185 | 1359 | 48 | 7.8 | 14.9 |
| dark_nav | EPSG:3857 | 12 | 12 | 2182 | 1350 | 35 | 6.4 | 8.2 |
| dark_nav | EPSG:3857 | 13 | 13 | 4337 | 2664 | 33 | 6.7 | 4.9 |
| dark_nav | EPSG:3857 | 13 | 13 | 4321 | 2726 | 49 | 6.7 | 11.4 |
| dark_nav | EPSG:3857 | 13 | 13 | 4368 | 2716 | 32 | 6.9 | 5.3 |
| dark_nav | EPSG:3857 | 13 | 13 | 4371 | 2722 | 36 | 6.9 | 8.0 |
| dark_nav | EPSG:3857 | 13 | 13 | 4355 | 2798 | 41 | 6.5 | 9.9 |
| dark_nav | EPSG:3857 | 14 | 14 | 8610 | 5528 | 35 | 6.8 | 4.6 |
| dark_nav | EPSG:3857 | 14 | 14 | 8580 | 5544 | 46 | 6.8 | 15.1 |
| dark_nav | EPSG:3857 | 14 | 14 | 8584 | 5531 | 31 | 7.5 | 0.3 |
| dark_nav | EPSG:3857 | 14 | 14 | 8640 | 5551 | 26 | 6.4 | 0.1 |
| dark_nav | EPSG:3857 | 14 | 14 | 8619 | 5339 | 30 | 6.9 | 4.0 |
| dark_nav | EPSG:3857 | 16 | 16 | 34794 | 21746 | 32 | 6.5 | 4.7 |
| dark_nav | EPSG:3857 | 16 | 16 | 34396 | 21605 | 33 | 7.7 | 4.1 |
| dark_nav | EPSG:3857 | 16 | 16 | 34718 | 21657 | 44 | 9.1 | 17.3 |
| dark_nav | EPSG:3857 | 16 | 16 | 34429 | 21350 | 51 | 9.2 | 10.2 |
| dark_nav | EPSG:3857 | 16 | 16 | 34985 | 22085 | 43 | 6.5 | 18.0 |
| dark_nav | EPSG:3857 | 18 | 18 | 137317 | 89546 | 26 | 6.9 | 0.7 |
| dark_nav | EPSG:3857 | 18 | 18 | 137380 | 86898 | 29 | 7.0 | 3.0 |
| dark_nav | EPSG:3857 | 18 | 18 | 140341 | 87356 | 29 | 7.3 | 0.7 |
| dark_nav | EPSG:3857 | 18 | 18 | 137052 | 86460 | 38 | 7.8 | 6.3 |
| dark_nav | EPSG:3857 | 18 | 18 | 137079 | 85468 | 37 | 7.7 | 7.0 |
| dark_std | EPSG:3857 | 8 | 8 | 135 | 87 | 231 | 7.6 | 42.8 |
| dark_std | EPSG:3857 | 8 | 8 | 134 | 86 | 222 | 8.1 | 43.5 |
| dark_std | EPSG:3857 | 8 | 8 | 136 | 84 | 234 | 8.5 | 44.9 |
| dark_std | EPSG:3857 | 8 | 8 | 136 | 87 | 191 | 8.1 | 40.0 |
| dark_std | EPSG:3857 | 8 | 8 | 134 | 85 | 194 | 7.7 | 42.2 |
| dark_std | EPSG:3857 | 10 | 10 | 535 | 347 | 379 | 6.8 | 42.2 |
| dark_std | EPSG:3857 | 10 | 10 | 543 | 340 | 161 | 7.5 | 33.4 |
| dark_std | EPSG:3857 | 10 | 10 | 538 | 340 | 215 | 6.8 | 37.8 |
| dark_std | EPSG:3857 | 10 | 10 | 545 | 350 | 143 | 6.5 | 28.5 |
| dark_std | EPSG:3857 | 10 | 10 | 545 | 338 | 156 | 6.8 | 34.5 |
| dark_std | EPSG:3857 | 12 | 12 | 2158 | 1391 | 51 | 6.8 | 22.0 |
| dark_std | EPSG:3857 | 12 | 12 | 2190 | 1378 | 63 | 6.9 | 29.7 |
| dark_std | EPSG:3857 | 12 | 12 | 2145 | 1395 | 93 | 8.2 | 21.7 |
| dark_std | EPSG:3857 | 12 | 12 | 2185 | 1359 | 56 | 8.1 | 23.6 |
| dark_std | EPSG:3857 | 12 | 12 | 2182 | 1350 | 51 | 6.9 | 15.2 |
| dark_std | EPSG:3857 | 13 | 13 | 4337 | 2664 | 46 | 6.6 | 14.6 |
| dark_std | EPSG:3857 | 13 | 13 | 4321 | 2726 | 73 | 7.4 | 22.5 |
| dark_std | EPSG:3857 | 13 | 13 | 4368 | 2716 | 42 | 6.8 | 9.8 |
| dark_std | EPSG:3857 | 13 | 13 | 4371 | 2722 | 50 | 8.6 | 14.5 |
| dark_std | EPSG:3857 | 13 | 13 | 4355 | 2798 | 60 | 7.5 | 22.8 |
| dark_std | EPSG:3857 | 14 | 14 | 8610 | 5528 | 51 | 7.2 | 13.5 |
| dark_std | EPSG:3857 | 14 | 14 | 8580 | 5544 | 78 | 7.2 | 29.1 |
| dark_std | EPSG:3857 | 14 | 14 | 8584 | 5531 | 46 | 7.2 | 10.8 |
| dark_std | EPSG:3857 | 14 | 14 | 8640 | 5551 | 41 | 10.4 | 5.6 |
| dark_std | EPSG:3857 | 14 | 14 | 8619 | 5339 | 50 | 6.8 | 11.6 |
| dark_std | EPSG:3857 | 16 | 16 | 34794 | 21746 | 44 | 6.7 | 8.9 |
| dark_std | EPSG:3857 | 16 | 16 | 34396 | 21605 | 46 | 6.8 | 7.6 |
| dark_std | EPSG:3857 | 16 | 16 | 34718 | 21657 | 50 | 6.6 | 17.9 |
| dark_std | EPSG:3857 | 16 | 16 | 34429 | 21350 | 46 | 7.5 | 12.8 |
| dark_std | EPSG:3857 | 16 | 16 | 34985 | 22085 | 51 | 7.3 | 19.2 |
| dark_std | EPSG:3857 | 18 | 18 | 137317 | 89546 | 42 | 9.1 | 1.8 |
| dark_std | EPSG:3857 | 18 | 18 | 137380 | 86898 | 46 | 9.0 | 3.7 |
| dark_std | EPSG:3857 | 18 | 18 | 140341 | 87356 | 44 | 6.8 | 2.7 |
| dark_std | EPSG:3857 | 18 | 18 | 137052 | 86460 | 44 | 7.0 | 8.7 |
| dark_std | EPSG:3857 | 18 | 18 | 137079 | 85468 | 42 | 7.4 | 7.5 |
| dark_topographic | EPSG:3857 | 8 | 8 | 135 | 87 | 208 | 6.7 | 41.3 |
| dark_topographic | EPSG:3857 | 8 | 8 | 134 | 86 | 194 | 7.8 | 44.0 |
| dark_topographic | EPSG:3857 | 8 | 8 | 136 | 84 | 220 | 8.3 | 44.9 |
| dark_topographic | EPSG:3857 | 8 | 8 | 136 | 87 | 220 | 6.9 | 39.2 |
| dark_topographic | EPSG:3857 | 8 | 8 | 134 | 85 | 199 | 7.2 | 41.9 |
| dark_topographic | EPSG:3857 | 10 | 10 | 535 | 347 | 320 | 7.3 | 40.7 |
| dark_topographic | EPSG:3857 | 10 | 10 | 543 | 340 | 187 | 6.8 | 32.4 |
| dark_topographic | EPSG:3857 | 10 | 10 | 538 | 340 | 216 | 8.2 | 37.5 |
| dark_topographic | EPSG:3857 | 10 | 10 | 545 | 350 | 171 | 7.5 | 36.2 |
| dark_topographic | EPSG:3857 | 10 | 10 | 545 | 338 | 182 | 9.2 | 34.2 |
| dark_topographic | EPSG:3857 | 12 | 12 | 2158 | 1391 | 69 | 9.0 | 28.3 |
| dark_topographic | EPSG:3857 | 12 | 12 | 2190 | 1378 | 75 | 9.0 | 29.8 |
| dark_topographic | EPSG:3857 | 12 | 12 | 2145 | 1395 | 129 | 11.3 | 25.5 |
| dark_topographic | EPSG:3857 | 12 | 12 | 2185 | 1359 | 65 | 8.2 | 23.4 |
| dark_topographic | EPSG:3857 | 12 | 12 | 2182 | 1350 | 51 | 8.8 | 14.6 |
| dark_topographic | EPSG:3857 | 13 | 13 | 4337 | 2664 | 52 | 9.1 | 9.7 |
| dark_topographic | EPSG:3857 | 13 | 13 | 4321 | 2726 | 71 | 7.9 | 22.0 |
| dark_topographic | EPSG:3857 | 13 | 13 | 4368 | 2716 | 48 | 8.2 | 9.0 |
| dark_topographic | EPSG:3857 | 13 | 13 | 4371 | 2722 | 51 | 8.4 | 15.5 |
| dark_topographic | EPSG:3857 | 13 | 13 | 4355 | 2798 | 58 | 8.0 | 22.2 |
| dark_topographic | EPSG:3857 | 14 | 14 | 8610 | 5528 | 47 | 7.7 | 10.4 |
| dark_topographic | EPSG:3857 | 14 | 14 | 8580 | 5544 | 65 | 8.6 | 26.7 |
| dark_topographic | EPSG:3857 | 14 | 14 | 8584 | 5531 | 56 | 7.7 | 5.8 |
| dark_topographic | EPSG:3857 | 14 | 14 | 8640 | 5551 | 54 | 7.9 | 5.0 |
| dark_topographic | EPSG:3857 | 14 | 14 | 8619 | 5339 | 48 | 7.9 | 12.7 |
| dark_topographic | EPSG:3857 | 16 | 16 | 34794 | 21746 | 52 | 7.7 | 7.7 |
| dark_topographic | EPSG:3857 | 16 | 16 | 34396 | 21605 | 48 | 8.3 | 7.6 |
| dark_topographic | EPSG:3857 | 16 | 16 | 34718 | 21657 | 58 | 8.7 | 17.7 |
| dark_topographic | EPSG:3857 | 16 | 16 | 34429 | 21350 | 52 | 8.6 | 12.2 |
| dark_topographic | EPSG:3857 | 16 | 16 | 34985 | 22085 | 61 | 8.4 | 18.7 |
| dark_topographic | EPSG:3857 | 18 | 18 | 137317 | 89546 | 49 | 8.6 | 1.2 |
| dark_topographic | EPSG:3857 | 18 | 18 | 137380 | 86898 | 57 | 11.8 | 6.2 |
| dark_topographic | EPSG:3857 | 18 | 18 | 140341 | 87356 | 60 | 10.1 | 1.9 |
| dark_topographic | EPSG:3857 | 18 | 18 | 137052 | 86460 | 55 | 8.4 | 6.7 |
| dark_topographic | EPSG:3857 | 18 | 18 | 137079 | 85468 | 59 | 8.0 | 7.2 |
| dark_vegetation | EPSG:3857 | 8 | 8 | 135 | 87 | 229 | 8.3 | 40.6 |
| dark_vegetation | EPSG:3857 | 8 | 8 | 134 | 86 | 326 | 9.3 | 40.8 |
| dark_vegetation | EPSG:3857 | 8 | 8 | 136 | 84 | 244 | 8.1 | 43.6 |
| dark_vegetation | EPSG:3857 | 8 | 8 | 136 | 87 | 209 | 7.8 | 37.2 |
| dark_vegetation | EPSG:3857 | 8 | 8 | 134 | 85 | 205 | 8.5 | 40.9 |
| dark_vegetation | EPSG:3857 | 10 | 10 | 535 | 347 | 397 | 15.4 | 41.4 |
| dark_vegetation | EPSG:3857 | 10 | 10 | 543 | 340 | 242 | 8.2 | 32.8 |
| dark_vegetation | EPSG:3857 | 10 | 10 | 538 | 340 | 244 | 9.7 | 37.8 |
| dark_vegetation | EPSG:3857 | 10 | 10 | 545 | 350 | 179 | 10.1 | 28.1 |
| dark_vegetation | EPSG:3857 | 10 | 10 | 545 | 338 | 200 | 9.7 | 34.3 |
| dark_vegetation | EPSG:3857 | 12 | 12 | 2158 | 1391 | 70 | 8.9 | 19.2 |
| dark_vegetation | EPSG:3857 | 12 | 12 | 2190 | 1378 | 85 | 9.4 | 27.4 |
| dark_vegetation | EPSG:3857 | 12 | 12 | 2145 | 1395 | 113 | 9.1 | 18.3 |
| dark_vegetation | EPSG:3857 | 12 | 12 | 2185 | 1359 | 66 | 8.4 | 21.6 |
| dark_vegetation | EPSG:3857 | 12 | 12 | 2182 | 1350 | 49 | 7.8 | 13.8 |
| dark_vegetation | EPSG:3857 | 13 | 13 | 4337 | 2664 | 60 | 9.2 | 8.1 |
| dark_vegetation | EPSG:3857 | 13 | 13 | 4321 | 2726 | 74 | 7.5 | 18.0 |
| dark_vegetation | EPSG:3857 | 13 | 13 | 4368 | 2716 | 45 | 8.3 | 6.6 |
| dark_vegetation | EPSG:3857 | 13 | 13 | 4371 | 2722 | 54 | 9.2 | 11.8 |
| dark_vegetation | EPSG:3857 | 13 | 13 | 4355 | 2798 | 55 | 9.1 | 14.0 |
| dark_vegetation | EPSG:3857 | 14 | 14 | 8610 | 5528 | 49 | 8.8 | 6.4 |
| dark_vegetation | EPSG:3857 | 14 | 14 | 8580 | 5544 | 73 | 9.1 | 20.0 |
| dark_vegetation | EPSG:3857 | 14 | 14 | 8584 | 5531 | 64 | 10.5 | 2.3 |
| dark_vegetation | EPSG:3857 | 14 | 14 | 8640 | 5551 | 57 | 10.1 | 1.3 |
| dark_vegetation | EPSG:3857 | 14 | 14 | 8619 | 5339 | 53 | 8.8 | 7.9 |
| dark_vegetation | EPSG:3857 | 16 | 16 | 34794 | 21746 | 56 | 9.2 | 5.8 |
| dark_vegetation | EPSG:3857 | 16 | 16 | 34396 | 21605 | 57 | 8.9 | 5.3 |
| dark_vegetation | EPSG:3857 | 16 | 16 | 34718 | 21657 | 59 | 9.8 | 6.0 |
| dark_vegetation | EPSG:3857 | 16 | 16 | 34429 | 21350 | 53 | 9.3 | 5.4 |
| dark_vegetation | EPSG:3857 | 16 | 16 | 34985 | 22085 | 49 | 9.3 | 3.5 |
| dark_vegetation | EPSG:3857 | 18 | 18 | 137317 | 89546 | 54 | 13.8 | 0.5 |
| dark_vegetation | EPSG:3857 | 18 | 18 | 137380 | 86898 | 47 | 8.8 | 1.3 |
| dark_vegetation | EPSG:3857 | 18 | 18 | 140341 | 87356 | 45 | 9.2 | 1.6 |
| dark_vegetation | EPSG:3857 | 18 | 18 | 137052 | 86460 | 48 | 9.6 | 0.6 |
| dark_vegetation | EPSG:3857 | 18 | 18 | 137079 | 85468 | 53 | 10.0 | 0.4 |
| default_max | EPSG:3857 | 8 | 8 | 135 | 87 | 262 | 9.1 | 46.6 |
| default_max | EPSG:3857 | 8 | 8 | 134 | 86 | 269 | 7.8 | 46.1 |
| default_max | EPSG:3857 | 8 | 8 | 136 | 84 | 235 | 7.5 | 45.5 |
| default_max | EPSG:3857 | 8 | 8 | 136 | 87 | 218 | 8.1 | 44.1 |
| default_max | EPSG:3857 | 8 | 8 | 134 | 85 | 231 | 8.6 | 45.5 |
| default_max | EPSG:3857 | 10 | 10 | 535 | 347 | 441 | 8.1 | 39.2 |
| default_max | EPSG:3857 | 10 | 10 | 543 | 340 | 225 | 8.3 | 34.3 |
| default_max | EPSG:3857 | 10 | 10 | 538 | 340 | 267 | 9.3 | 35.8 |
| default_max | EPSG:3857 | 10 | 10 | 545 | 350 | 196 | 8.4 | 36.2 |
| default_max | EPSG:3857 | 10 | 10 | 545 | 338 | 202 | 9.8 | 33.1 |
| default_max | EPSG:3857 | 12 | 12 | 2158 | 1391 | 83 | 10.0 | 28.0 |
| default_max | EPSG:3857 | 12 | 12 | 2190 | 1378 | 103 | 8.5 | 32.5 |
| default_max | EPSG:3857 | 12 | 12 | 2145 | 1395 | 133 | 8.2 | 25.1 |
| default_max | EPSG:3857 | 12 | 12 | 2185 | 1359 | 77 | 8.3 | 23.1 |
| default_max | EPSG:3857 | 12 | 12 | 2182 | 1350 | 79 | 10.0 | 14.4 |
| default_max | EPSG:3857 | 13 | 13 | 4337 | 2664 | 82 | 9.3 | 14.1 |
| default_max | EPSG:3857 | 13 | 13 | 4321 | 2726 | 119 | 8.0 | 23.0 |
| default_max | EPSG:3857 | 13 | 13 | 4368 | 2716 | 72 | 10.3 | 10.2 |
| default_max | EPSG:3857 | 13 | 13 | 4371 | 2722 | 84 | 10.6 | 15.7 |
| default_max | EPSG:3857 | 13 | 13 | 4355 | 2798 | 98 | 10.3 | 26.3 |
| default_max | EPSG:3857 | 14 | 14 | 8610 | 5528 | 75 | 10.3 | 14.3 |
| default_max | EPSG:3857 | 14 | 14 | 8580 | 5544 | 107 | 7.9 | 27.9 |
| default_max | EPSG:3857 | 14 | 14 | 8584 | 5531 | 73 | 9.0 | 12.7 |
| default_max | EPSG:3857 | 14 | 14 | 8640 | 5551 | 61 | 9.1 | 8.8 |
| default_max | EPSG:3857 | 14 | 14 | 8619 | 5339 | 61 | 9.4 | 13.4 |
| default_max | EPSG:3857 | 16 | 16 | 34794 | 21746 | 72 | 9.6 | 10.7 |
| default_max | EPSG:3857 | 16 | 16 | 34396 | 21605 | 75 | 10.3 | 7.6 |
| default_max | EPSG:3857 | 16 | 16 | 34718 | 21657 | 79 | 9.7 | 17.8 |
| default_max | EPSG:3857 | 16 | 16 | 34429 | 21350 | 75 | 13.5 | 13.0 |
| default_max | EPSG:3857 | 16 | 16 | 34985 | 22085 | 82 | 11.3 | 19.7 |
| default_max | EPSG:3857 | 18 | 18 | 137317 | 89546 | 89 | 10.2 | 1.7 |
| default_max | EPSG:3857 | 18 | 18 | 137380 | 86898 | 78 | 11.3 | 6.7 |
| default_max | EPSG:3857 | 18 | 18 | 140341 | 87356 | 73 | 12.3 | 2.7 |
| default_max | EPSG:3857 | 18 | 18 | 137052 | 86460 | 85 | 10.3 | 9.0 |
| default_max | EPSG:3857 | 18 | 18 | 137079 | 85468 | 77 | 9.7 | 7.6 |
| default_min | EPSG:3857 | 8 | 8 | 135 | 87 | 119 | 9.2 | 21.2 |
| default_min | EPSG:3857 | 8 | 8 | 134 | 86 | 149 | 8.2 | 24.9 |
| default_min | EPSG:3857 | 8 | 8 | 136 | 84 | 90 | 8.8 | 19.9 |
| default_min | EPSG:3857 | 8 | 8 | 136 | 87 | 92 | 7.9 | 19.1 |
| default_min | EPSG:3857 | 8 | 8 | 134 | 85 | 98 | 8.1 | 21.9 |
| default_min | EPSG:3857 | 10 | 10 | 535 | 347 | 283 | 8.0 | 26.2 |
| default_min | EPSG:3857 | 10 | 10 | 543 | 340 | 119 | 9.1 | 16.3 |
| default_min | EPSG:3857 | 10 | 10 | 538 | 340 | 157 | 9.0 | 21.7 |
| default_min | EPSG:3857 | 10 | 10 | 545 | 350 | 115 | 12.8 | 17.2 |
| default_min | EPSG:3857 | 10 | 10 | 545 | 338 | 137 | 8.6 | 20.5 |
| default_min | EPSG:3857 | 12 | 12 | 2158 | 1391 | 40 | 9.1 | 8.0 |
| default_min | EPSG:3857 | 12 | 12 | 2190 | 1378 | 53 | 8.2 | 16.9 |
| default_min | EPSG:3857 | 12 | 12 | 2145 | 1395 | 90 | 8.7 | 14.2 |
| default_min | EPSG:3857 | 12 | 12 | 2185 | 1359 | 51 | 8.8 | 13.7 |
| default_min | EPSG:3857 | 12 | 12 | 2182 | 1350 | 43 | 9.2 | 7.1 |
| default_min | EPSG:3857 | 13 | 13 | 4337 | 2664 | 42 | 9.8 | 4.4 |
| default_min | EPSG:3857 | 13 | 13 | 4321 | 2726 | 59 | 9.4 | 9.7 |
| default_min | EPSG:3857 | 13 | 13 | 4368 | 2716 | 41 | 9.0 | 4.2 |
| default_min | EPSG:3857 | 13 | 13 | 4371 | 2722 | 42 | 8.9 | 5.8 |
| default_min | EPSG:3857 | 13 | 13 | 4355 | 2798 | 49 | 10.9 | 8.9 |
| default_min | EPSG:3857 | 14 | 14 | 8610 | 5528 | 38 | 8.8 | 3.7 |
| default_min | EPSG:3857 | 14 | 14 | 8580 | 5544 | 48 | 9.0 | 6.8 |
| default_min | EPSG:3857 | 14 | 14 | 8584 | 5531 | 36 | 9.5 | 0.3 |
| default_min | EPSG:3857 | 14 | 14 | 8640 | 5551 | 31 | 9.2 | 0.1 |
| default_min | EPSG:3857 | 14 | 14 | 8619 | 5339 | 36 | 9.2 | 3.7 |
| default_min | EPSG:3857 | 16 | 16 | 34794 | 21746 | 40 | 9.0 | 3.6 |
| default_min | EPSG:3857 | 16 | 16 | 34396 | 21605 | 38 | 8.9 | 4.0 |
| default_min | EPSG:3857 | 16 | 16 | 34718 | 21657 | 48 | 9.8 | 9.5 |
| default_min | EPSG:3857 | 16 | 16 | 34429 | 21350 | 42 | 7.9 | 5.4 |
| default_min | EPSG:3857 | 16 | 16 | 34985 | 22085 | 38 | 8.2 | 7.4 |
| default_min | EPSG:3857 | 18 | 18 | 137317 | 89546 | 32 | 9.2 | 0.1 |
| default_min | EPSG:3857 | 18 | 18 | 137380 | 86898 | 33 | 7.4 | 2.0 |
| default_min | EPSG:3857 | 18 | 18 | 140341 | 87356 | 29 | 7.7 | 0.3 |
| default_min | EPSG:3857 | 18 | 18 | 137052 | 86460 | 33 | 8.2 | 2.3 |
| default_min | EPSG:3857 | 18 | 18 | 137079 | 85468 | 32 | 7.7 | 3.7 |
| default_nav | EPSG:3857 | 8 | 8 | 135 | 87 | 123 | 6.8 | 23.2 |
| default_nav | EPSG:3857 | 8 | 8 | 134 | 86 | 170 | 7.7 | 27.1 |
| default_nav | EPSG:3857 | 8 | 8 | 136 | 84 | 126 | 7.2 | 23.5 |
| default_nav | EPSG:3857 | 8 | 8 | 136 | 87 | 120 | 8.3 | 20.9 |
| default_nav | EPSG:3857 | 8 | 8 | 134 | 85 | 132 | 7.6 | 23.2 |
| default_nav | EPSG:3857 | 10 | 10 | 535 | 347 | 309 | 8.0 | 28.1 |
| default_nav | EPSG:3857 | 10 | 10 | 543 | 340 | 119 | 8.9 | 16.4 |
| default_nav | EPSG:3857 | 10 | 10 | 538 | 340 | 164 | 9.1 | 22.3 |
| default_nav | EPSG:3857 | 10 | 10 | 545 | 350 | 108 | 8.1 | 17.2 |
| default_nav | EPSG:3857 | 10 | 10 | 545 | 338 | 120 | 8.8 | 22.0 |
| default_nav | EPSG:3857 | 12 | 12 | 2158 | 1391 | 39 | 9.3 | 8.0 |
| default_nav | EPSG:3857 | 12 | 12 | 2190 | 1378 | 55 | 8.9 | 16.9 |
| default_nav | EPSG:3857 | 12 | 12 | 2145 | 1395 | 84 | 8.3 | 14.5 |
| default_nav | EPSG:3857 | 12 | 12 | 2185 | 1359 | 53 | 8.7 | 14.3 |
| default_nav | EPSG:3857 | 12 | 12 | 2182 | 1350 | 41 | 10.6 | 7.9 |
| default_nav | EPSG:3857 | 13 | 13 | 4337 | 2664 | 37 | 9.4 | 4.6 |
| default_nav | EPSG:3857 | 13 | 13 | 4321 | 2726 | 50 | 8.5 | 10.9 |
| default_nav | EPSG:3857 | 13 | 13 | 4368 | 2716 | 35 | 6.6 | 4.9 |
| default_nav | EPSG:3857 | 13 | 13 | 4371 | 2722 | 36 | 7.6 | 7.5 |
| default_nav | EPSG:3857 | 13 | 13 | 4355 | 2798 | 47 | 10.1 | 9.4 |
| default_nav | EPSG:3857 | 14 | 14 | 8610 | 5528 | 41 | 9.2 | 4.3 |
| default_nav | EPSG:3857 | 14 | 14 | 8580 | 5544 | 52 | 9.8 | 14.6 |
| default_nav | EPSG:3857 | 14 | 14 | 8584 | 5531 | 36 | 10.2 | 0.3 |
| default_nav | EPSG:3857 | 14 | 14 | 8640 | 5551 | 30 | 8.6 | 0.1 |
| default_nav | EPSG:3857 | 14 | 14 | 8619 | 5339 | 32 | 12.9 | 4.4 |
| default_nav | EPSG:3857 | 16 | 16 | 34794 | 21746 | 41 | 8.6 | 4.5 |
| default_nav | EPSG:3857 | 16 | 16 | 34396 | 21605 | 34 | 7.7 | 4.5 |
| default_nav | EPSG:3857 | 16 | 16 | 34718 | 21657 | 43 | 8.8 | 17.3 |
| default_nav | EPSG:3857 | 16 | 16 | 34429 | 21350 | 38 | 9.5 | 10.2 |
| default_nav | EPSG:3857 | 16 | 16 | 34985 | 22085 | 44 | 8.0 | 19.2 |
| default_nav | EPSG:3857 | 18 | 18 | 137317 | 89546 | 31 | 7.6 | 1.1 |
| default_nav | EPSG:3857 | 18 | 18 | 137380 | 86898 | 32 | 8.0 | 3.9 |
| default_nav | EPSG:3857 | 18 | 18 | 140341 | 87356 | 32 | 9.6 | 0.9 |
| default_nav | EPSG:3857 | 18 | 18 | 137052 | 86460 | 38 | 8.2 | 6.9 |
| default_nav | EPSG:3857 | 18 | 18 | 137079 | 85468 | 36 | 9.1 | 7.3 |
| default_std | EPSG:3857 | 8 | 8 | 135 | 87 | 212 | 8.4 | 46.6 |
| default_std | EPSG:3857 | 8 | 8 | 134 | 86 | 206 | 8.1 | 46.1 |
| default_std | EPSG:3857 | 8 | 8 | 136 | 84 | 254 | 7.8 | 45.5 |
| default_std | EPSG:3857 | 8 | 8 | 136 | 87 | 183 | 9.3 | 44.1 |
| default_std | EPSG:3857 | 8 | 8 | 134 | 85 | 196 | 9.7 | 45.5 |
| default_std | EPSG:3857 | 10 | 10 | 535 | 347 | 373 | 7.4 | 39.2 |
| default_std | EPSG:3857 | 10 | 10 | 543 | 340 | 209 | 7.1 | 33.7 |
| default_std | EPSG:3857 | 10 | 10 | 538 | 340 | 271 | 10.1 | 35.8 |
| default_std | EPSG:3857 | 10 | 10 | 545 | 350 | 197 | 8.7 | 28.9 |
| default_std | EPSG:3857 | 10 | 10 | 545 | 338 | 198 | 8.7 | 33.1 |
| default_std | EPSG:3857 | 12 | 12 | 2158 | 1391 | 75 | 9.6 | 22.2 |
| default_std | EPSG:3857 | 12 | 12 | 2190 | 1378 | 86 | 9.5 | 29.6 |
| default_std | EPSG:3857 | 12 | 12 | 2145 | 1395 | 125 | 8.9 | 20.5 |
| default_std | EPSG:3857 | 12 | 12 | 2185 | 1359 | 72 | 8.3 | 23.0 |
| default_std | EPSG:3857 | 12 | 12 | 2182 | 1350 | 50 | 8.1 | 14.4 |
| default_std | EPSG:3857 | 13 | 13 | 4337 | 2664 | 54 | 8.8 | 13.8 |
| default_std | EPSG:3857 | 13 | 13 | 4321 | 2726 | 85 | 8.4 | 21.6 |
| default_std | EPSG:3857 | 13 | 13 | 4368 | 2716 | 51 | 7.6 | 9.8 |
| default_std | EPSG:3857 | 13 | 13 | 4371 | 2722 | 59 | 7.7 | 13.9 |
| default_std | EPSG:3857 | 13 | 13 | 4355 | 2798 | 61 | 8.6 | 21.9 |
| default_std | EPSG:3857 | 14 | 14 | 8610 | 5528 | 50 | 8.9 | 13.0 |
| default_std | EPSG:3857 | 14 | 14 | 8580 | 5544 | 81 | 8.3 | 27.4 |
| default_std | EPSG:3857 | 14 | 14 | 8584 | 5531 | 49 | 7.5 | 10.5 |
| default_std | EPSG:3857 | 14 | 14 | 8640 | 5551 | 41 | 6.9 | 5.6 |
| default_std | EPSG:3857 | 14 | 14 | 8619 | 5339 | 41 | 7.9 | 11.4 |
| default_std | EPSG:3857 | 16 | 16 | 34794 | 21746 | 45 | 7.5 | 8.7 |
| default_std | EPSG:3857 | 16 | 16 | 34396 | 21605 | 46 | 7.4 | 7.3 |
| default_std | EPSG:3857 | 16 | 16 | 34718 | 21657 | 49 | 7.3 | 17.8 |
| default_std | EPSG:3857 | 16 | 16 | 34429 | 21350 | 48 | 7.6 | 13.0 |
| default_std | EPSG:3857 | 16 | 16 | 34985 | 22085 | 56 | 7.1 | 19.7 |
| default_std | EPSG:3857 | 18 | 18 | 137317 | 89546 | 43 | 6.8 | 1.7 |
| default_std | EPSG:3857 | 18 | 18 | 137380 | 86898 | 49 | 7.0 | 4.6 |
| default_std | EPSG:3857 | 18 | 18 | 140341 | 87356 | 48 | 7.0 | 2.7 |
| default_std | EPSG:3857 | 18 | 18 | 137052 | 86460 | 51 | 8.4 | 9.0 |
| default_std | EPSG:3857 | 18 | 18 | 137079 | 85468 | 61 | 7.4 | 7.6 |
| default_topographic | EPSG:3857 | 8 | 8 | 135 | 87 | 207 | 7.2 | 45.3 |
| default_topographic | EPSG:3857 | 8 | 8 | 134 | 86 | 200 | 7.5 | 45.1 |
| default_topographic | EPSG:3857 | 8 | 8 | 136 | 84 | 238 | 7.7 | 45.3 |
| default_topographic | EPSG:3857 | 8 | 8 | 136 | 87 | 189 | 7.4 | 43.8 |
| default_topographic | EPSG:3857 | 8 | 8 | 134 | 85 | 207 | 10.6 | 45.8 |
| default_topographic | EPSG:3857 | 10 | 10 | 535 | 347 | 337 | 7.4 | 38.3 |
| default_topographic | EPSG:3857 | 10 | 10 | 543 | 340 | 169 | 7.3 | 32.2 |
| default_topographic | EPSG:3857 | 10 | 10 | 538 | 340 | 204 | 7.9 | 35.2 |
| default_topographic | EPSG:3857 | 10 | 10 | 545 | 350 | 147 | 7.3 | 36.3 |
| default_topographic | EPSG:3857 | 10 | 10 | 545 | 338 | 150 | 7.7 | 32.2 |
| default_topographic | EPSG:3857 | 12 | 12 | 2158 | 1391 | 65 | 7.9 | 27.4 |
| default_topographic | EPSG:3857 | 12 | 12 | 2190 | 1378 | 72 | 7.9 | 29.6 |
| default_topographic | EPSG:3857 | 12 | 12 | 2145 | 1395 | 114 | 7.7 | 24.6 |
| default_topographic | EPSG:3857 | 12 | 12 | 2185 | 1359 | 73 | 7.1 | 22.5 |
| default_topographic | EPSG:3857 | 12 | 12 | 2182 | 1350 | 64 | 7.4 | 14.1 |
| default_topographic | EPSG:3857 | 13 | 13 | 4337 | 2664 | 64 | 7.4 | 9.5 |
| default_topographic | EPSG:3857 | 13 | 13 | 4321 | 2726 | 88 | 8.3 | 20.6 |
| default_topographic | EPSG:3857 | 13 | 13 | 4368 | 2716 | 64 | 8.2 | 8.9 |
| default_topographic | EPSG:3857 | 13 | 13 | 4371 | 2722 | 74 | 10.7 | 14.9 |
| default_topographic | EPSG:3857 | 13 | 13 | 4355 | 2798 | 74 | 7.0 | 21.2 |
| default_topographic | EPSG:3857 | 14 | 14 | 8610 | 5528 | 54 | 6.8 | 9.9 |
| default_topographic | EPSG:3857 | 14 | 14 | 8580 | 5544 | 79 | 7.6 | 25.0 |
| default_topographic | EPSG:3857 | 14 | 14 | 8584 | 5531 | 56 | 6.9 | 5.2 |
| default_topographic | EPSG:3857 | 14 | 14 | 8640 | 5551 | 50 | 6.6 | 4.5 |
| default_topographic | EPSG:3857 | 14 | 14 | 8619 | 5339 | 58 | 9.5 | 12.4 |
| default_topographic | EPSG:3857 | 16 | 16 | 34794 | 21746 | 57 | 6.5 | 7.2 |
| default_topographic | EPSG:3857 | 16 | 16 | 34396 | 21605 | 54 | 6.6 | 8.0 |
| default_topographic | EPSG:3857 | 16 | 16 | 34718 | 21657 | 61 | 7.3 | 17.6 |
| default_topographic | EPSG:3857 | 16 | 16 | 34429 | 21350 | 60 | 6.7 | 12.3 |
| default_topographic | EPSG:3857 | 16 | 16 | 34985 | 22085 | 61 | 6.8 | 19.3 |
| default_topographic | EPSG:3857 | 18 | 18 | 137317 | 89546 | 53 | 6.4 | 1.0 |
| default_topographic | EPSG:3857 | 18 | 18 | 137380 | 86898 | 45 | 6.1 | 6.4 |
| default_topographic | EPSG:3857 | 18 | 18 | 140341 | 87356 | 49 | 7.1 | 2.0 |
| default_topographic | EPSG:3857 | 18 | 18 | 137052 | 86460 | 54 | 7.3 | 7.3 |
| default_topographic | EPSG:3857 | 18 | 18 | 137079 | 85468 | 56 | 7.9 | 7.3 |
| default_vegetation | EPSG:3857 | 8 | 8 | 135 | 87 | 214 | 7.7 | 45.7 |
| default_vegetation | EPSG:3857 | 8 | 8 | 134 | 86 | 274 | 7.0 | 45.0 |
| default_vegetation | EPSG:3857 | 8 | 8 | 136 | 84 | 215 | 7.4 | 45.5 |
| default_vegetation | EPSG:3857 | 8 | 8 | 136 | 87 | 183 | 7.2 | 43.1 |
| default_vegetation | EPSG:3857 | 8 | 8 | 134 | 85 | 217 | 9.4 | 46.3 |
| default_vegetation | EPSG:3857 | 10 | 10 | 535 | 347 | 349 | 7.1 | 38.5 |
| default_vegetation | EPSG:3857 | 10 | 10 | 543 | 340 | 184 | 8.5 | 33.3 |
| default_vegetation | EPSG:3857 | 10 | 10 | 538 | 340 | 266 | 8.4 | 35.9 |
| default_vegetation | EPSG:3857 | 10 | 10 | 545 | 350 | 191 | 7.7 | 28.5 |
| default_vegetation | EPSG:3857 | 10 | 10 | 545 | 338 | 178 | 8.1 | 33.0 |
| default_vegetation | EPSG:3857 | 12 | 12 | 2158 | 1391 | 61 | 7.8 | 19.9 |
| default_vegetation | EPSG:3857 | 12 | 12 | 2190 | 1378 | 78 | 7.9 | 27.5 |
| default_vegetation | EPSG:3857 | 12 | 12 | 2145 | 1395 | 105 | 9.7 | 17.5 |
| default_vegetation | EPSG:3857 | 12 | 12 | 2185 | 1359 | 73 | 8.6 | 20.9 |
| default_vegetation | EPSG:3857 | 12 | 12 | 2182 | 1350 | 61 | 9.2 | 13.4 |
| default_vegetation | EPSG:3857 | 13 | 13 | 4337 | 2664 | 54 | 8.9 | 8.5 |
| default_vegetation | EPSG:3857 | 13 | 13 | 4321 | 2726 | 82 | 9.7 | 16.8 |
| default_vegetation | EPSG:3857 | 13 | 13 | 4368 | 2716 | 50 | 9.0 | 6.8 |
| default_vegetation | EPSG:3857 | 13 | 13 | 4371 | 2722 | 56 | 9.1 | 12.0 |
| default_vegetation | EPSG:3857 | 13 | 13 | 4355 | 2798 | 52 | 9.5 | 14.2 |
| default_vegetation | EPSG:3857 | 14 | 14 | 8610 | 5528 | 46 | 9.4 | 6.5 |
| default_vegetation | EPSG:3857 | 14 | 14 | 8580 | 5544 | 65 | 10.2 | 19.6 |
| default_vegetation | EPSG:3857 | 14 | 14 | 8584 | 5531 | 49 | 8.7 | 2.3 |
| default_vegetation | EPSG:3857 | 14 | 14 | 8640 | 5551 | 42 | 8.6 | 1.2 |
| default_vegetation | EPSG:3857 | 14 | 14 | 8619 | 5339 | 42 | 8.9 | 8.6 |
| default_vegetation | EPSG:3857 | 16 | 16 | 34794 | 21746 | 47 | 8.8 | 5.7 |
| default_vegetation | EPSG:3857 | 16 | 16 | 34396 | 21605 | 47 | 8.3 | 4.9 |
| default_vegetation | EPSG:3857 | 16 | 16 | 34718 | 21657 | 43 | 8.4 | 5.7 |
| default_vegetation | EPSG:3857 | 16 | 16 | 34429 | 21350 | 43 | 9.5 | 5.5 |
| default_vegetation | EPSG:3857 | 16 | 16 | 34985 | 22085 | 44 | 9.3 | 5.0 |
| default_vegetation | EPSG:3857 | 18 | 18 | 137317 | 89546 | 46 | 10.6 | 0.3 |
| default_vegetation | EPSG:3857 | 18 | 18 | 137380 | 86898 | 53 | 11.4 | 2.3 |
| default_vegetation | EPSG:3857 | 18 | 18 | 140341 | 87356 | 50 | 14.6 | 1.7 |
| default_vegetation | EPSG:3857 | 18 | 18 | 137052 | 86460 | 55 | 11.4 | 0.7 |
| default_vegetation | EPSG:3857 | 18 | 18 | 137079 | 85468 | 51 | 11.8 | 0.4 |
| flora_max | EPSG:3857 | 8 | 8 | 135 | 87 | 261 | 10.7 | 50.3 |
| flora_max | EPSG:3857 | 8 | 8 | 134 | 86 | 236 | 9.4 | 49.6 |
| flora_max | EPSG:3857 | 8 | 8 | 136 | 84 | 260 | 10.4 | 48.7 |
| flora_max | EPSG:3857 | 8 | 8 | 136 | 87 | 232 | 9.5 | 48.5 |
| flora_max | EPSG:3857 | 8 | 8 | 134 | 85 | 227 | 7.8 | 49.4 |
| flora_max | EPSG:3857 | 10 | 10 | 535 | 347 | 416 | 8.5 | 42.2 |
| flora_max | EPSG:3857 | 10 | 10 | 543 | 340 | 195 | 8.5 | 36.1 |
| flora_max | EPSG:3857 | 10 | 10 | 538 | 340 | 267 | 8.2 | 38.7 |
| flora_max | EPSG:3857 | 10 | 10 | 545 | 350 | 210 | 9.4 | 37.8 |
| flora_max | EPSG:3857 | 10 | 10 | 545 | 338 | 218 | 8.7 | 35.0 |
| flora_max | EPSG:3857 | 12 | 12 | 2158 | 1391 | 89 | 10.9 | 29.2 |
| flora_max | EPSG:3857 | 12 | 12 | 2190 | 1378 | 108 | 7.6 | 33.7 |
| flora_max | EPSG:3857 | 12 | 12 | 2145 | 1395 | 129 | 8.1 | 25.8 |
| flora_max | EPSG:3857 | 12 | 12 | 2185 | 1359 | 80 | 8.1 | 23.8 |
| flora_max | EPSG:3857 | 12 | 12 | 2182 | 1350 | 67 | 8.8 | 15.0 |
| flora_max | EPSG:3857 | 13 | 13 | 4337 | 2664 | 71 | 9.3 | 14.3 |
| flora_max | EPSG:3857 | 13 | 13 | 4321 | 2726 | 104 | 9.4 | 23.2 |
| flora_max | EPSG:3857 | 13 | 13 | 4368 | 2716 | 68 | 8.7 | 9.9 |
| flora_max | EPSG:3857 | 13 | 13 | 4371 | 2722 | 78 | 9.2 | 15.8 |
| flora_max | EPSG:3857 | 13 | 13 | 4355 | 2798 | 88 | 7.9 | 26.7 |
| flora_max | EPSG:3857 | 14 | 14 | 8610 | 5528 | 84 | 10.3 | 14.5 |
| flora_max | EPSG:3857 | 14 | 14 | 8580 | 5544 | 123 | 12.1 | 29.7 |
| flora_max | EPSG:3857 | 14 | 14 | 8584 | 5531 | 77 | 9.5 | 11.9 |
| flora_max | EPSG:3857 | 14 | 14 | 8640 | 5551 | 76 | 10.0 | 8.4 |
| flora_max | EPSG:3857 | 14 | 14 | 8619 | 5339 | 63 | 10.5 | 13.3 |
| flora_max | EPSG:3857 | 16 | 16 | 34794 | 21746 | 77 | 10.0 | 10.7 |
| flora_max | EPSG:3857 | 16 | 16 | 34396 | 21605 | 75 | 9.6 | 8.2 |
| flora_max | EPSG:3857 | 16 | 16 | 34718 | 21657 | 74 | 10.0 | 17.5 |
| flora_max | EPSG:3857 | 16 | 16 | 34429 | 21350 | 72 | 9.2 | 13.0 |
| flora_max | EPSG:3857 | 16 | 16 | 34985 | 22085 | 91 | 9.6 | 19.1 |
| flora_max | EPSG:3857 | 18 | 18 | 137317 | 89546 | 64 | 10.4 | 1.9 |
| flora_max | EPSG:3857 | 18 | 18 | 137380 | 86898 | 75 | 11.2 | 6.5 |
| flora_max | EPSG:3857 | 18 | 18 | 140341 | 87356 | 71 | 10.9 | 2.7 |
| flora_max | EPSG:3857 | 18 | 18 | 137052 | 86460 | 84 | 9.5 | 8.3 |
| flora_max | EPSG:3857 | 18 | 18 | 137079 | 85468 | 72 | 32.4 | 7.2 |
| flora_min | EPSG:3857 | 8 | 8 | 135 | 87 | 119 | 9.7 | 21.6 |
| flora_min | EPSG:3857 | 8 | 8 | 134 | 86 | 167 | 8.6 | 25.1 |
| flora_min | EPSG:3857 | 8 | 8 | 136 | 84 | 108 | 9.9 | 20.7 |
| flora_min | EPSG:3857 | 8 | 8 | 136 | 87 | 99 | 8.9 | 19.2 |
| flora_min | EPSG:3857 | 8 | 8 | 134 | 85 | 117 | 8.3 | 22.5 |
| flora_min | EPSG:3857 | 10 | 10 | 535 | 347 | 284 | 13.3 | 27.4 |
| flora_min | EPSG:3857 | 10 | 10 | 543 | 340 | 145 | 11.2 | 17.0 |
| flora_min | EPSG:3857 | 10 | 10 | 538 | 340 | 178 | 8.5 | 23.0 |
| flora_min | EPSG:3857 | 10 | 10 | 545 | 350 | 128 | 8.2 | 17.4 |
| flora_min | EPSG:3857 | 10 | 10 | 545 | 338 | 144 | 9.4 | 21.2 |
| flora_min | EPSG:3857 | 12 | 12 | 2158 | 1391 | 45 | 12.0 | 7.8 |
| flora_min | EPSG:3857 | 12 | 12 | 2190 | 1378 | 59 | 9.2 | 16.8 |
| flora_min | EPSG:3857 | 12 | 12 | 2145 | 1395 | 103 | 11.3 | 15.0 |
| flora_min | EPSG:3857 | 12 | 12 | 2185 | 1359 | 64 | 11.3 | 13.9 |
| flora_min | EPSG:3857 | 12 | 12 | 2182 | 1350 | 48 | 11.2 | 7.1 |
| flora_min | EPSG:3857 | 13 | 13 | 4337 | 2664 | 42 | 10.5 | 4.4 |
| flora_min | EPSG:3857 | 13 | 13 | 4321 | 2726 | 63 | 10.9 | 9.6 |
| flora_min | EPSG:3857 | 13 | 13 | 4368 | 2716 | 35 | 8.6 | 4.3 |
| flora_min | EPSG:3857 | 13 | 13 | 4371 | 2722 | 43 | 10.8 | 5.9 |
| flora_min | EPSG:3857 | 13 | 13 | 4355 | 2798 | 66 | 12.0 | 8.9 |
| flora_min | EPSG:3857 | 14 | 14 | 8610 | 5528 | 36 | 7.9 | 3.7 |
| flora_min | EPSG:3857 | 14 | 14 | 8580 | 5544 | 51 | 11.7 | 6.9 |
| flora_min | EPSG:3857 | 14 | 14 | 8584 | 5531 | 48 | 11.5 | 0.3 |
| flora_min | EPSG:3857 | 14 | 14 | 8640 | 5551 | 38 | 8.9 | 0.1 |
| flora_min | EPSG:3857 | 14 | 14 | 8619 | 5339 | 39 | 9.5 | 3.9 |
| flora_min | EPSG:3857 | 16 | 16 | 34794 | 21746 | 44 | 9.9 | 3.4 |
| flora_min | EPSG:3857 | 16 | 16 | 34396 | 21605 | 42 | 10.3 | 4.0 |
| flora_min | EPSG:3857 | 16 | 16 | 34718 | 21657 | 48 | 9.5 | 9.6 |
| flora_min | EPSG:3857 | 16 | 16 | 34429 | 21350 | 46 | 8.9 | 5.6 |
| flora_min | EPSG:3857 | 16 | 16 | 34985 | 22085 | 40 | 8.8 | 7.7 |
| flora_min | EPSG:3857 | 18 | 18 | 137317 | 89546 | 37 | 13.1 | 0.1 |
| flora_min | EPSG:3857 | 18 | 18 | 137380 | 86898 | 41 | 11.0 | 2.1 |
| flora_min | EPSG:3857 | 18 | 18 | 140341 | 87356 | 40 | 11.3 | 0.3 |
| flora_min | EPSG:3857 | 18 | 18 | 137052 | 86460 | 42 | 11.9 | 2.3 |
| flora_min | EPSG:3857 | 18 | 18 | 137079 | 85468 | 46 | 9.2 | 3.7 |
| flora_nav | EPSG:3857 | 8 | 8 | 135 | 87 | 164 | 8.6 | 24.1 |
| flora_nav | EPSG:3857 | 8 | 8 | 134 | 86 | 158 | 8.7 | 27.9 |
| flora_nav | EPSG:3857 | 8 | 8 | 136 | 84 | 129 | 8.4 | 24.0 |
| flora_nav | EPSG:3857 | 8 | 8 | 136 | 87 | 124 | 8.5 | 20.9 |
| flora_nav | EPSG:3857 | 8 | 8 | 134 | 85 | 127 | 8.2 | 24.4 |
| flora_nav | EPSG:3857 | 10 | 10 | 535 | 347 | 286 | 8.1 | 29.1 |
| flora_nav | EPSG:3857 | 10 | 10 | 543 | 340 | 133 | 8.0 | 17.5 |
| flora_nav | EPSG:3857 | 10 | 10 | 538 | 340 | 171 | 8.6 | 23.9 |
| flora_nav | EPSG:3857 | 10 | 10 | 545 | 350 | 112 | 8.8 | 17.6 |
| flora_nav | EPSG:3857 | 10 | 10 | 545 | 338 | 152 | 10.0 | 23.2 |
| flora_nav | EPSG:3857 | 12 | 12 | 2158 | 1391 | 46 | 10.8 | 8.0 |
| flora_nav | EPSG:3857 | 12 | 12 | 2190 | 1378 | 61 | 10.6 | 17.0 |
| flora_nav | EPSG:3857 | 12 | 12 | 2145 | 1395 | 115 | 10.7 | 15.5 |
| flora_nav | EPSG:3857 | 12 | 12 | 2185 | 1359 | 70 | 9.0 | 14.7 |
| flora_nav | EPSG:3857 | 12 | 12 | 2182 | 1350 | 48 | 11.1 | 7.9 |
| flora_nav | EPSG:3857 | 13 | 13 | 4337 | 2664 | 46 | 9.2 | 4.6 |
| flora_nav | EPSG:3857 | 13 | 13 | 4321 | 2726 | 69 | 13.6 | 11.1 |
| flora_nav | EPSG:3857 | 13 | 13 | 4368 | 2716 | 46 | 10.2 | 4.8 |
| flora_nav | EPSG:3857 | 13 | 13 | 4371 | 2722 | 57 | 9.1 | 7.7 |
| flora_nav | EPSG:3857 | 13 | 13 | 4355 | 2798 | 54 | 9.1 | 9.2 |
| flora_nav | EPSG:3857 | 14 | 14 | 8610 | 5528 | 51 | 10.2 | 4.3 |
| flora_nav | EPSG:3857 | 14 | 14 | 8580 | 5544 | 65 | 8.4 | 14.5 |
| flora_nav | EPSG:3857 | 14 | 14 | 8584 | 5531 | 45 | 9.1 | 0.4 |
| flora_nav | EPSG:3857 | 14 | 14 | 8640 | 5551 | 36 | 9.2 | 0.1 |
| flora_nav | EPSG:3857 | 14 | 14 | 8619 | 5339 | 40 | 9.6 | 4.5 |
| flora_nav | EPSG:3857 | 16 | 16 | 34794 | 21746 | 44 | 9.5 | 4.2 |
| flora_nav | EPSG:3857 | 16 | 16 | 34396 | 21605 | 46 | 9.9 | 4.3 |
| flora_nav | EPSG:3857 | 16 | 16 | 34718 | 21657 | 57 | 8.6 | 16.8 |
| flora_nav | EPSG:3857 | 16 | 16 | 34429 | 21350 | 47 | 8.8 | 9.6 |
| flora_nav | EPSG:3857 | 16 | 16 | 34985 | 22085 | 50 | 7.7 | 18.5 |
| flora_nav | EPSG:3857 | 18 | 18 | 137317 | 89546 | 35 | 11.0 | 0.7 |
| flora_nav | EPSG:3857 | 18 | 18 | 137380 | 86898 | 48 | 11.5 | 3.9 |
| flora_nav | EPSG:3857 | 18 | 18 | 140341 | 87356 | 42 | 9.2 | 0.9 |
| flora_nav | EPSG:3857 | 18 | 18 | 137052 | 86460 | 50 | 9.5 | 6.3 |
| flora_nav | EPSG:3857 | 18 | 18 | 137079 | 85468 | 52 | 9.0 | 7.2 |
| flora_std | EPSG:3857 | 8 | 8 | 135 | 87 | 240 | 8.4 | 50.3 |
| flora_std | EPSG:3857 | 8 | 8 | 134 | 86 | 244 | 7.7 | 49.6 |
| flora_std | EPSG:3857 | 8 | 8 | 136 | 84 | 239 | 7.7 | 48.7 |
| flora_std | EPSG:3857 | 8 | 8 | 136 | 87 | 220 | 8.2 | 48.5 |
| flora_std | EPSG:3857 | 8 | 8 | 134 | 85 | 222 | 8.4 | 49.4 |
| flora_std | EPSG:3857 | 10 | 10 | 535 | 347 | 431 | 8.7 | 42.2 |
| flora_std | EPSG:3857 | 10 | 10 | 543 | 340 | 220 | 8.3 | 35.8 |
| flora_std | EPSG:3857 | 10 | 10 | 538 | 340 | 258 | 8.2 | 38.7 |
| flora_std | EPSG:3857 | 10 | 10 | 545 | 350 | 200 | 9.5 | 31.7 |
| flora_std | EPSG:3857 | 10 | 10 | 545 | 338 | 205 | 9.2 | 35.0 |
| flora_std | EPSG:3857 | 12 | 12 | 2158 | 1391 | 69 | 8.4 | 23.4 |
| flora_std | EPSG:3857 | 12 | 12 | 2190 | 1378 | 99 | 9.8 | 31.1 |
| flora_std | EPSG:3857 | 12 | 12 | 2145 | 1395 | 116 | 9.5 | 21.5 |
| flora_std | EPSG:3857 | 12 | 12 | 2185 | 1359 | 73 | 9.4 | 23.8 |
| flora_std | EPSG:3857 | 12 | 12 | 2182 | 1350 | 63 | 10.6 | 15.0 |
| flora_std | EPSG:3857 | 13 | 13 | 4337 | 2664 | 67 | 8.6 | 14.0 |
| flora_std | EPSG:3857 | 13 | 13 | 4321 | 2726 | 103 | 8.5 | 21.7 |
| flora_std | EPSG:3857 | 13 | 13 | 4368 | 2716 | 63 | 10.1 | 9.5 |
| flora_std | EPSG:3857 | 13 | 13 | 4371 | 2722 | 68 | 12.7 | 14.3 |
| flora_std | EPSG:3857 | 13 | 13 | 4355 | 2798 | 91 | 8.9 | 22.9 |
| flora_std | EPSG:3857 | 14 | 14 | 8610 | 5528 | 69 | 12.3 | 13.1 |
| flora_std | EPSG:3857 | 14 | 14 | 8580 | 5544 | 93 | 8.9 | 29.2 |
| flora_std | EPSG:3857 | 14 | 14 | 8584 | 5531 | 56 | 9.3 | 10.1 |
| flora_std | EPSG:3857 | 14 | 14 | 8640 | 5551 | 57 | 10.3 | 5.3 |
| flora_std | EPSG:3857 | 14 | 14 | 8619 | 5339 | 62 | 9.7 | 11.5 |
| flora_std | EPSG:3857 | 16 | 16 | 34794 | 21746 | 57 | 8.7 | 9.0 |
| flora_std | EPSG:3857 | 16 | 16 | 34396 | 21605 | 56 | 9.2 | 8.1 |
| flora_std | EPSG:3857 | 16 | 16 | 34718 | 21657 | 63 | 9.1 | 17.5 |
| flora_std | EPSG:3857 | 16 | 16 | 34429 | 21350 | 56 | 8.1 | 13.0 |
| flora_std | EPSG:3857 | 16 | 16 | 34985 | 22085 | 61 | 8.0 | 19.1 |
| flora_std | EPSG:3857 | 18 | 18 | 137317 | 89546 | 52 | 9.1 | 1.9 |
| flora_std | EPSG:3857 | 18 | 18 | 137380 | 86898 | 62 | 11.1 | 4.4 |
| flora_std | EPSG:3857 | 18 | 18 | 140341 | 87356 | 61 | 11.6 | 2.7 |
| flora_std | EPSG:3857 | 18 | 18 | 137052 | 86460 | 61 | 8.6 | 8.3 |
| flora_std | EPSG:3857 | 18 | 18 | 137079 | 85468 | 52 | 8.0 | 7.2 |
| flora_topographic | EPSG:3857 | 8 | 8 | 135 | 87 | 203 | 7.9 | 48.6 |
| flora_topographic | EPSG:3857 | 8 | 8 | 134 | 86 | 223 | 7.7 | 48.3 |
| flora_topographic | EPSG:3857 | 8 | 8 | 136 | 84 | 229 | 7.6 | 47.5 |
| flora_topographic | EPSG:3857 | 8 | 8 | 136 | 87 | 179 | 8.4 | 47.1 |
| flora_topographic | EPSG:3857 | 8 | 8 | 134 | 85 | 191 | 7.9 | 48.4 |
| flora_topographic | EPSG:3857 | 10 | 10 | 535 | 347 | 337 | 10.7 | 41.5 |
| flora_topographic | EPSG:3857 | 10 | 10 | 543 | 340 | 164 | 8.9 | 33.9 |
| flora_topographic | EPSG:3857 | 10 | 10 | 538 | 340 | 198 | 9.3 | 38.5 |
| flora_topographic | EPSG:3857 | 10 | 10 | 545 | 350 | 173 | 8.4 | 37.8 |
| flora_topographic | EPSG:3857 | 10 | 10 | 545 | 338 | 161 | 9.4 | 34.1 |
| flora_topographic | EPSG:3857 | 12 | 12 | 2158 | 1391 | 62 | 9.2 | 28.7 |
| flora_topographic | EPSG:3857 | 12 | 12 | 2190 | 1378 | 73 | 8.9 | 30.6 |
| flora_topographic | EPSG:3857 | 12 | 12 | 2145 | 1395 | 107 | 8.0 | 25.0 |
| flora_topographic | EPSG:3857 | 12 | 12 | 2185 | 1359 | 63 | 9.5 | 23.4 |
| flora_topographic | EPSG:3857 | 12 | 12 | 2182 | 1350 | 53 | 9.0 | 14.4 |
| flora_topographic | EPSG:3857 | 13 | 13 | 4337 | 2664 | 51 | 8.3 | 9.9 |
| flora_topographic | EPSG:3857 | 13 | 13 | 4321 | 2726 | 73 | 7.8 | 21.2 |
| flora_topographic | EPSG:3857 | 13 | 13 | 4368 | 2716 | 46 | 7.7 | 8.9 |
| flora_topographic | EPSG:3857 | 13 | 13 | 4371 | 2722 | 54 | 8.8 | 15.2 |
| flora_topographic | EPSG:3857 | 13 | 13 | 4355 | 2798 | 57 | 8.0 | 21.7 |
| flora_topographic | EPSG:3857 | 14 | 14 | 8610 | 5528 | 50 | 8.0 | 10.1 |
| flora_topographic | EPSG:3857 | 14 | 14 | 8580 | 5544 | 66 | 8.2 | 26.7 |
| flora_topographic | EPSG:3857 | 14 | 14 | 8584 | 5531 | 50 | 11.2 | 6.1 |
| flora_topographic | EPSG:3857 | 14 | 14 | 8640 | 5551 | 49 | 8.6 | 4.5 |
| flora_topographic | EPSG:3857 | 14 | 14 | 8619 | 5339 | 50 | 8.9 | 12.5 |
| flora_topographic | EPSG:3857 | 16 | 16 | 34794 | 21746 | 60 | 8.4 | 7.3 |
| flora_topographic | EPSG:3857 | 16 | 16 | 34396 | 21605 | 57 | 8.5 | 8.1 |
| flora_topographic | EPSG:3857 | 16 | 16 | 34718 | 21657 | 62 | 9.6 | 17.3 |
| flora_topographic | EPSG:3857 | 16 | 16 | 34429 | 21350 | 54 | 9.4 | 12.1 |
| flora_topographic | EPSG:3857 | 16 | 16 | 34985 | 22085 | 61 | 8.6 | 18.9 |
| flora_topographic | EPSG:3857 | 18 | 18 | 137317 | 89546 | 50 | 10.1 | 1.3 |
| flora_topographic | EPSG:3857 | 18 | 18 | 137380 | 86898 | 54 | 7.2 | 6.3 |
| flora_topographic | EPSG:3857 | 18 | 18 | 140341 | 87356 | 56 | 7.0 | 2.4 |
| flora_topographic | EPSG:3857 | 18 | 18 | 137052 | 86460 | 61 | 7.8 | 6.6 |
| flora_topographic | EPSG:3857 | 18 | 18 | 137079 | 85468 | 55 | 7.5 | 7.2 |
| flora_vegetation | EPSG:3857 | 8 | 8 | 135 | 87 | 245 | 7.7 | 48.6 |
| flora_vegetation | EPSG:3857 | 8 | 8 | 134 | 86 | 302 | 7.7 | 48.3 |
| flora_vegetation | EPSG:3857 | 8 | 8 | 136 | 84 | 258 | 7.9 | 47.5 |
| flora_vegetation | EPSG:3857 | 8 | 8 | 136 | 87 | 206 | 8.2 | 47.1 |
| flora_vegetation | EPSG:3857 | 8 | 8 | 134 | 85 | 189 | 6.5 | 48.4 |
| flora_vegetation | EPSG:3857 | 10 | 10 | 535 | 347 | 386 | 7.2 | 41.7 |
| flora_vegetation | EPSG:3857 | 10 | 10 | 543 | 340 | 187 | 7.5 | 35.3 |
| flora_vegetation | EPSG:3857 | 10 | 10 | 538 | 340 | 213 | 7.2 | 38.6 |
| flora_vegetation | EPSG:3857 | 10 | 10 | 545 | 350 | 151 | 7.1 | 31.6 |
| flora_vegetation | EPSG:3857 | 10 | 10 | 545 | 338 | 172 | 7.9 | 34.6 |
| flora_vegetation | EPSG:3857 | 12 | 12 | 2158 | 1391 | 56 | 8.0 | 22.1 |
| flora_vegetation | EPSG:3857 | 12 | 12 | 2190 | 1378 | 79 | 7.9 | 28.9 |
| flora_vegetation | EPSG:3857 | 12 | 12 | 2145 | 1395 | 101 | 7.8 | 18.5 |
| flora_vegetation | EPSG:3857 | 12 | 12 | 2185 | 1359 | 61 | 7.8 | 21.6 |
| flora_vegetation | EPSG:3857 | 12 | 12 | 2182 | 1350 | 75 | 7.6 | 13.9 |
| flora_vegetation | EPSG:3857 | 13 | 13 | 4337 | 2664 | 50 | 7.9 | 8.9 |
| flora_vegetation | EPSG:3857 | 13 | 13 | 4321 | 2726 | 85 | 7.9 | 17.7 |
| flora_vegetation | EPSG:3857 | 13 | 13 | 4368 | 2716 | 53 | 10.1 | 7.2 |
| flora_vegetation | EPSG:3857 | 13 | 13 | 4371 | 2722 | 64 | 9.6 | 11.8 |
| flora_vegetation | EPSG:3857 | 13 | 13 | 4355 | 2798 | 66 | 10.2 | 15.2 |
| flora_vegetation | EPSG:3857 | 14 | 14 | 8610 | 5528 | 53 | 9.9 | 7.0 |
| flora_vegetation | EPSG:3857 | 14 | 14 | 8580 | 5544 | 63 | 9.4 | 21.1 |
| flora_vegetation | EPSG:3857 | 14 | 14 | 8584 | 5531 | 51 | 10.2 | 2.9 |
| flora_vegetation | EPSG:3857 | 14 | 14 | 8640 | 5551 | 52 | 11.0 | 1.2 |
| flora_vegetation | EPSG:3857 | 14 | 14 | 8619 | 5339 | 48 | 9.5 | 9.4 |
| flora_vegetation | EPSG:3857 | 16 | 16 | 34794 | 21746 | 50 | 10.7 | 5.7 |
| flora_vegetation | EPSG:3857 | 16 | 16 | 34396 | 21605 | 58 | 8.7 | 6.5 |
| flora_vegetation | EPSG:3857 | 16 | 16 | 34718 | 21657 | 40 | 8.0 | 5.8 |
| flora_vegetation | EPSG:3857 | 16 | 16 | 34429 | 21350 | 42 | 9.4 | 5.5 |
| flora_vegetation | EPSG:3857 | 16 | 16 | 34985 | 22085 | 44 | 9.7 | 5.3 |
| flora_vegetation | EPSG:3857 | 18 | 18 | 137317 | 89546 | 39 | 7.0 | 0.5 |
| flora_vegetation | EPSG:3857 | 18 | 18 | 137380 | 86898 | 36 | 7.8 | 2.2 |
| flora_vegetation | EPSG:3857 | 18 | 18 | 140341 | 87356 | 38 | 10.0 | 2.0 |
| flora_vegetation | EPSG:3857 | 18 | 18 | 137052 | 86460 | 36 | 6.8 | 0.6 |
| flora_vegetation | EPSG:3857 | 18 | 18 | 137079 | 85468 | 30 | 6.6 | 0.6 |
| grayscale_max | EPSG:3857 | 8 | 8 | 135 | 87 | 180 | 7.8 | 32.9 |
| grayscale_max | EPSG:3857 | 8 | 8 | 134 | 86 | 197 | 7.0 | 33.8 |
| grayscale_max | EPSG:3857 | 8 | 8 | 136 | 84 | 194 | 6.7 | 29.8 |
| grayscale_max | EPSG:3857 | 8 | 8 | 136 | 87 | 164 | 7.6 | 31.6 |
| grayscale_max | EPSG:3857 | 8 | 8 | 134 | 85 | 181 | 7.2 | 32.2 |
| grayscale_max | EPSG:3857 | 10 | 10 | 535 | 347 | 358 | 7.1 | 32.9 |
| grayscale_max | EPSG:3857 | 10 | 10 | 543 | 340 | 168 | 7.9 | 26.9 |
| grayscale_max | EPSG:3857 | 10 | 10 | 538 | 340 | 218 | 7.5 | 27.9 |
| grayscale_max | EPSG:3857 | 10 | 10 | 545 | 350 | 164 | 7.5 | 30.2 |
| grayscale_max | EPSG:3857 | 10 | 10 | 545 | 338 | 180 | 8.2 | 24.4 |
| grayscale_max | EPSG:3857 | 12 | 12 | 2158 | 1391 | 72 | 8.1 | 20.8 |
| grayscale_max | EPSG:3857 | 12 | 12 | 2190 | 1378 | 158 | 10.7 | 27.3 |
| grayscale_max | EPSG:3857 | 12 | 12 | 2145 | 1395 | 118 | 7.5 | 21.5 |
| grayscale_max | EPSG:3857 | 12 | 12 | 2185 | 1359 | 63 | 7.8 | 18.6 |
| grayscale_max | EPSG:3857 | 12 | 12 | 2182 | 1350 | 61 | 9.0 | 10.7 |
| grayscale_max | EPSG:3857 | 13 | 13 | 4337 | 2664 | 61 | 7.9 | 11.1 |
| grayscale_max | EPSG:3857 | 13 | 13 | 4321 | 2726 | 82 | 6.9 | 18.4 |
| grayscale_max | EPSG:3857 | 13 | 13 | 4368 | 2716 | 48 | 7.2 | 7.5 |
| grayscale_max | EPSG:3857 | 13 | 13 | 4371 | 2722 | 61 | 6.9 | 12.4 |
| grayscale_max | EPSG:3857 | 13 | 13 | 4355 | 2798 | 62 | 7.5 | 21.9 |
| grayscale_max | EPSG:3857 | 14 | 14 | 8610 | 5528 | 55 | 8.0 | 11.7 |
| grayscale_max | EPSG:3857 | 14 | 14 | 8580 | 5544 | 70 | 7.3 | 23.2 |
| grayscale_max | EPSG:3857 | 14 | 14 | 8584 | 5531 | 56 | 7.7 | 9.7 |
| grayscale_max | EPSG:3857 | 14 | 14 | 8640 | 5551 | 51 | 8.5 | 7.0 |
| grayscale_max | EPSG:3857 | 14 | 14 | 8619 | 5339 | 62 | 9.9 | 9.7 |
| grayscale_max | EPSG:3857 | 16 | 16 | 34794 | 21746 | 58 | 7.9 | 8.6 |
| grayscale_max | EPSG:3857 | 16 | 16 | 34396 | 21605 | 63 | 8.5 | 5.4 |
| grayscale_max | EPSG:3857 | 16 | 16 | 34718 | 21657 | 59 | 8.2 | 13.6 |
| grayscale_max | EPSG:3857 | 16 | 16 | 34429 | 21350 | 53 | 8.9 | 9.9 |
| grayscale_max | EPSG:3857 | 16 | 16 | 34985 | 22085 | 66 | 10.4 | 15.3 |
| grayscale_max | EPSG:3857 | 18 | 18 | 137317 | 89546 | 56 | 10.6 | 1.5 |
| grayscale_max | EPSG:3857 | 18 | 18 | 137380 | 86898 | 57 | 8.1 | 5.1 |
| grayscale_max | EPSG:3857 | 18 | 18 | 140341 | 87356 | 48 | 7.2 | 2.3 |
| grayscale_max | EPSG:3857 | 18 | 18 | 137052 | 86460 | 63 | 7.4 | 7.4 |
| grayscale_max | EPSG:3857 | 18 | 18 | 137079 | 85468 | 50 | 7.7 | 6.3 |
| grayscale_min | EPSG:3857 | 8 | 8 | 135 | 87 | 106 | 9.2 | 17.3 |
| grayscale_min | EPSG:3857 | 8 | 8 | 134 | 86 | 147 | 8.2 | 20.0 |
| grayscale_min | EPSG:3857 | 8 | 8 | 136 | 84 | 89 | 8.2 | 16.0 |
| grayscale_min | EPSG:3857 | 8 | 8 | 136 | 87 | 86 | 7.8 | 15.3 |
| grayscale_min | EPSG:3857 | 8 | 8 | 134 | 85 | 92 | 9.6 | 17.7 |
| grayscale_min | EPSG:3857 | 10 | 10 | 535 | 347 | 259 | 9.8 | 23.8 |
| grayscale_min | EPSG:3857 | 10 | 10 | 543 | 340 | 150 | 10.2 | 14.0 |
| grayscale_min | EPSG:3857 | 10 | 10 | 538 | 340 | 153 | 10.2 | 18.8 |
| grayscale_min | EPSG:3857 | 10 | 10 | 545 | 350 | 120 | 10.6 | 14.2 |
| grayscale_min | EPSG:3857 | 10 | 10 | 545 | 338 | 156 | 8.9 | 17.7 |
| grayscale_min | EPSG:3857 | 12 | 12 | 2158 | 1391 | 36 | 8.2 | 6.3 |
| grayscale_min | EPSG:3857 | 12 | 12 | 2190 | 1378 | 49 | 7.7 | 13.7 |
| grayscale_min | EPSG:3857 | 12 | 12 | 2145 | 1395 | 77 | 8.9 | 12.9 |
| grayscale_min | EPSG:3857 | 12 | 12 | 2185 | 1359 | 48 | 8.1 | 11.3 |
| grayscale_min | EPSG:3857 | 12 | 12 | 2182 | 1350 | 34 | 8.2 | 5.5 |
| grayscale_min | EPSG:3857 | 13 | 13 | 4337 | 2664 | 33 | 8.8 | 3.4 |
| grayscale_min | EPSG:3857 | 13 | 13 | 4321 | 2726 | 48 | 7.7 | 7.9 |
| grayscale_min | EPSG:3857 | 13 | 13 | 4368 | 2716 | 31 | 9.6 | 3.6 |
| grayscale_min | EPSG:3857 | 13 | 13 | 4371 | 2722 | 37 | 8.9 | 5.1 |
| grayscale_min | EPSG:3857 | 13 | 13 | 4355 | 2798 | 41 | 9.6 | 7.3 |
| grayscale_min | EPSG:3857 | 14 | 14 | 8610 | 5528 | 36 | 9.1 | 3.0 |
| grayscale_min | EPSG:3857 | 14 | 14 | 8580 | 5544 | 45 | 10.0 | 5.7 |
| grayscale_min | EPSG:3857 | 14 | 14 | 8584 | 5531 | 34 | 11.1 | 0.3 |
| grayscale_min | EPSG:3857 | 14 | 14 | 8640 | 5551 | 33 | 10.4 | 0.1 |
| grayscale_min | EPSG:3857 | 14 | 14 | 8619 | 5339 | 35 | 9.1 | 3.3 |
| grayscale_min | EPSG:3857 | 16 | 16 | 34794 | 21746 | 39 | 8.9 | 2.7 |
| grayscale_min | EPSG:3857 | 16 | 16 | 34396 | 21605 | 36 | 9.4 | 3.4 |
| grayscale_min | EPSG:3857 | 16 | 16 | 34718 | 21657 | 48 | 9.4 | 7.4 |
| grayscale_min | EPSG:3857 | 16 | 16 | 34429 | 21350 | 35 | 7.6 | 4.4 |
| grayscale_min | EPSG:3857 | 16 | 16 | 34985 | 22085 | 40 | 9.6 | 6.4 |
| grayscale_min | EPSG:3857 | 18 | 18 | 137317 | 89546 | 32 | 10.0 | 0.1 |
| grayscale_min | EPSG:3857 | 18 | 18 | 137380 | 86898 | 44 | 8.1 | 1.3 |
| grayscale_min | EPSG:3857 | 18 | 18 | 140341 | 87356 | 31 | 7.1 | 0.3 |
| grayscale_min | EPSG:3857 | 18 | 18 | 137052 | 86460 | 39 | 9.9 | 2.2 |
| grayscale_min | EPSG:3857 | 18 | 18 | 137079 | 85468 | 39 | 10.0 | 3.4 |
| grayscale_nav | EPSG:3857 | 8 | 8 | 135 | 87 | 151 | 8.4 | 19.3 |
| grayscale_nav | EPSG:3857 | 8 | 8 | 134 | 86 | 166 | 7.6 | 22.2 |
| grayscale_nav | EPSG:3857 | 8 | 8 | 136 | 84 | 125 | 8.4 | 19.1 |
| grayscale_nav | EPSG:3857 | 8 | 8 | 136 | 87 | 143 | 9.3 | 16.9 |
| grayscale_nav | EPSG:3857 | 8 | 8 | 134 | 85 | 164 | 11.0 | 19.1 |
| grayscale_nav | EPSG:3857 | 10 | 10 | 535 | 347 | 334 | 9.4 | 25.0 |
| grayscale_nav | EPSG:3857 | 10 | 10 | 543 | 340 | 163 | 12.0 | 14.4 |
| grayscale_nav | EPSG:3857 | 10 | 10 | 538 | 340 | 181 | 8.5 | 19.5 |
| grayscale_nav | EPSG:3857 | 10 | 10 | 545 | 350 | 144 | 11.0 | 14.4 |
| grayscale_nav | EPSG:3857 | 10 | 10 | 545 | 338 | 153 | 11.4 | 19.3 |
| grayscale_nav | EPSG:3857 | 12 | 12 | 2158 | 1391 | 56 | 11.5 | 6.4 |
| grayscale_nav | EPSG:3857 | 12 | 12 | 2190 | 1378 | 69 | 9.4 | 13.8 |
| grayscale_nav | EPSG:3857 | 12 | 12 | 2145 | 1395 | 105 | 9.7 | 13.3 |
| grayscale_nav | EPSG:3857 | 12 | 12 | 2185 | 1359 | 57 | 9.0 | 12.0 |
| grayscale_nav | EPSG:3857 | 12 | 12 | 2182 | 1350 | 43 | 8.6 | 6.0 |
| grayscale_nav | EPSG:3857 | 13 | 13 | 4337 | 2664 | 40 | 7.6 | 3.6 |
| grayscale_nav | EPSG:3857 | 13 | 13 | 4321 | 2726 | 70 | 9.7 | 9.1 |
| grayscale_nav | EPSG:3857 | 13 | 13 | 4368 | 2716 | 45 | 10.5 | 4.0 |
| grayscale_nav | EPSG:3857 | 13 | 13 | 4371 | 2722 | 57 | 9.5 | 6.3 |
| grayscale_nav | EPSG:3857 | 13 | 13 | 4355 | 2798 | 51 | 9.4 | 7.6 |
| grayscale_nav | EPSG:3857 | 14 | 14 | 8610 | 5528 | 44 | 9.0 | 3.4 |
| grayscale_nav | EPSG:3857 | 14 | 14 | 8580 | 5544 | 66 | 8.7 | 11.6 |
| grayscale_nav | EPSG:3857 | 14 | 14 | 8584 | 5531 | 41 | 8.4 | 0.4 |
| grayscale_nav | EPSG:3857 | 14 | 14 | 8640 | 5551 | 36 | 8.9 | 0.1 |
| grayscale_nav | EPSG:3857 | 14 | 14 | 8619 | 5339 | 41 | 7.9 | 3.8 |
| grayscale_nav | EPSG:3857 | 16 | 16 | 34794 | 21746 | 45 | 8.7 | 3.3 |
| grayscale_nav | EPSG:3857 | 16 | 16 | 34396 | 21605 | 42 | 9.5 | 3.8 |
| grayscale_nav | EPSG:3857 | 16 | 16 | 34718 | 21657 | 55 | 8.3 | 13.3 |
| grayscale_nav | EPSG:3857 | 16 | 16 | 34429 | 21350 | 47 | 9.3 | 8.0 |
| grayscale_nav | EPSG:3857 | 16 | 16 | 34985 | 22085 | 56 | 10.0 | 15.0 |
| grayscale_nav | EPSG:3857 | 18 | 18 | 137317 | 89546 | 41 | 9.4 | 0.7 |
| grayscale_nav | EPSG:3857 | 18 | 18 | 137380 | 86898 | 44 | 8.8 | 3.1 |
| grayscale_nav | EPSG:3857 | 18 | 18 | 140341 | 87356 | 37 | 8.8 | 0.6 |
| grayscale_nav | EPSG:3857 | 18 | 18 | 137052 | 86460 | 42 | 9.3 | 5.8 |
| grayscale_nav | EPSG:3857 | 18 | 18 | 137079 | 85468 | 47 | 10.7 | 6.4 |
| grayscale_std | EPSG:3857 | 8 | 8 | 135 | 87 | 230 | 8.7 | 32.9 |
| grayscale_std | EPSG:3857 | 8 | 8 | 134 | 86 | 253 | 8.9 | 33.8 |
| grayscale_std | EPSG:3857 | 8 | 8 | 136 | 84 | 245 | 8.9 | 29.8 |
| grayscale_std | EPSG:3857 | 8 | 8 | 136 | 87 | 251 | 9.7 | 31.6 |
| grayscale_std | EPSG:3857 | 8 | 8 | 134 | 85 | 249 | 7.9 | 32.2 |
| grayscale_std | EPSG:3857 | 10 | 10 | 535 | 347 | 409 | 13.3 | 32.9 |
| grayscale_std | EPSG:3857 | 10 | 10 | 543 | 340 | 217 | 8.1 | 26.2 |
| grayscale_std | EPSG:3857 | 10 | 10 | 538 | 340 | 247 | 8.0 | 27.9 |
| grayscale_std | EPSG:3857 | 10 | 10 | 545 | 350 | 168 | 7.7 | 24.0 |
| grayscale_std | EPSG:3857 | 10 | 10 | 545 | 338 | 195 | 8.0 | 24.4 |
| grayscale_std | EPSG:3857 | 12 | 12 | 2158 | 1391 | 71 | 8.9 | 14.8 |
| grayscale_std | EPSG:3857 | 12 | 12 | 2190 | 1378 | 88 | 8.9 | 24.9 |
| grayscale_std | EPSG:3857 | 12 | 12 | 2145 | 1395 | 124 | 9.3 | 17.8 |
| grayscale_std | EPSG:3857 | 12 | 12 | 2185 | 1359 | 78 | 8.2 | 18.4 |
| grayscale_std | EPSG:3857 | 12 | 12 | 2182 | 1350 | 63 | 9.2 | 10.7 |
| grayscale_std | EPSG:3857 | 13 | 13 | 4337 | 2664 | 61 | 8.1 | 10.9 |
| grayscale_std | EPSG:3857 | 13 | 13 | 4321 | 2726 | 86 | 7.6 | 17.2 |
| grayscale_std | EPSG:3857 | 13 | 13 | 4368 | 2716 | 53 | 8.3 | 7.2 |
| grayscale_std | EPSG:3857 | 13 | 13 | 4371 | 2722 | 58 | 9.1 | 10.8 |
| grayscale_std | EPSG:3857 | 13 | 13 | 4355 | 2798 | 69 | 8.8 | 18.2 |
| grayscale_std | EPSG:3857 | 14 | 14 | 8610 | 5528 | 65 | 9.5 | 10.2 |
| grayscale_std | EPSG:3857 | 14 | 14 | 8580 | 5544 | 93 | 7.9 | 22.8 |
| grayscale_std | EPSG:3857 | 14 | 14 | 8584 | 5531 | 60 | 11.8 | 8.0 |
| grayscale_std | EPSG:3857 | 14 | 14 | 8640 | 5551 | 57 | 8.1 | 4.7 |
| grayscale_std | EPSG:3857 | 14 | 14 | 8619 | 5339 | 52 | 8.8 | 7.8 |
| grayscale_std | EPSG:3857 | 16 | 16 | 34794 | 21746 | 60 | 10.1 | 7.0 |
| grayscale_std | EPSG:3857 | 16 | 16 | 34396 | 21605 | 59 | 8.9 | 5.2 |
| grayscale_std | EPSG:3857 | 16 | 16 | 34718 | 21657 | 67 | 8.8 | 13.6 |
| grayscale_std | EPSG:3857 | 16 | 16 | 34429 | 21350 | 67 | 8.6 | 9.9 |
| grayscale_std | EPSG:3857 | 16 | 16 | 34985 | 22085 | 70 | 9.5 | 15.3 |
| grayscale_std | EPSG:3857 | 18 | 18 | 137317 | 89546 | 55 | 8.7 | 1.5 |
| grayscale_std | EPSG:3857 | 18 | 18 | 137380 | 86898 | 55 | 9.0 | 3.5 |
| grayscale_std | EPSG:3857 | 18 | 18 | 140341 | 87356 | 50 | 9.0 | 2.3 |
| grayscale_std | EPSG:3857 | 18 | 18 | 137052 | 86460 | 58 | 9.5 | 7.4 |
| grayscale_std | EPSG:3857 | 18 | 18 | 137079 | 85468 | 57 | 9.9 | 6.3 |
| grayscale_topographic | EPSG:3857 | 8 | 8 | 135 | 87 | 204 | 8.2 | 32.7 |
| grayscale_topographic | EPSG:3857 | 8 | 8 | 134 | 86 | 205 | 8.4 | 33.5 |
| grayscale_topographic | EPSG:3857 | 8 | 8 | 136 | 84 | 218 | 8.5 | 29.4 |
| grayscale_topographic | EPSG:3857 | 8 | 8 | 136 | 87 | 179 | 8.2 | 32.3 |
| grayscale_topographic | EPSG:3857 | 8 | 8 | 134 | 85 | 192 | 8.1 | 32.3 |
| grayscale_topographic | EPSG:3857 | 10 | 10 | 535 | 347 | 335 | 10.2 | 30.8 |
| grayscale_topographic | EPSG:3857 | 10 | 10 | 543 | 340 | 192 | 8.4 | 24.0 |
| grayscale_topographic | EPSG:3857 | 10 | 10 | 538 | 340 | 209 | 8.4 | 26.6 |
| grayscale_topographic | EPSG:3857 | 10 | 10 | 545 | 350 | 185 | 8.7 | 29.2 |
| grayscale_topographic | EPSG:3857 | 10 | 10 | 545 | 338 | 174 | 8.5 | 23.2 |
| grayscale_topographic | EPSG:3857 | 12 | 12 | 2158 | 1391 | 68 | 8.5 | 20.3 |
| grayscale_topographic | EPSG:3857 | 12 | 12 | 2190 | 1378 | 88 | 7.6 | 24.7 |
| grayscale_topographic | EPSG:3857 | 12 | 12 | 2145 | 1395 | 119 | 8.5 | 20.5 |
| grayscale_topographic | EPSG:3857 | 12 | 12 | 2185 | 1359 | 76 | 10.7 | 17.8 |
| grayscale_topographic | EPSG:3857 | 12 | 12 | 2182 | 1350 | 60 | 9.3 | 10.2 |
| grayscale_topographic | EPSG:3857 | 13 | 13 | 4337 | 2664 | 64 | 11.5 | 6.4 |
| grayscale_topographic | EPSG:3857 | 13 | 13 | 4321 | 2726 | 93 | 7.9 | 16.0 |
| grayscale_topographic | EPSG:3857 | 13 | 13 | 4368 | 2716 | 63 | 9.0 | 6.4 |
| grayscale_topographic | EPSG:3857 | 13 | 13 | 4371 | 2722 | 79 | 10.4 | 11.5 |
| grayscale_topographic | EPSG:3857 | 13 | 13 | 4355 | 2798 | 88 | 9.2 | 17.2 |
| grayscale_topographic | EPSG:3857 | 14 | 14 | 8610 | 5528 | 64 | 10.1 | 7.3 |
| grayscale_topographic | EPSG:3857 | 14 | 14 | 8580 | 5544 | 83 | 8.0 | 19.5 |
| grayscale_topographic | EPSG:3857 | 14 | 14 | 8584 | 5531 | 64 | 10.0 | 4.2 |
| grayscale_topographic | EPSG:3857 | 14 | 14 | 8640 | 5551 | 62 | 9.2 | 3.7 |
| grayscale_topographic | EPSG:3857 | 14 | 14 | 8619 | 5339 | 65 | 9.0 | 8.1 |
| grayscale_topographic | EPSG:3857 | 16 | 16 | 34794 | 21746 | 65 | 8.3 | 5.5 |
| grayscale_topographic | EPSG:3857 | 16 | 16 | 34396 | 21605 | 60 | 9.3 | 5.3 |
| grayscale_topographic | EPSG:3857 | 16 | 16 | 34718 | 21657 | 72 | 9.0 | 13.4 |
| grayscale_topographic | EPSG:3857 | 16 | 16 | 34429 | 21350 | 66 | 9.2 | 9.2 |
| grayscale_topographic | EPSG:3857 | 16 | 16 | 34985 | 22085 | 81 | 9.1 | 15.0 |
| grayscale_topographic | EPSG:3857 | 18 | 18 | 137317 | 89546 | 59 | 9.4 | 0.8 |
| grayscale_topographic | EPSG:3857 | 18 | 18 | 137380 | 86898 | 62 | 8.6 | 4.9 |
| grayscale_topographic | EPSG:3857 | 18 | 18 | 140341 | 87356 | 58 | 8.8 | 1.6 |
| grayscale_topographic | EPSG:3857 | 18 | 18 | 137052 | 86460 | 67 | 9.5 | 5.9 |
| grayscale_topographic | EPSG:3857 | 18 | 18 | 137079 | 85468 | 64 | 10.6 | 6.3 |
| grayscale_vegetation | EPSG:3857 | 8 | 8 | 135 | 87 | 216 | 8.2 | 31.6 |
| grayscale_vegetation | EPSG:3857 | 8 | 8 | 134 | 86 | 292 | 7.7 | 32.8 |
| grayscale_vegetation | EPSG:3857 | 8 | 8 | 136 | 84 | 233 | 7.6 | 28.7 |
| grayscale_vegetation | EPSG:3857 | 8 | 8 | 136 | 87 | 200 | 7.9 | 30.2 |
| grayscale_vegetation | EPSG:3857 | 8 | 8 | 134 | 85 | 221 | 9.3 | 31.3 |
| grayscale_vegetation | EPSG:3857 | 10 | 10 | 535 | 347 | 378 | 7.4 | 32.3 |
| grayscale_vegetation | EPSG:3857 | 10 | 10 | 543 | 340 | 195 | 8.3 | 25.8 |
| grayscale_vegetation | EPSG:3857 | 10 | 10 | 538 | 340 | 231 | 8.0 | 27.8 |
| grayscale_vegetation | EPSG:3857 | 10 | 10 | 545 | 350 | 186 | 8.3 | 23.8 |
| grayscale_vegetation | EPSG:3857 | 10 | 10 | 545 | 338 | 168 | 7.8 | 24.0 |
| grayscale_vegetation | EPSG:3857 | 12 | 12 | 2158 | 1391 | 56 | 7.9 | 12.3 |
| grayscale_vegetation | EPSG:3857 | 12 | 12 | 2190 | 1378 | 70 | 8.6 | 22.8 |
| grayscale_vegetation | EPSG:3857 | 12 | 12 | 2145 | 1395 | 115 | 9.3 | 14.6 |
| grayscale_vegetation | EPSG:3857 | 12 | 12 | 2185 | 1359 | 71 | 9.1 | 16.2 |
| grayscale_vegetation | EPSG:3857 | 12 | 12 | 2182 | 1350 | 63 | 9.2 | 9.7 |
| grayscale_vegetation | EPSG:3857 | 13 | 13 | 4337 | 2664 | 54 | 7.4 | 5.3 |
| grayscale_vegetation | EPSG:3857 | 13 | 13 | 4321 | 2726 | 75 | 7.7 | 12.6 |
| grayscale_vegetation | EPSG:3857 | 13 | 13 | 4368 | 2716 | 56 | 8.8 | 4.8 |
| grayscale_vegetation | EPSG:3857 | 13 | 13 | 4371 | 2722 | 61 | 9.4 | 8.4 |
| grayscale_vegetation | EPSG:3857 | 13 | 13 | 4355 | 2798 | 53 | 8.8 | 10.9 |
| grayscale_vegetation | EPSG:3857 | 14 | 14 | 8610 | 5528 | 58 | 10.2 | 4.5 |
| grayscale_vegetation | EPSG:3857 | 14 | 14 | 8580 | 5544 | 70 | 10.1 | 14.7 |
| grayscale_vegetation | EPSG:3857 | 14 | 14 | 8584 | 5531 | 62 | 7.6 | 1.8 |
| grayscale_vegetation | EPSG:3857 | 14 | 14 | 8640 | 5551 | 42 | 7.9 | 1.1 |
| grayscale_vegetation | EPSG:3857 | 14 | 14 | 8619 | 5339 | 42 | 8.2 | 4.7 |
| grayscale_vegetation | EPSG:3857 | 16 | 16 | 34794 | 21746 | 44 | 8.4 | 4.2 |
| grayscale_vegetation | EPSG:3857 | 16 | 16 | 34396 | 21605 | 52 | 9.4 | 3.4 |
| grayscale_vegetation | EPSG:3857 | 16 | 16 | 34718 | 21657 | 49 | 9.7 | 4.1 |
| grayscale_vegetation | EPSG:3857 | 16 | 16 | 34429 | 21350 | 48 | 9.9 | 3.6 |
| grayscale_vegetation | EPSG:3857 | 16 | 16 | 34985 | 22085 | 46 | 8.4 | 3.7 |
| grayscale_vegetation | EPSG:3857 | 18 | 18 | 137317 | 89546 | 42 | 9.9 | 0.3 |
| grayscale_vegetation | EPSG:3857 | 18 | 18 | 137380 | 86898 | 45 | 8.0 | 1.5 |
| grayscale_vegetation | EPSG:3857 | 18 | 18 | 140341 | 87356 | 41 | 8.3 | 1.4 |
| grayscale_vegetation | EPSG:3857 | 18 | 18 | 137052 | 86460 | 46 | 11.2 | 0.4 |
| grayscale_vegetation | EPSG:3857 | 18 | 18 | 137079 | 85468 | 49 | 11.7 | 0.4 |
| hico_max | EPSG:3857 | 8 | 8 | 135 | 87 | 261 | 8.3 | 45.6 |
| hico_max | EPSG:3857 | 8 | 8 | 134 | 86 | 254 | 8.0 | 45.1 |
| hico_max | EPSG:3857 | 8 | 8 | 136 | 84 | 253 | 9.1 | 43.1 |
| hico_max | EPSG:3857 | 8 | 8 | 136 | 87 | 209 | 8.2 | 44.7 |
| hico_max | EPSG:3857 | 8 | 8 | 134 | 85 | 228 | 8.5 | 45.9 |
| hico_max | EPSG:3857 | 10 | 10 | 535 | 347 | 430 | 9.0 | 38.0 |
| hico_max | EPSG:3857 | 10 | 10 | 543 | 340 | 216 | 9.1 | 34.6 |
| hico_max | EPSG:3857 | 10 | 10 | 538 | 340 | 296 | 9.7 | 36.5 |
| hico_max | EPSG:3857 | 10 | 10 | 545 | 350 | 197 | 7.2 | 35.9 |
| hico_max | EPSG:3857 | 10 | 10 | 545 | 338 | 182 | 7.4 | 34.2 |
| hico_max | EPSG:3857 | 12 | 12 | 2158 | 1391 | 68 | 7.1 | 28.6 |
| hico_max | EPSG:3857 | 12 | 12 | 2190 | 1378 | 86 | 7.3 | 31.7 |
| hico_max | EPSG:3857 | 12 | 12 | 2145 | 1395 | 133 | 9.0 | 25.7 |
| hico_max | EPSG:3857 | 12 | 12 | 2185 | 1359 | 82 | 8.8 | 23.8 |
| hico_max | EPSG:3857 | 12 | 12 | 2182 | 1350 | 68 | 12.0 | 15.5 |
| hico_max | EPSG:3857 | 13 | 13 | 4337 | 2664 | 79 | 7.5 | 14.6 |
| hico_max | EPSG:3857 | 13 | 13 | 4321 | 2726 | 96 | 7.3 | 23.4 |
| hico_max | EPSG:3857 | 13 | 13 | 4368 | 2716 | 71 | 8.3 | 10.5 |
| hico_max | EPSG:3857 | 13 | 13 | 4371 | 2722 | 81 | 8.7 | 16.5 |
| hico_max | EPSG:3857 | 13 | 13 | 4355 | 2798 | 90 | 10.6 | 26.5 |
| hico_max | EPSG:3857 | 14 | 14 | 8610 | 5528 | 82 | 12.3 | 14.7 |
| hico_max | EPSG:3857 | 14 | 14 | 8580 | 5544 | 110 | 8.7 | 29.6 |
| hico_max | EPSG:3857 | 14 | 14 | 8584 | 5531 | 80 | 9.0 | 12.8 |
| hico_max | EPSG:3857 | 14 | 14 | 8640 | 5551 | 82 | 11.6 | 9.0 |
| hico_max | EPSG:3857 | 14 | 14 | 8619 | 5339 | 73 | 11.9 | 14.1 |
| hico_max | EPSG:3857 | 16 | 16 | 34794 | 21746 | 90 | 13.3 | 10.2 |
| hico_max | EPSG:3857 | 16 | 16 | 34396 | 21605 | 83 | 10.0 | 9.2 |
| hico_max | EPSG:3857 | 16 | 16 | 34718 | 21657 | 76 | 8.2 | 19.4 |
| hico_max | EPSG:3857 | 16 | 16 | 34429 | 21350 | 73 | 10.2 | 13.9 |
| hico_max | EPSG:3857 | 16 | 16 | 34985 | 22085 | 84 | 8.6 | 21.4 |
| hico_max | EPSG:3857 | 18 | 18 | 137317 | 89546 | 56 | 8.2 | 2.1 |
| hico_max | EPSG:3857 | 18 | 18 | 137380 | 86898 | 63 | 9.9 | 7.2 |
| hico_max | EPSG:3857 | 18 | 18 | 140341 | 87356 | 65 | 9.6 | 3.3 |
| hico_max | EPSG:3857 | 18 | 18 | 137052 | 86460 | 72 | 10.9 | 9.3 |
| hico_max | EPSG:3857 | 18 | 18 | 137079 | 85468 | 77 | 9.8 | 9.2 |
| hico_min | EPSG:3857 | 8 | 8 | 135 | 87 | 136 | 7.9 | 21.1 |
| hico_min | EPSG:3857 | 8 | 8 | 134 | 86 | 188 | 8.4 | 23.8 |
| hico_min | EPSG:3857 | 8 | 8 | 136 | 84 | 115 | 7.8 | 19.7 |
| hico_min | EPSG:3857 | 8 | 8 | 136 | 87 | 85 | 7.8 | 18.3 |
| hico_min | EPSG:3857 | 8 | 8 | 134 | 85 | 102 | 6.9 | 22.6 |
| hico_min | EPSG:3857 | 10 | 10 | 535 | 347 | 251 | 7.2 | 26.7 |
| hico_min | EPSG:3857 | 10 | 10 | 543 | 340 | 132 | 7.9 | 18.0 |
| hico_min | EPSG:3857 | 10 | 10 | 538 | 340 | 165 | 11.4 | 23.8 |
| hico_min | EPSG:3857 | 10 | 10 | 545 | 350 | 148 | 8.2 | 18.8 |
| hico_min | EPSG:3857 | 10 | 10 | 545 | 338 | 147 | 7.7 | 22.6 |
| hico_min | EPSG:3857 | 12 | 12 | 2158 | 1391 | 45 | 8.4 | 8.6 |
| hico_min | EPSG:3857 | 12 | 12 | 2190 | 1378 | 60 | 10.9 | 16.9 |
| hico_min | EPSG:3857 | 12 | 12 | 2145 | 1395 | 95 | 9.9 | 15.8 |
| hico_min | EPSG:3857 | 12 | 12 | 2185 | 1359 | 82 | 9.5 | 14.4 |
| hico_min | EPSG:3857 | 12 | 12 | 2182 | 1350 | 47 | 10.4 | 8.3 |
| hico_min | EPSG:3857 | 13 | 13 | 4337 | 2664 | 42 | 10.1 | 4.9 |
| hico_min | EPSG:3857 | 13 | 13 | 4321 | 2726 | 63 | 10.3 | 11.0 |
| hico_min | EPSG:3857 | 13 | 13 | 4368 | 2716 | 47 | 10.0 | 4.6 |
| hico_min | EPSG:3857 | 13 | 13 | 4371 | 2722 | 47 | 10.6 | 6.7 |
| hico_min | EPSG:3857 | 13 | 13 | 4355 | 2798 | 55 | 11.5 | 9.5 |
| hico_min | EPSG:3857 | 14 | 14 | 8610 | 5528 | 48 | 10.5 | 4.4 |
| hico_min | EPSG:3857 | 14 | 14 | 8580 | 5544 | 55 | 10.3 | 8.5 |
| hico_min | EPSG:3857 | 14 | 14 | 8584 | 5531 | 48 | 10.6 | 0.7 |
| hico_min | EPSG:3857 | 14 | 14 | 8640 | 5551 | 35 | 9.6 | 0.1 |
| hico_min | EPSG:3857 | 14 | 14 | 8619 | 5339 | 41 | 10.3 | 4.7 |
| hico_min | EPSG:3857 | 16 | 16 | 34794 | 21746 | 51 | 12.2 | 4.2 |
| hico_min | EPSG:3857 | 16 | 16 | 34396 | 21605 | 38 | 9.6 | 4.4 |
| hico_min | EPSG:3857 | 16 | 16 | 34718 | 21657 | 46 | 10.5 | 10.6 |
| hico_min | EPSG:3857 | 16 | 16 | 34429 | 21350 | 36 | 9.0 | 6.5 |
| hico_min | EPSG:3857 | 16 | 16 | 34985 | 22085 | 36 | 8.6 | 8.1 |
| hico_min | EPSG:3857 | 18 | 18 | 137317 | 89546 | 27 | 8.8 | 0.1 |
| hico_min | EPSG:3857 | 18 | 18 | 137380 | 86898 | 30 | 7.3 | 1.8 |
| hico_min | EPSG:3857 | 18 | 18 | 140341 | 87356 | 35 | 8.1 | 0.8 |
| hico_min | EPSG:3857 | 18 | 18 | 137052 | 86460 | 40 | 9.4 | 2.8 |
| hico_min | EPSG:3857 | 18 | 18 | 137079 | 85468 | 41 | 12.1 | 4.1 |
| hico_nav | EPSG:3857 | 8 | 8 | 135 | 87 | 148 | 7.5 | 22.3 |
| hico_nav | EPSG:3857 | 8 | 8 | 134 | 86 | 156 | 7.6 | 25.5 |
| hico_nav | EPSG:3857 | 8 | 8 | 136 | 84 | 134 | 8.0 | 22.6 |
| hico_nav | EPSG:3857 | 8 | 8 | 136 | 87 | 136 | 8.5 | 19.7 |
| hico_nav | EPSG:3857 | 8 | 8 | 134 | 85 | 127 | 8.3 | 23.0 |
| hico_nav | EPSG:3857 | 10 | 10 | 535 | 347 | 287 | 7.5 | 28.3 |
| hico_nav | EPSG:3857 | 10 | 10 | 543 | 340 | 141 | 8.2 | 18.3 |
| hico_nav | EPSG:3857 | 10 | 10 | 538 | 340 | 149 | 6.9 | 24.4 |
| hico_nav | EPSG:3857 | 10 | 10 | 545 | 350 | 109 | 7.1 | 19.1 |
| hico_nav | EPSG:3857 | 10 | 10 | 545 | 338 | 128 | 7.0 | 24.4 |
| hico_nav | EPSG:3857 | 12 | 12 | 2158 | 1391 | 41 | 7.3 | 8.7 |
| hico_nav | EPSG:3857 | 12 | 12 | 2190 | 1378 | 58 | 7.7 | 16.9 |
| hico_nav | EPSG:3857 | 12 | 12 | 2145 | 1395 | 93 | 8.7 | 16.4 |
| hico_nav | EPSG:3857 | 12 | 12 | 2185 | 1359 | 52 | 7.2 | 15.0 |
| hico_nav | EPSG:3857 | 12 | 12 | 2182 | 1350 | 57 | 9.8 | 8.9 |
| hico_nav | EPSG:3857 | 13 | 13 | 4337 | 2664 | 54 | 9.0 | 5.1 |
| hico_nav | EPSG:3857 | 13 | 13 | 4321 | 2726 | 65 | 7.9 | 12.3 |
| hico_nav | EPSG:3857 | 13 | 13 | 4368 | 2716 | 42 | 9.3 | 5.1 |
| hico_nav | EPSG:3857 | 13 | 13 | 4371 | 2722 | 52 | 10.5 | 8.4 |
| hico_nav | EPSG:3857 | 13 | 13 | 4355 | 2798 | 65 | 10.0 | 9.7 |
| hico_nav | EPSG:3857 | 14 | 14 | 8610 | 5528 | 52 | 11.5 | 5.1 |
| hico_nav | EPSG:3857 | 14 | 14 | 8580 | 5544 | 78 | 11.8 | 16.7 |
| hico_nav | EPSG:3857 | 14 | 14 | 8584 | 5531 | 56 | 10.9 | 0.8 |
| hico_nav | EPSG:3857 | 14 | 14 | 8640 | 5551 | 43 | 13.4 | 0.1 |
| hico_nav | EPSG:3857 | 14 | 14 | 8619 | 5339 | 45 | 9.9 | 5.3 |
| hico_nav | EPSG:3857 | 16 | 16 | 34794 | 21746 | 46 | 10.2 | 5.3 |
| hico_nav | EPSG:3857 | 16 | 16 | 34396 | 21605 | 53 | 10.0 | 4.8 |
| hico_nav | EPSG:3857 | 16 | 16 | 34718 | 21657 | 59 | 8.3 | 19.1 |
| hico_nav | EPSG:3857 | 16 | 16 | 34429 | 21350 | 52 | 9.2 | 11.0 |
| hico_nav | EPSG:3857 | 16 | 16 | 34985 | 22085 | 71 | 10.1 | 21.0 |
| hico_nav | EPSG:3857 | 18 | 18 | 137317 | 89546 | 48 | 9.0 | 1.3 |
| hico_nav | EPSG:3857 | 18 | 18 | 137380 | 86898 | 45 | 11.2 | 4.0 |
| hico_nav | EPSG:3857 | 18 | 18 | 140341 | 87356 | 43 | 10.4 | 1.1 |
| hico_nav | EPSG:3857 | 18 | 18 | 137052 | 86460 | 52 | 12.5 | 7.3 |
| hico_nav | EPSG:3857 | 18 | 18 | 137079 | 85468 | 50 | 10.1 | 7.9 |
| hico_std | EPSG:3857 | 8 | 8 | 135 | 87 | 268 | 9.2 | 45.6 |
| hico_std | EPSG:3857 | 8 | 8 | 134 | 86 | 291 | 11.4 | 45.1 |
| hico_std | EPSG:3857 | 8 | 8 | 136 | 84 | 246 | 8.3 | 43.1 |
| hico_std | EPSG:3857 | 8 | 8 | 136 | 87 | 214 | 8.6 | 44.7 |
| hico_std | EPSG:3857 | 8 | 8 | 134 | 85 | 217 | 8.1 | 45.9 |
| hico_std | EPSG:3857 | 10 | 10 | 535 | 347 | 414 | 8.0 | 38.0 |
| hico_std | EPSG:3857 | 10 | 10 | 543 | 340 | 169 | 8.1 | 34.1 |
| hico_std | EPSG:3857 | 10 | 10 | 538 | 340 | 233 | 8.4 | 36.5 |
| hico_std | EPSG:3857 | 10 | 10 | 545 | 350 | 178 | 8.4 | 30.2 |
| hico_std | EPSG:3857 | 10 | 10 | 545 | 338 | 208 | 8.5 | 34.2 |
| hico_std | EPSG:3857 | 12 | 12 | 2158 | 1391 | 71 | 7.8 | 23.2 |
| hico_std | EPSG:3857 | 12 | 12 | 2190 | 1378 | 70 | 7.1 | 29.2 |
| hico_std | EPSG:3857 | 12 | 12 | 2145 | 1395 | 92 | 7.5 | 22.1 |
| hico_std | EPSG:3857 | 12 | 12 | 2185 | 1359 | 57 | 7.6 | 23.7 |
| hico_std | EPSG:3857 | 12 | 12 | 2182 | 1350 | 48 | 8.0 | 15.5 |
| hico_std | EPSG:3857 | 13 | 13 | 4337 | 2664 | 60 | 7.9 | 14.2 |
| hico_std | EPSG:3857 | 13 | 13 | 4321 | 2726 | 81 | 7.9 | 22.0 |
| hico_std | EPSG:3857 | 13 | 13 | 4368 | 2716 | 44 | 8.2 | 10.0 |
| hico_std | EPSG:3857 | 13 | 13 | 4371 | 2722 | 52 | 7.8 | 14.8 |
| hico_std | EPSG:3857 | 13 | 13 | 4355 | 2798 | 56 | 7.8 | 22.5 |
| hico_std | EPSG:3857 | 14 | 14 | 8610 | 5528 | 48 | 7.9 | 13.1 |
| hico_std | EPSG:3857 | 14 | 14 | 8580 | 5544 | 69 | 7.7 | 29.3 |
| hico_std | EPSG:3857 | 14 | 14 | 8584 | 5531 | 44 | 8.0 | 10.7 |
| hico_std | EPSG:3857 | 14 | 14 | 8640 | 5551 | 41 | 8.1 | 5.9 |
| hico_std | EPSG:3857 | 14 | 14 | 8619 | 5339 | 43 | 7.1 | 12.2 |
| hico_std | EPSG:3857 | 16 | 16 | 34794 | 21746 | 45 | 7.4 | 8.6 |
| hico_std | EPSG:3857 | 16 | 16 | 34396 | 21605 | 57 | 7.2 | 9.0 |
| hico_std | EPSG:3857 | 16 | 16 | 34718 | 21657 | 64 | 7.2 | 19.4 |
| hico_std | EPSG:3857 | 16 | 16 | 34429 | 21350 | 53 | 7.3 | 13.9 |
| hico_std | EPSG:3857 | 16 | 16 | 34985 | 22085 | 52 | 7.7 | 21.4 |
| hico_std | EPSG:3857 | 18 | 18 | 137317 | 89546 | 47 | 9.5 | 2.1 |
| hico_std | EPSG:3857 | 18 | 18 | 137380 | 86898 | 46 | 6.6 | 4.8 |
| hico_std | EPSG:3857 | 18 | 18 | 140341 | 87356 | 41 | 6.7 | 3.3 |
| hico_std | EPSG:3857 | 18 | 18 | 137052 | 86460 | 49 | 6.9 | 9.3 |
| hico_std | EPSG:3857 | 18 | 18 | 137079 | 85468 | 44 | 6.8 | 9.2 |
| hico_topographic | EPSG:3857 | 8 | 8 | 135 | 87 | 194 | 7.2 | 43.8 |
| hico_topographic | EPSG:3857 | 8 | 8 | 134 | 86 | 214 | 8.6 | 43.8 |
| hico_topographic | EPSG:3857 | 8 | 8 | 136 | 84 | 243 | 10.4 | 43.1 |
| hico_topographic | EPSG:3857 | 8 | 8 | 136 | 87 | 187 | 9.4 | 43.1 |
| hico_topographic | EPSG:3857 | 8 | 8 | 134 | 85 | 194 | 7.0 | 43.9 |
| hico_topographic | EPSG:3857 | 10 | 10 | 535 | 347 | 328 | 6.9 | 37.1 |
| hico_topographic | EPSG:3857 | 10 | 10 | 543 | 340 | 180 | 7.8 | 33.1 |
| hico_topographic | EPSG:3857 | 10 | 10 | 538 | 340 | 223 | 9.0 | 36.5 |
| hico_topographic | EPSG:3857 | 10 | 10 | 545 | 350 | 209 | 9.5 | 36.0 |
| hico_topographic | EPSG:3857 | 10 | 10 | 545 | 338 | 194 | 8.0 | 33.9 |
| hico_topographic | EPSG:3857 | 12 | 12 | 2158 | 1391 | 77 | 7.9 | 27.9 |
| hico_topographic | EPSG:3857 | 12 | 12 | 2190 | 1378 | 89 | 8.0 | 29.1 |
| hico_topographic | EPSG:3857 | 12 | 12 | 2145 | 1395 | 123 | 10.1 | 25.3 |
| hico_topographic | EPSG:3857 | 12 | 12 | 2185 | 1359 | 78 | 7.9 | 23.4 |
| hico_topographic | EPSG:3857 | 12 | 12 | 2182 | 1350 | 63 | 8.3 | 15.1 |
| hico_topographic | EPSG:3857 | 13 | 13 | 4337 | 2664 | 66 | 8.8 | 10.5 |
| hico_topographic | EPSG:3857 | 13 | 13 | 4321 | 2726 | 93 | 8.6 | 21.5 |
| hico_topographic | EPSG:3857 | 13 | 13 | 4368 | 2716 | 71 | 9.9 | 9.5 |
| hico_topographic | EPSG:3857 | 13 | 13 | 4371 | 2722 | 76 | 10.2 | 15.6 |
| hico_topographic | EPSG:3857 | 13 | 13 | 4355 | 2798 | 90 | 10.5 | 21.7 |
| hico_topographic | EPSG:3857 | 14 | 14 | 8610 | 5528 | 70 | 9.8 | 10.4 |
| hico_topographic | EPSG:3857 | 14 | 14 | 8580 | 5544 | 93 | 9.0 | 27.0 |
| hico_topographic | EPSG:3857 | 14 | 14 | 8584 | 5531 | 70 | 9.1 | 6.1 |
| hico_topographic | EPSG:3857 | 14 | 14 | 8640 | 5551 | 60 | 10.3 | 4.7 |
| hico_topographic | EPSG:3857 | 14 | 14 | 8619 | 5339 | 63 | 8.8 | 13.1 |
| hico_topographic | EPSG:3857 | 16 | 16 | 34794 | 21746 | 61 | 9.5 | 7.6 |
| hico_topographic | EPSG:3857 | 16 | 16 | 34396 | 21605 | 62 | 10.8 | 8.8 |
| hico_topographic | EPSG:3857 | 16 | 16 | 34718 | 21657 | 76 | 9.5 | 19.2 |
| hico_topographic | EPSG:3857 | 16 | 16 | 34429 | 21350 | 75 | 32.1 | 13.5 |
| hico_topographic | EPSG:3857 | 16 | 16 | 34985 | 22085 | 88 | 12.6 | 21.3 |
| hico_topographic | EPSG:3857 | 18 | 18 | 137317 | 89546 | 64 | 10.1 | 1.4 |
| hico_topographic | EPSG:3857 | 18 | 18 | 137380 | 86898 | 73 | 11.6 | 7.2 |
| hico_topographic | EPSG:3857 | 18 | 18 | 140341 | 87356 | 62 | 11.8 | 2.7 |
| hico_topographic | EPSG:3857 | 18 | 18 | 137052 | 86460 | 71 | 9.6 | 7.8 |
| hico_topographic | EPSG:3857 | 18 | 18 | 137079 | 85468 | 76 | 11.3 | 8.2 |
| hico_vegetation | EPSG:3857 | 8 | 8 | 135 | 87 | 247 | 11.0 | 44.3 |
| hico_vegetation | EPSG:3857 | 8 | 8 | 134 | 86 | 338 | 10.6 | 44.0 |
| hico_vegetation | EPSG:3857 | 8 | 8 | 136 | 84 | 298 | 11.2 | 43.1 |
| hico_vegetation | EPSG:3857 | 8 | 8 | 136 | 87 | 256 | 11.6 | 43.7 |
| hico_vegetation | EPSG:3857 | 8 | 8 | 134 | 85 | 252 | 7.5 | 44.0 |
| hico_vegetation | EPSG:3857 | 10 | 10 | 535 | 347 | 385 | 7.1 | 37.6 |
| hico_vegetation | EPSG:3857 | 10 | 10 | 543 | 340 | 173 | 7.8 | 33.4 |
| hico_vegetation | EPSG:3857 | 10 | 10 | 538 | 340 | 218 | 7.1 | 36.5 |
| hico_vegetation | EPSG:3857 | 10 | 10 | 545 | 350 | 162 | 6.8 | 29.8 |
| hico_vegetation | EPSG:3857 | 10 | 10 | 545 | 338 | 173 | 7.4 | 34.2 |
| hico_vegetation | EPSG:3857 | 12 | 12 | 2158 | 1391 | 63 | 6.8 | 20.4 |
| hico_vegetation | EPSG:3857 | 12 | 12 | 2190 | 1378 | 75 | 7.6 | 27.7 |
| hico_vegetation | EPSG:3857 | 12 | 12 | 2145 | 1395 | 97 | 9.6 | 18.5 |
| hico_vegetation | EPSG:3857 | 12 | 12 | 2185 | 1359 | 71 | 7.1 | 21.8 |
| hico_vegetation | EPSG:3857 | 12 | 12 | 2182 | 1350 | 49 | 7.2 | 14.3 |
| hico_vegetation | EPSG:3857 | 13 | 13 | 4337 | 2664 | 44 | 7.0 | 9.3 |
| hico_vegetation | EPSG:3857 | 13 | 13 | 4321 | 2726 | 72 | 7.4 | 18.4 |
| hico_vegetation | EPSG:3857 | 13 | 13 | 4368 | 2716 | 48 | 7.9 | 7.8 |
| hico_vegetation | EPSG:3857 | 13 | 13 | 4371 | 2722 | 52 | 7.1 | 12.3 |
| hico_vegetation | EPSG:3857 | 13 | 13 | 4355 | 2798 | 47 | 9.5 | 15.2 |
| hico_vegetation | EPSG:3857 | 14 | 14 | 8610 | 5528 | 46 | 6.9 | 7.3 |
| hico_vegetation | EPSG:3857 | 14 | 14 | 8580 | 5544 | 64 | 8.9 | 20.6 |
| hico_vegetation | EPSG:3857 | 14 | 14 | 8584 | 5531 | 55 | 10.0 | 3.2 |
| hico_vegetation | EPSG:3857 | 14 | 14 | 8640 | 5551 | 53 | 11.6 | 1.3 |
| hico_vegetation | EPSG:3857 | 14 | 14 | 8619 | 5339 | 54 | 12.0 | 9.9 |
| hico_vegetation | EPSG:3857 | 16 | 16 | 34794 | 21746 | 50 | 9.0 | 5.7 |
| hico_vegetation | EPSG:3857 | 16 | 16 | 34396 | 21605 | 49 | 9.5 | 6.9 |
| hico_vegetation | EPSG:3857 | 16 | 16 | 34718 | 21657 | 44 | 8.6 | 6.3 |
| hico_vegetation | EPSG:3857 | 16 | 16 | 34429 | 21350 | 48 | 9.2 | 5.9 |
| hico_vegetation | EPSG:3857 | 16 | 16 | 34985 | 22085 | 44 | 9.2 | 4.7 |
| hico_vegetation | EPSG:3857 | 18 | 18 | 137317 | 89546 | 42 | 9.8 | 0.4 |
| hico_vegetation | EPSG:3857 | 18 | 18 | 137380 | 86898 | 45 | 9.2 | 2.0 |
| hico_vegetation | EPSG:3857 | 18 | 18 | 140341 | 87356 | 44 | 8.8 | 2.3 |
| hico_vegetation | EPSG:3857 | 18 | 18 | 137052 | 86460 | 44 | 9.5 | 1.1 |
| hico_vegetation | EPSG:3857 | 18 | 18 | 137079 | 85468 | 44 | 8.9 | 1.0 |
| light_max | EPSG:3857 | 8 | 8 | 135 | 87 | 225 | 8.3 | 43.8 |
| light_max | EPSG:3857 | 8 | 8 | 134 | 86 | 223 | 7.9 | 44.0 |
| light_max | EPSG:3857 | 8 | 8 | 136 | 84 | 230 | 7.9 | 43.1 |
| light_max | EPSG:3857 | 8 | 8 | 136 | 87 | 203 | 9.5 | 41.9 |
| light_max | EPSG:3857 | 8 | 8 | 134 | 85 | 200 | 9.4 | 43.1 |
| light_max | EPSG:3857 | 10 | 10 | 535 | 347 | 427 | 8.9 | 38.5 |
| light_max | EPSG:3857 | 10 | 10 | 543 | 340 | 222 | 6.8 | 33.7 |
| light_max | EPSG:3857 | 10 | 10 | 538 | 340 | 235 | 8.9 | 34.5 |
| light_max | EPSG:3857 | 10 | 10 | 545 | 350 | 181 | 10.3 | 35.7 |
| light_max | EPSG:3857 | 10 | 10 | 545 | 338 | 209 | 7.7 | 31.4 |
| light_max | EPSG:3857 | 12 | 12 | 2158 | 1391 | 74 | 8.1 | 26.1 |
| light_max | EPSG:3857 | 12 | 12 | 2190 | 1378 | 85 | 8.2 | 31.7 |
| light_max | EPSG:3857 | 12 | 12 | 2145 | 1395 | 131 | 8.2 | 24.4 |
| light_max | EPSG:3857 | 12 | 12 | 2185 | 1359 | 66 | 7.3 | 22.3 |
| light_max | EPSG:3857 | 12 | 12 | 2182 | 1350 | 59 | 8.9 | 13.0 |
| light_max | EPSG:3857 | 13 | 13 | 4337 | 2664 | 83 | 10.3 | 13.3 |
| light_max | EPSG:3857 | 13 | 13 | 4321 | 2726 | 111 | 9.8 | 21.1 |
| light_max | EPSG:3857 | 13 | 13 | 4368 | 2716 | 63 | 9.3 | 8.9 |
| light_max | EPSG:3857 | 13 | 13 | 4371 | 2722 | 87 | 11.4 | 14.4 |
| light_max | EPSG:3857 | 13 | 13 | 4355 | 2798 | 88 | 8.5 | 25.6 |
| light_max | EPSG:3857 | 14 | 14 | 8610 | 5528 | 74 | 9.3 | 14.1 |
| light_max | EPSG:3857 | 14 | 14 | 8580 | 5544 | 101 | 9.0 | 27.0 |
| light_max | EPSG:3857 | 14 | 14 | 8584 | 5531 | 81 | 10.7 | 11.8 |
| light_max | EPSG:3857 | 14 | 14 | 8640 | 5551 | 75 | 11.0 | 7.7 |
| light_max | EPSG:3857 | 14 | 14 | 8619 | 5339 | 68 | 9.0 | 11.8 |
| light_max | EPSG:3857 | 16 | 16 | 34794 | 21746 | 72 | 10.1 | 10.2 |
| light_max | EPSG:3857 | 16 | 16 | 34396 | 21605 | 71 | 8.6 | 6.4 |
| light_max | EPSG:3857 | 16 | 16 | 34718 | 21657 | 80 | 11.3 | 14.4 |
| light_max | EPSG:3857 | 16 | 16 | 34429 | 21350 | 69 | 8.1 | 11.4 |
| light_max | EPSG:3857 | 16 | 16 | 34985 | 22085 | 77 | 10.1 | 15.7 |
| light_max | EPSG:3857 | 18 | 18 | 137317 | 89546 | 68 | 8.0 | 1.4 |
| light_max | EPSG:3857 | 18 | 18 | 137380 | 86898 | 60 | 7.4 | 5.1 |
| light_max | EPSG:3857 | 18 | 18 | 140341 | 87356 | 64 | 14.3 | 2.3 |
| light_max | EPSG:3857 | 18 | 18 | 137052 | 86460 | 79 | 9.3 | 6.9 |
| light_max | EPSG:3857 | 18 | 18 | 137079 | 85468 | 68 | 8.7 | 6.4 |
| light_min | EPSG:3857 | 8 | 8 | 135 | 87 | 113 | 7.9 | 19.2 |
| light_min | EPSG:3857 | 8 | 8 | 134 | 86 | 166 | 7.9 | 22.5 |
| light_min | EPSG:3857 | 8 | 8 | 136 | 84 | 103 | 9.4 | 17.6 |
| light_min | EPSG:3857 | 8 | 8 | 136 | 87 | 111 | 11.0 | 17.0 |
| light_min | EPSG:3857 | 8 | 8 | 134 | 85 | 108 | 8.6 | 20.5 |
| light_min | EPSG:3857 | 10 | 10 | 535 | 347 | 253 | 9.7 | 25.1 |
| light_min | EPSG:3857 | 10 | 10 | 543 | 340 | 125 | 7.8 | 16.0 |
| light_min | EPSG:3857 | 10 | 10 | 538 | 340 | 147 | 7.4 | 21.3 |
| light_min | EPSG:3857 | 10 | 10 | 545 | 350 | 109 | 8.2 | 15.9 |
| light_min | EPSG:3857 | 10 | 10 | 545 | 338 | 158 | 10.6 | 20.0 |
| light_min | EPSG:3857 | 12 | 12 | 2158 | 1391 | 43 | 9.9 | 6.6 |
| light_min | EPSG:3857 | 12 | 12 | 2190 | 1378 | 62 | 9.2 | 14.2 |
| light_min | EPSG:3857 | 12 | 12 | 2145 | 1395 | 99 | 9.0 | 13.6 |
| light_min | EPSG:3857 | 12 | 12 | 2185 | 1359 | 55 | 10.3 | 12.3 |
| light_min | EPSG:3857 | 12 | 12 | 2182 | 1350 | 48 | 9.8 | 6.1 |
| light_min | EPSG:3857 | 13 | 13 | 4337 | 2664 | 44 | 10.1 | 3.9 |
| light_min | EPSG:3857 | 13 | 13 | 4321 | 2726 | 63 | 9.1 | 8.3 |
| light_min | EPSG:3857 | 13 | 13 | 4368 | 2716 | 42 | 10.4 | 3.7 |
| light_min | EPSG:3857 | 13 | 13 | 4371 | 2722 | 50 | 13.5 | 5.0 |
| light_min | EPSG:3857 | 13 | 13 | 4355 | 2798 | 53 | 10.5 | 7.6 |
| light_min | EPSG:3857 | 14 | 14 | 8610 | 5528 | 41 | 10.7 | 3.2 |
| light_min | EPSG:3857 | 14 | 14 | 8580 | 5544 | 56 | 10.9 | 6.0 |
| light_min | EPSG:3857 | 14 | 14 | 8584 | 5531 | 46 | 9.2 | 0.3 |
| light_min | EPSG:3857 | 14 | 14 | 8640 | 5551 | 33 | 11.1 | 0.1 |
| light_min | EPSG:3857 | 14 | 14 | 8619 | 5339 | 37 | 10.9 | 3.2 |
| light_min | EPSG:3857 | 16 | 16 | 34794 | 21746 | 43 | 10.2 | 2.8 |
| light_min | EPSG:3857 | 16 | 16 | 34396 | 21605 | 42 | 9.3 | 3.5 |
| light_min | EPSG:3857 | 16 | 16 | 34718 | 21657 | 49 | 11.1 | 8.0 |
| light_min | EPSG:3857 | 16 | 16 | 34429 | 21350 | 43 | 9.0 | 4.4 |
| light_min | EPSG:3857 | 16 | 16 | 34985 | 22085 | 46 | 9.4 | 6.3 |
| light_min | EPSG:3857 | 18 | 18 | 137317 | 89546 | 36 | 10.0 | 0.1 |
| light_min | EPSG:3857 | 18 | 18 | 137380 | 86898 | 35 | 10.0 | 1.2 |
| light_min | EPSG:3857 | 18 | 18 | 140341 | 87356 | 37 | 11.7 | 0.3 |
| light_min | EPSG:3857 | 18 | 18 | 137052 | 86460 | 50 | 9.5 | 1.8 |
| light_min | EPSG:3857 | 18 | 18 | 137079 | 85468 | 46 | 10.3 | 3.1 |
| light_nav | EPSG:3857 | 8 | 8 | 135 | 87 | 157 | 9.2 | 22.2 |
| light_nav | EPSG:3857 | 8 | 8 | 134 | 86 | 170 | 7.5 | 25.7 |
| light_nav | EPSG:3857 | 8 | 8 | 136 | 84 | 142 | 9.1 | 22.1 |
| light_nav | EPSG:3857 | 8 | 8 | 136 | 87 | 145 | 10.6 | 19.3 |
| light_nav | EPSG:3857 | 8 | 8 | 134 | 85 | 152 | 9.7 | 22.5 |
| light_nav | EPSG:3857 | 10 | 10 | 535 | 347 | 318 | 8.4 | 26.4 |
| light_nav | EPSG:3857 | 10 | 10 | 543 | 340 | 143 | 9.7 | 16.4 |
| light_nav | EPSG:3857 | 10 | 10 | 538 | 340 | 193 | 7.3 | 21.9 |
| light_nav | EPSG:3857 | 10 | 10 | 545 | 350 | 107 | 8.9 | 16.1 |
| light_nav | EPSG:3857 | 10 | 10 | 545 | 338 | 141 | 9.6 | 21.7 |
| light_nav | EPSG:3857 | 12 | 12 | 2158 | 1391 | 42 | 9.5 | 6.7 |
| light_nav | EPSG:3857 | 12 | 12 | 2190 | 1378 | 59 | 8.6 | 14.3 |
| light_nav | EPSG:3857 | 12 | 12 | 2145 | 1395 | 99 | 10.6 | 14.2 |
| light_nav | EPSG:3857 | 12 | 12 | 2185 | 1359 | 61 | 9.8 | 13.1 |
| light_nav | EPSG:3857 | 12 | 12 | 2182 | 1350 | 47 | 9.7 | 6.9 |
| light_nav | EPSG:3857 | 13 | 13 | 4337 | 2664 | 42 | 7.9 | 4.0 |
| light_nav | EPSG:3857 | 13 | 13 | 4321 | 2726 | 64 | 7.9 | 9.5 |
| light_nav | EPSG:3857 | 13 | 13 | 4368 | 2716 | 40 | 7.6 | 4.0 |
| light_nav | EPSG:3857 | 13 | 13 | 4371 | 2722 | 40 | 7.8 | 6.4 |
| light_nav | EPSG:3857 | 13 | 13 | 4355 | 2798 | 41 | 7.3 | 7.9 |
| light_nav | EPSG:3857 | 14 | 14 | 8610 | 5528 | 35 | 7.7 | 3.7 |
| light_nav | EPSG:3857 | 14 | 14 | 8580 | 5544 | 48 | 7.6 | 12.0 |
| light_nav | EPSG:3857 | 14 | 14 | 8584 | 5531 | 32 | 7.1 | 0.3 |
| light_nav | EPSG:3857 | 14 | 14 | 8640 | 5551 | 27 | 7.6 | 0.1 |
| light_nav | EPSG:3857 | 14 | 14 | 8619 | 5339 | 31 | 8.3 | 3.8 |
| light_nav | EPSG:3857 | 16 | 16 | 34794 | 21746 | 34 | 8.1 | 3.4 |
| light_nav | EPSG:3857 | 16 | 16 | 34396 | 21605 | 34 | 10.3 | 3.7 |
| light_nav | EPSG:3857 | 16 | 16 | 34718 | 21657 | 46 | 7.2 | 13.7 |
| light_nav | EPSG:3857 | 16 | 16 | 34429 | 21350 | 37 | 7.5 | 7.9 |
| light_nav | EPSG:3857 | 16 | 16 | 34985 | 22085 | 41 | 6.8 | 15.2 |
| light_nav | EPSG:3857 | 18 | 18 | 137317 | 89546 | 30 | 7.2 | 0.6 |
| light_nav | EPSG:3857 | 18 | 18 | 137380 | 86898 | 30 | 7.0 | 2.4 |
| light_nav | EPSG:3857 | 18 | 18 | 140341 | 87356 | 36 | 8.3 | 0.6 |
| light_nav | EPSG:3857 | 18 | 18 | 137052 | 86460 | 45 | 9.4 | 5.1 |
| light_nav | EPSG:3857 | 18 | 18 | 137079 | 85468 | 41 | 7.8 | 5.9 |
| light_std | EPSG:3857 | 8 | 8 | 135 | 87 | 228 | 8.4 | 43.8 |
| light_std | EPSG:3857 | 8 | 8 | 134 | 86 | 230 | 8.5 | 44.0 |
| light_std | EPSG:3857 | 8 | 8 | 136 | 84 | 263 | 8.5 | 43.1 |
| light_std | EPSG:3857 | 8 | 8 | 136 | 87 | 213 | 8.0 | 41.9 |
| light_std | EPSG:3857 | 8 | 8 | 134 | 85 | 216 | 8.5 | 43.1 |
| light_std | EPSG:3857 | 10 | 10 | 535 | 347 | 406 | 9.7 | 38.5 |
| light_std | EPSG:3857 | 10 | 10 | 543 | 340 | 208 | 9.4 | 33.2 |
| light_std | EPSG:3857 | 10 | 10 | 538 | 340 | 251 | 10.7 | 34.5 |
| light_std | EPSG:3857 | 10 | 10 | 545 | 350 | 195 | 8.4 | 28.4 |
| light_std | EPSG:3857 | 10 | 10 | 545 | 338 | 201 | 9.2 | 31.4 |
| light_std | EPSG:3857 | 12 | 12 | 2158 | 1391 | 76 | 9.7 | 19.5 |
| light_std | EPSG:3857 | 12 | 12 | 2190 | 1378 | 79 | 8.3 | 28.9 |
| light_std | EPSG:3857 | 12 | 12 | 2145 | 1395 | 108 | 8.0 | 20.2 |
| light_std | EPSG:3857 | 12 | 12 | 2185 | 1359 | 67 | 11.1 | 22.2 |
| light_std | EPSG:3857 | 12 | 12 | 2182 | 1350 | 62 | 7.3 | 13.0 |
| light_std | EPSG:3857 | 13 | 13 | 4337 | 2664 | 63 | 9.0 | 13.0 |
| light_std | EPSG:3857 | 13 | 13 | 4321 | 2726 | 89 | 7.6 | 19.9 |
| light_std | EPSG:3857 | 13 | 13 | 4368 | 2716 | 53 | 9.2 | 8.3 |
| light_std | EPSG:3857 | 13 | 13 | 4371 | 2722 | 64 | 9.8 | 12.2 |
| light_std | EPSG:3857 | 13 | 13 | 4355 | 2798 | 73 | 7.2 | 21.6 |
| light_std | EPSG:3857 | 14 | 14 | 8610 | 5528 | 57 | 6.8 | 12.5 |
| light_std | EPSG:3857 | 14 | 14 | 8580 | 5544 | 91 | 7.9 | 26.9 |
| light_std | EPSG:3857 | 14 | 14 | 8584 | 5531 | 57 | 7.6 | 9.3 |
| light_std | EPSG:3857 | 14 | 14 | 8640 | 5551 | 53 | 8.3 | 4.7 |
| light_std | EPSG:3857 | 14 | 14 | 8619 | 5339 | 56 | 9.3 | 9.5 |
| light_std | EPSG:3857 | 16 | 16 | 34794 | 21746 | 61 | 10.9 | 8.1 |
| light_std | EPSG:3857 | 16 | 16 | 34396 | 21605 | 62 | 10.6 | 6.1 |
| light_std | EPSG:3857 | 16 | 16 | 34718 | 21657 | 67 | 8.9 | 14.4 |
| light_std | EPSG:3857 | 16 | 16 | 34429 | 21350 | 63 | 9.1 | 11.4 |
| light_std | EPSG:3857 | 16 | 16 | 34985 | 22085 | 67 | 9.9 | 15.7 |
| light_std | EPSG:3857 | 18 | 18 | 137317 | 89546 | 54 | 8.4 | 1.4 |
| light_std | EPSG:3857 | 18 | 18 | 137380 | 86898 | 51 | 7.8 | 3.3 |
| light_std | EPSG:3857 | 18 | 18 | 140341 | 87356 | 53 | 8.4 | 2.3 |
| light_std | EPSG:3857 | 18 | 18 | 137052 | 86460 | 62 | 9.1 | 6.9 |
| light_std | EPSG:3857 | 18 | 18 | 137079 | 85468 | 60 | 8.7 | 6.4 |
| light_topographic | EPSG:3857 | 8 | 8 | 135 | 87 | 252 | 10.3 | 41.8 |
| light_topographic | EPSG:3857 | 8 | 8 | 134 | 86 | 268 | 8.2 | 42.3 |
| light_topographic | EPSG:3857 | 8 | 8 | 136 | 84 | 245 | 8.3 | 41.6 |
| light_topographic | EPSG:3857 | 8 | 8 | 136 | 87 | 210 | 9.3 | 40.6 |
| light_topographic | EPSG:3857 | 8 | 8 | 134 | 85 | 203 | 9.1 | 41.4 |
| light_topographic | EPSG:3857 | 10 | 10 | 535 | 347 | 333 | 8.4 | 36.7 |
| light_topographic | EPSG:3857 | 10 | 10 | 543 | 340 | 195 | 8.5 | 31.0 |
| light_topographic | EPSG:3857 | 10 | 10 | 538 | 340 | 224 | 8.1 | 34.3 |
| light_topographic | EPSG:3857 | 10 | 10 | 545 | 350 | 182 | 8.6 | 35.4 |
| light_topographic | EPSG:3857 | 10 | 10 | 545 | 338 | 186 | 8.1 | 31.0 |
| light_topographic | EPSG:3857 | 12 | 12 | 2158 | 1391 | 83 | 12.2 | 25.5 |
| light_topographic | EPSG:3857 | 12 | 12 | 2190 | 1378 | 88 | 8.1 | 28.9 |
| light_topographic | EPSG:3857 | 12 | 12 | 2145 | 1395 | 120 | 8.1 | 24.1 |
| light_topographic | EPSG:3857 | 12 | 12 | 2185 | 1359 | 78 | 8.8 | 21.8 |
| light_topographic | EPSG:3857 | 12 | 12 | 2182 | 1350 | 64 | 10.7 | 12.3 |
| light_topographic | EPSG:3857 | 13 | 13 | 4337 | 2664 | 64 | 10.8 | 8.1 |
| light_topographic | EPSG:3857 | 13 | 13 | 4321 | 2726 | 91 | 9.5 | 20.1 |
| light_topographic | EPSG:3857 | 13 | 13 | 4368 | 2716 | 59 | 11.9 | 7.2 |
| light_topographic | EPSG:3857 | 13 | 13 | 4371 | 2722 | 76 | 10.2 | 13.1 |
| light_topographic | EPSG:3857 | 13 | 13 | 4355 | 2798 | 80 | 10.2 | 20.9 |
| light_topographic | EPSG:3857 | 14 | 14 | 8610 | 5528 | 72 | 9.1 | 9.3 |
| light_topographic | EPSG:3857 | 14 | 14 | 8580 | 5544 | 93 | 9.6 | 24.5 |
| light_topographic | EPSG:3857 | 14 | 14 | 8584 | 5531 | 71 | 10.2 | 4.5 |
| light_topographic | EPSG:3857 | 14 | 14 | 8640 | 5551 | 53 | 7.9 | 4.0 |
| light_topographic | EPSG:3857 | 14 | 14 | 8619 | 5339 | 59 | 9.7 | 10.2 |
| light_topographic | EPSG:3857 | 16 | 16 | 34794 | 21746 | 64 | 8.3 | 6.4 |
| light_topographic | EPSG:3857 | 16 | 16 | 34396 | 21605 | 57 | 7.9 | 6.2 |
| light_topographic | EPSG:3857 | 16 | 16 | 34718 | 21657 | 74 | 10.1 | 14.3 |
| light_topographic | EPSG:3857 | 16 | 16 | 34429 | 21350 | 70 | 14.1 | 10.5 |
| light_topographic | EPSG:3857 | 16 | 16 | 34985 | 22085 | 81 | 10.0 | 15.3 |
| light_topographic | EPSG:3857 | 18 | 18 | 137317 | 89546 | 63 | 9.0 | 0.6 |
| light_topographic | EPSG:3857 | 18 | 18 | 137380 | 86898 | 58 | 8.8 | 5.0 |
| light_topographic | EPSG:3857 | 18 | 18 | 140341 | 87356 | 54 | 12.3 | 1.9 |
| light_topographic | EPSG:3857 | 18 | 18 | 137052 | 86460 | 61 | 11.7 | 5.3 |
| light_topographic | EPSG:3857 | 18 | 18 | 137079 | 85468 | 71 | 7.1 | 6.1 |
| light_vegetation | EPSG:3857 | 8 | 8 | 135 | 87 | 247 | 7.7 | 42.0 |
| light_vegetation | EPSG:3857 | 8 | 8 | 134 | 86 | 281 | 9.9 | 42.3 |
| light_vegetation | EPSG:3857 | 8 | 8 | 136 | 84 | 243 | 8.7 | 42.3 |
| light_vegetation | EPSG:3857 | 8 | 8 | 136 | 87 | 216 | 8.1 | 40.0 |
| light_vegetation | EPSG:3857 | 8 | 8 | 134 | 85 | 248 | 8.7 | 42.3 |
| light_vegetation | EPSG:3857 | 10 | 10 | 535 | 347 | 414 | 8.9 | 37.7 |
| light_vegetation | EPSG:3857 | 10 | 10 | 543 | 340 | 196 | 8.8 | 32.3 |
| light_vegetation | EPSG:3857 | 10 | 10 | 538 | 340 | 248 | 8.3 | 34.6 |
| light_vegetation | EPSG:3857 | 10 | 10 | 545 | 350 | 201 | 7.8 | 28.3 |
| light_vegetation | EPSG:3857 | 10 | 10 | 545 | 338 | 216 | 9.0 | 31.3 |
| light_vegetation | EPSG:3857 | 12 | 12 | 2158 | 1391 | 57 | 7.7 | 17.7 |
| light_vegetation | EPSG:3857 | 12 | 12 | 2190 | 1378 | 74 | 8.5 | 27.0 |
| light_vegetation | EPSG:3857 | 12 | 12 | 2145 | 1395 | 95 | 8.1 | 17.0 |
| light_vegetation | EPSG:3857 | 12 | 12 | 2185 | 1359 | 64 | 9.5 | 20.4 |
| light_vegetation | EPSG:3857 | 12 | 12 | 2182 | 1350 | 62 | 9.8 | 11.7 |
| light_vegetation | EPSG:3857 | 13 | 13 | 4337 | 2664 | 58 | 9.1 | 6.7 |
| light_vegetation | EPSG:3857 | 13 | 13 | 4321 | 2726 | 78 | 8.4 | 15.4 |
| light_vegetation | EPSG:3857 | 13 | 13 | 4368 | 2716 | 52 | 10.8 | 4.8 |
| light_vegetation | EPSG:3857 | 13 | 13 | 4371 | 2722 | 63 | 10.7 | 9.2 |
| light_vegetation | EPSG:3857 | 13 | 13 | 4355 | 2798 | 58 | 9.0 | 12.6 |
| light_vegetation | EPSG:3857 | 14 | 14 | 8610 | 5528 | 51 | 9.5 | 5.2 |
| light_vegetation | EPSG:3857 | 14 | 14 | 8580 | 5544 | 64 | 9.2 | 18.5 |
| light_vegetation | EPSG:3857 | 14 | 14 | 8584 | 5531 | 47 | 8.7 | 1.9 |
| light_vegetation | EPSG:3857 | 14 | 14 | 8640 | 5551 | 46 | 9.2 | 1.4 |
| light_vegetation | EPSG:3857 | 14 | 14 | 8619 | 5339 | 45 | 9.1 | 6.0 |
| light_vegetation | EPSG:3857 | 16 | 16 | 34794 | 21746 | 49 | 8.7 | 4.7 |
| light_vegetation | EPSG:3857 | 16 | 16 | 34396 | 21605 | 49 | 9.2 | 4.2 |
| light_vegetation | EPSG:3857 | 16 | 16 | 34718 | 21657 | 45 | 8.7 | 4.7 |
| light_vegetation | EPSG:3857 | 16 | 16 | 34429 | 21350 | 45 | 9.7 | 4.8 |
| light_vegetation | EPSG:3857 | 16 | 16 | 34985 | 22085 | 38 | 6.7 | 3.1 |
| light_vegetation | EPSG:3857 | 18 | 18 | 137317 | 89546 | 38 | 6.9 | 0.3 |
| light_vegetation | EPSG:3857 | 18 | 18 | 137380 | 86898 | 42 | 9.0 | 1.4 |
| light_vegetation | EPSG:3857 | 18 | 18 | 140341 | 87356 | 68 | 9.7 | 1.6 |
| light_vegetation | EPSG:3857 | 18 | 18 | 137052 | 86460 | 48 | 9.2 | 0.6 |
| light_vegetation | EPSG:3857 | 18 | 18 | 137079 | 85468 | 42 | 9.2 | 0.4 |
| sepia_max | EPSG:3857 | 8 | 8 | 135 | 87 | 229 | 8.3 | 44.0 |
| sepia_max | EPSG:3857 | 8 | 8 | 134 | 86 | 233 | 8.8 | 44.5 |
| sepia_max | EPSG:3857 | 8 | 8 | 136 | 84 | 244 | 8.5 | 41.3 |
| sepia_max | EPSG:3857 | 8 | 8 | 136 | 87 | 212 | 9.2 | 42.4 |
| sepia_max | EPSG:3857 | 8 | 8 | 134 | 85 | 206 | 7.7 | 43.0 |
| sepia_max | EPSG:3857 | 10 | 10 | 535 | 347 | 403 | 7.7 | 44.5 |
| sepia_max | EPSG:3857 | 10 | 10 | 543 | 340 | 218 | 15.1 | 34.4 |
| sepia_max | EPSG:3857 | 10 | 10 | 538 | 340 | 282 | 8.8 | 37.4 |
| sepia_max | EPSG:3857 | 10 | 10 | 545 | 350 | 202 | 8.6 | 37.5 |
| sepia_max | EPSG:3857 | 10 | 10 | 545 | 338 | 201 | 12.0 | 31.0 |
| sepia_max | EPSG:3857 | 12 | 12 | 2158 | 1391 | 97 | 9.3 | 25.3 |
| sepia_max | EPSG:3857 | 12 | 12 | 2190 | 1378 | 95 | 8.9 | 34.8 |
| sepia_max | EPSG:3857 | 12 | 12 | 2145 | 1395 | 138 | 10.1 | 26.3 |
| sepia_max | EPSG:3857 | 12 | 12 | 2185 | 1359 | 81 | 9.2 | 22.8 |
| sepia_max | EPSG:3857 | 12 | 12 | 2182 | 1350 | 83 | 7.9 | 13.2 |
| sepia_max | EPSG:3857 | 13 | 13 | 4337 | 2664 | 61 | 8.9 | 14.0 |
| sepia_max | EPSG:3857 | 13 | 13 | 4321 | 2726 | 101 | 9.4 | 22.8 |
| sepia_max | EPSG:3857 | 13 | 13 | 4368 | 2716 | 66 | 9.3 | 9.1 |
| sepia_max | EPSG:3857 | 13 | 13 | 4371 | 2722 | 78 | 9.2 | 14.7 |
| sepia_max | EPSG:3857 | 13 | 13 | 4355 | 2798 | 94 | 10.9 | 27.1 |
| sepia_max | EPSG:3857 | 14 | 14 | 8610 | 5528 | 77 | 10.3 | 14.2 |
| sepia_max | EPSG:3857 | 14 | 14 | 8580 | 5544 | 102 | 8.4 | 29.3 |
| sepia_max | EPSG:3857 | 14 | 14 | 8584 | 5531 | 65 | 9.7 | 11.7 |
| sepia_max | EPSG:3857 | 14 | 14 | 8640 | 5551 | 68 | 13.2 | 8.1 |
| sepia_max | EPSG:3857 | 14 | 14 | 8619 | 5339 | 72 | 8.6 | 12.1 |
| sepia_max | EPSG:3857 | 16 | 16 | 34794 | 21746 | 71 | 9.2 | 10.5 |
| sepia_max | EPSG:3857 | 16 | 16 | 34396 | 21605 | 71 | 10.1 | 7.5 |
| sepia_max | EPSG:3857 | 16 | 16 | 34718 | 21657 | 77 | 9.2 | 17.7 |
| sepia_max | EPSG:3857 | 16 | 16 | 34429 | 21350 | 74 | 10.8 | 13.2 |
| sepia_max | EPSG:3857 | 16 | 16 | 34985 | 22085 | 87 | 10.0 | 19.2 |
| sepia_max | EPSG:3857 | 18 | 18 | 137317 | 89546 | 81 | 10.8 | 1.9 |
| sepia_max | EPSG:3857 | 18 | 18 | 137380 | 86898 | 78 | 9.5 | 6.8 |
| sepia_max | EPSG:3857 | 18 | 18 | 140341 | 87356 | 74 | 11.9 | 2.0 |
| sepia_max | EPSG:3857 | 18 | 18 | 137052 | 86460 | 79 | 9.1 | 8.6 |
| sepia_max | EPSG:3857 | 18 | 18 | 137079 | 85468 | 78 | 11.6 | 7.3 |
| sepia_min | EPSG:3857 | 8 | 8 | 135 | 87 | 138 | 9.6 | 21.3 |
| sepia_min | EPSG:3857 | 8 | 8 | 134 | 86 | 164 | 7.6 | 25.1 |
| sepia_min | EPSG:3857 | 8 | 8 | 136 | 84 | 88 | 8.8 | 19.8 |
| sepia_min | EPSG:3857 | 8 | 8 | 136 | 87 | 88 | 8.2 | 18.8 |
| sepia_min | EPSG:3857 | 8 | 8 | 134 | 85 | 93 | 10.6 | 22.0 |
| sepia_min | EPSG:3857 | 10 | 10 | 535 | 347 | 260 | 7.8 | 30.0 |
| sepia_min | EPSG:3857 | 10 | 10 | 543 | 340 | 141 | 9.3 | 17.4 |
| sepia_min | EPSG:3857 | 10 | 10 | 538 | 340 | 151 | 8.3 | 23.8 |
| sepia_min | EPSG:3857 | 10 | 10 | 545 | 350 | 123 | 8.3 | 17.5 |
| sepia_min | EPSG:3857 | 10 | 10 | 545 | 338 | 135 | 10.2 | 22.2 |
| sepia_min | EPSG:3857 | 12 | 12 | 2158 | 1391 | 48 | 9.6 | 7.5 |
| sepia_min | EPSG:3857 | 12 | 12 | 2190 | 1378 | 61 | 10.4 | 17.3 |
| sepia_min | EPSG:3857 | 12 | 12 | 2145 | 1395 | 109 | 11.5 | 16.4 |
| sepia_min | EPSG:3857 | 12 | 12 | 2185 | 1359 | 72 | 10.8 | 14.4 |
| sepia_min | EPSG:3857 | 12 | 12 | 2182 | 1350 | 53 | 11.4 | 6.8 |
| sepia_min | EPSG:3857 | 13 | 13 | 4337 | 2664 | 49 | 9.2 | 4.3 |
| sepia_min | EPSG:3857 | 13 | 13 | 4321 | 2726 | 55 | 10.7 | 9.9 |
| sepia_min | EPSG:3857 | 13 | 13 | 4368 | 2716 | 42 | 9.7 | 4.4 |
| sepia_min | EPSG:3857 | 13 | 13 | 4371 | 2722 | 44 | 11.1 | 6.1 |
| sepia_min | EPSG:3857 | 13 | 13 | 4355 | 2798 | 56 | 10.6 | 8.8 |
| sepia_min | EPSG:3857 | 14 | 14 | 8610 | 5528 | 45 | 10.4 | 3.5 |
| sepia_min | EPSG:3857 | 14 | 14 | 8580 | 5544 | 55 | 12.8 | 6.5 |
| sepia_min | EPSG:3857 | 14 | 14 | 8584 | 5531 | 44 | 13.5 | 0.3 |
| sepia_min | EPSG:3857 | 14 | 14 | 8640 | 5551 | 43 | 12.1 | 0.1 |
| sepia_min | EPSG:3857 | 14 | 14 | 8619 | 5339 | 44 | 10.5 | 3.9 |
| sepia_min | EPSG:3857 | 16 | 16 | 34794 | 21746 | 45 | 9.7 | 3.3 |
| sepia_min | EPSG:3857 | 16 | 16 | 34396 | 21605 | 47 | 12.0 | 4.0 |
| sepia_min | EPSG:3857 | 16 | 16 | 34718 | 21657 | 56 | 11.1 | 9.1 |
| sepia_min | EPSG:3857 | 16 | 16 | 34429 | 21350 | 46 | 10.1 | 5.1 |
| sepia_min | EPSG:3857 | 16 | 16 | 34985 | 22085 | 46 | 9.9 | 8.1 |
| sepia_min | EPSG:3857 | 18 | 18 | 137317 | 89546 | 33 | 8.6 | 0.1 |
| sepia_min | EPSG:3857 | 18 | 18 | 137380 | 86898 | 39 | 9.1 | 1.9 |
| sepia_min | EPSG:3857 | 18 | 18 | 140341 | 87356 | 32 | 8.3 | 0.4 |
| sepia_min | EPSG:3857 | 18 | 18 | 137052 | 86460 | 34 | 11.8 | 2.6 |
| sepia_min | EPSG:3857 | 18 | 18 | 137079 | 85468 | 33 | 9.0 | 4.0 |
| sepia_nav | EPSG:3857 | 8 | 8 | 135 | 87 | 141 | 8.2 | 23.6 |
| sepia_nav | EPSG:3857 | 8 | 8 | 134 | 86 | 170 | 8.3 | 27.4 |
| sepia_nav | EPSG:3857 | 8 | 8 | 136 | 84 | 149 | 8.2 | 23.2 |
| sepia_nav | EPSG:3857 | 8 | 8 | 136 | 87 | 146 | 9.0 | 20.6 |
| sepia_nav | EPSG:3857 | 8 | 8 | 134 | 85 | 147 | 7.9 | 23.5 |
| sepia_nav | EPSG:3857 | 10 | 10 | 535 | 347 | 297 | 9.2 | 32.3 |
| sepia_nav | EPSG:3857 | 10 | 10 | 543 | 340 | 141 | 10.0 | 17.9 |
| sepia_nav | EPSG:3857 | 10 | 10 | 538 | 340 | 169 | 7.6 | 24.5 |
| sepia_nav | EPSG:3857 | 10 | 10 | 545 | 350 | 117 | 8.3 | 17.7 |
| sepia_nav | EPSG:3857 | 10 | 10 | 545 | 338 | 151 | 8.7 | 24.0 |
| sepia_nav | EPSG:3857 | 12 | 12 | 2158 | 1391 | 53 | 9.7 | 7.6 |
| sepia_nav | EPSG:3857 | 12 | 12 | 2190 | 1378 | 66 | 9.5 | 17.4 |
| sepia_nav | EPSG:3857 | 12 | 12 | 2145 | 1395 | 104 | 10.9 | 16.7 |
| sepia_nav | EPSG:3857 | 12 | 12 | 2185 | 1359 | 62 | 9.1 | 15.2 |
| sepia_nav | EPSG:3857 | 12 | 12 | 2182 | 1350 | 46 | 11.0 | 7.4 |
| sepia_nav | EPSG:3857 | 13 | 13 | 4337 | 2664 | 48 | 9.2 | 4.5 |
| sepia_nav | EPSG:3857 | 13 | 13 | 4321 | 2726 | 68 | 8.2 | 11.2 |
| sepia_nav | EPSG:3857 | 13 | 13 | 4368 | 2716 | 44 | 7.8 | 5.0 |
| sepia_nav | EPSG:3857 | 13 | 13 | 4371 | 2722 | 53 | 8.9 | 7.6 |
| sepia_nav | EPSG:3857 | 13 | 13 | 4355 | 2798 | 53 | 10.4 | 9.1 |
| sepia_nav | EPSG:3857 | 14 | 14 | 8610 | 5528 | 46 | 8.5 | 4.1 |
| sepia_nav | EPSG:3857 | 14 | 14 | 8580 | 5544 | 55 | 8.2 | 14.8 |
| sepia_nav | EPSG:3857 | 14 | 14 | 8584 | 5531 | 42 | 8.8 | 0.4 |
| sepia_nav | EPSG:3857 | 14 | 14 | 8640 | 5551 | 37 | 8.4 | 0.1 |
| sepia_nav | EPSG:3857 | 14 | 14 | 8619 | 5339 | 45 | 9.0 | 4.6 |
| sepia_nav | EPSG:3857 | 16 | 16 | 34794 | 21746 | 51 | 13.1 | 4.1 |
| sepia_nav | EPSG:3857 | 16 | 16 | 34396 | 21605 | 55 | 11.6 | 4.6 |
| sepia_nav | EPSG:3857 | 16 | 16 | 34718 | 21657 | 70 | 9.2 | 16.6 |
| sepia_nav | EPSG:3857 | 16 | 16 | 34429 | 21350 | 50 | 9.5 | 9.4 |
| sepia_nav | EPSG:3857 | 16 | 16 | 34985 | 22085 | 55 | 8.4 | 18.9 |
| sepia_nav | EPSG:3857 | 18 | 18 | 137317 | 89546 | 38 | 9.9 | 1.2 |
| sepia_nav | EPSG:3857 | 18 | 18 | 137380 | 86898 | 40 | 8.5 | 3.7 |
| sepia_nav | EPSG:3857 | 18 | 18 | 140341 | 87356 | 48 | 11.0 | 0.6 |
| sepia_nav | EPSG:3857 | 18 | 18 | 137052 | 86460 | 48 | 8.4 | 6.8 |
| sepia_nav | EPSG:3857 | 18 | 18 | 137079 | 85468 | 46 | 8.6 | 7.6 |
| sepia_std | EPSG:3857 | 8 | 8 | 135 | 87 | 221 | 8.1 | 44.0 |
| sepia_std | EPSG:3857 | 8 | 8 | 134 | 86 | 228 | 8.5 | 44.5 |
| sepia_std | EPSG:3857 | 8 | 8 | 136 | 84 | 233 | 9.5 | 41.3 |
| sepia_std | EPSG:3857 | 8 | 8 | 136 | 87 | 207 | 8.7 | 42.4 |
| sepia_std | EPSG:3857 | 8 | 8 | 134 | 85 | 216 | 7.9 | 43.0 |
| sepia_std | EPSG:3857 | 10 | 10 | 535 | 347 | 434 | 7.8 | 44.5 |
| sepia_std | EPSG:3857 | 10 | 10 | 543 | 340 | 196 | 8.0 | 33.7 |
| sepia_std | EPSG:3857 | 10 | 10 | 538 | 340 | 278 | 7.6 | 37.4 |
| sepia_std | EPSG:3857 | 10 | 10 | 545 | 350 | 158 | 8.0 | 30.4 |
| sepia_std | EPSG:3857 | 10 | 10 | 545 | 338 | 206 | 8.6 | 31.0 |
| sepia_std | EPSG:3857 | 12 | 12 | 2158 | 1391 | 59 | 7.7 | 18.1 |
| sepia_std | EPSG:3857 | 12 | 12 | 2190 | 1378 | 78 | 7.9 | 31.8 |
| sepia_std | EPSG:3857 | 12 | 12 | 2145 | 1395 | 113 | 8.1 | 22.3 |
| sepia_std | EPSG:3857 | 12 | 12 | 2185 | 1359 | 74 | 8.5 | 22.6 |
| sepia_std | EPSG:3857 | 12 | 12 | 2182 | 1350 | 58 | 8.3 | 13.2 |
| sepia_std | EPSG:3857 | 13 | 13 | 4337 | 2664 | 64 | 9.8 | 13.7 |
| sepia_std | EPSG:3857 | 13 | 13 | 4321 | 2726 | 104 | 7.9 | 21.3 |
| sepia_std | EPSG:3857 | 13 | 13 | 4368 | 2716 | 65 | 10.0 | 8.6 |
| sepia_std | EPSG:3857 | 13 | 13 | 4371 | 2722 | 69 | 10.1 | 12.7 |
| sepia_std | EPSG:3857 | 13 | 13 | 4355 | 2798 | 84 | 8.9 | 22.7 |
| sepia_std | EPSG:3857 | 14 | 14 | 8610 | 5528 | 68 | 9.2 | 12.5 |
| sepia_std | EPSG:3857 | 14 | 14 | 8580 | 5544 | 108 | 8.8 | 28.9 |
| sepia_std | EPSG:3857 | 14 | 14 | 8584 | 5531 | 52 | 8.1 | 9.6 |
| sepia_std | EPSG:3857 | 14 | 14 | 8640 | 5551 | 48 | 8.1 | 5.6 |
| sepia_std | EPSG:3857 | 14 | 14 | 8619 | 5339 | 52 | 8.8 | 10.1 |
| sepia_std | EPSG:3857 | 16 | 16 | 34794 | 21746 | 64 | 8.9 | 8.6 |
| sepia_std | EPSG:3857 | 16 | 16 | 34396 | 21605 | 74 | 11.0 | 7.3 |
| sepia_std | EPSG:3857 | 16 | 16 | 34718 | 21657 | 82 | 9.2 | 17.7 |
| sepia_std | EPSG:3857 | 16 | 16 | 34429 | 21350 | 62 | 9.7 | 13.2 |
| sepia_std | EPSG:3857 | 16 | 16 | 34985 | 22085 | 65 | 8.9 | 19.2 |
| sepia_std | EPSG:3857 | 18 | 18 | 137317 | 89546 | 56 | 9.1 | 1.9 |
| sepia_std | EPSG:3857 | 18 | 18 | 137380 | 86898 | 56 | 9.6 | 4.7 |
| sepia_std | EPSG:3857 | 18 | 18 | 140341 | 87356 | 53 | 9.0 | 2.0 |
| sepia_std | EPSG:3857 | 18 | 18 | 137052 | 86460 | 60 | 9.2 | 8.6 |
| sepia_std | EPSG:3857 | 18 | 18 | 137079 | 85468 | 56 | 9.0 | 7.3 |
| sepia_topographic | EPSG:3857 | 8 | 8 | 135 | 87 | 211 | 8.1 | 42.3 |
| sepia_topographic | EPSG:3857 | 8 | 8 | 134 | 86 | 243 | 10.7 | 43.0 |
| sepia_topographic | EPSG:3857 | 8 | 8 | 136 | 84 | 234 | 9.0 | 39.8 |
| sepia_topographic | EPSG:3857 | 8 | 8 | 136 | 87 | 191 | 8.2 | 41.4 |
| sepia_topographic | EPSG:3857 | 8 | 8 | 134 | 85 | 217 | 11.4 | 41.9 |
| sepia_topographic | EPSG:3857 | 10 | 10 | 535 | 347 | 354 | 7.9 | 42.0 |
| sepia_topographic | EPSG:3857 | 10 | 10 | 543 | 340 | 194 | 8.2 | 30.9 |
| sepia_topographic | EPSG:3857 | 10 | 10 | 538 | 340 | 209 | 8.3 | 34.6 |
| sepia_topographic | EPSG:3857 | 10 | 10 | 545 | 350 | 184 | 8.0 | 36.5 |
| sepia_topographic | EPSG:3857 | 10 | 10 | 545 | 338 | 178 | 8.3 | 29.6 |
| sepia_topographic | EPSG:3857 | 12 | 12 | 2158 | 1391 | 72 | 8.3 | 24.7 |
| sepia_topographic | EPSG:3857 | 12 | 12 | 2190 | 1378 | 92 | 8.4 | 31.0 |
| sepia_topographic | EPSG:3857 | 12 | 12 | 2145 | 1395 | 135 | 9.5 | 26.3 |
| sepia_topographic | EPSG:3857 | 12 | 12 | 2185 | 1359 | 81 | 9.7 | 22.3 |
| sepia_topographic | EPSG:3857 | 12 | 12 | 2182 | 1350 | 62 | 8.3 | 12.6 |
| sepia_topographic | EPSG:3857 | 13 | 13 | 4337 | 2664 | 62 | 8.7 | 8.3 |
| sepia_topographic | EPSG:3857 | 13 | 13 | 4321 | 2726 | 91 | 8.1 | 20.1 |
| sepia_topographic | EPSG:3857 | 13 | 13 | 4368 | 2716 | 59 | 9.4 | 7.7 |
| sepia_topographic | EPSG:3857 | 13 | 13 | 4371 | 2722 | 73 | 9.9 | 13.8 |
| sepia_topographic | EPSG:3857 | 13 | 13 | 4355 | 2798 | 82 | 9.1 | 21.2 |
| sepia_topographic | EPSG:3857 | 14 | 14 | 8610 | 5528 | 68 | 8.9 | 9.0 |
| sepia_topographic | EPSG:3857 | 14 | 14 | 8580 | 5544 | 95 | 11.2 | 25.0 |
| sepia_topographic | EPSG:3857 | 14 | 14 | 8584 | 5531 | 64 | 10.8 | 4.8 |
| sepia_topographic | EPSG:3857 | 14 | 14 | 8640 | 5551 | 65 | 9.5 | 4.6 |
| sepia_topographic | EPSG:3857 | 14 | 14 | 8619 | 5339 | 67 | 9.9 | 10.7 |
| sepia_topographic | EPSG:3857 | 16 | 16 | 34794 | 21746 | 78 | 11.2 | 6.9 |
| sepia_topographic | EPSG:3857 | 16 | 16 | 34396 | 21605 | 68 | 9.8 | 7.2 |
| sepia_topographic | EPSG:3857 | 16 | 16 | 34718 | 21657 | 72 | 8.1 | 17.5 |
| sepia_topographic | EPSG:3857 | 16 | 16 | 34429 | 21350 | 61 | 10.1 | 12.4 |
| sepia_topographic | EPSG:3857 | 16 | 16 | 34985 | 22085 | 64 | 8.4 | 19.0 |
| sepia_topographic | EPSG:3857 | 18 | 18 | 137317 | 89546 | 66 | 9.2 | 1.2 |
| sepia_topographic | EPSG:3857 | 18 | 18 | 137380 | 86898 | 47 | 7.7 | 6.5 |
| sepia_topographic | EPSG:3857 | 18 | 18 | 140341 | 87356 | 47 | 8.3 | 1.3 |
| sepia_topographic | EPSG:3857 | 18 | 18 | 137052 | 86460 | 58 | 11.6 | 7.0 |
| sepia_topographic | EPSG:3857 | 18 | 18 | 137079 | 85468 | 62 | 8.3 | 7.6 |
| sepia_vegetation | EPSG:3857 | 8 | 8 | 135 | 87 | 225 | 8.8 | 42.4 |
| sepia_vegetation | EPSG:3857 | 8 | 8 | 134 | 86 | 292 | 10.1 | 43.1 |
| sepia_vegetation | EPSG:3857 | 8 | 8 | 136 | 84 | 248 | 9.3 | 40.0 |
| sepia_vegetation | EPSG:3857 | 8 | 8 | 136 | 87 | 210 | 8.6 | 40.9 |
| sepia_vegetation | EPSG:3857 | 8 | 8 | 134 | 85 | 217 | 9.6 | 41.9 |
| sepia_vegetation | EPSG:3857 | 10 | 10 | 535 | 347 | 384 | 9.8 | 43.9 |
| sepia_vegetation | EPSG:3857 | 10 | 10 | 543 | 340 | 199 | 9.0 | 33.2 |
| sepia_vegetation | EPSG:3857 | 10 | 10 | 538 | 340 | 236 | 8.4 | 37.3 |
| sepia_vegetation | EPSG:3857 | 10 | 10 | 545 | 350 | 159 | 8.7 | 30.1 |
| sepia_vegetation | EPSG:3857 | 10 | 10 | 545 | 338 | 204 | 10.9 | 30.5 |
| sepia_vegetation | EPSG:3857 | 12 | 12 | 2158 | 1391 | 65 | 8.5 | 14.6 |
| sepia_vegetation | EPSG:3857 | 12 | 12 | 2190 | 1378 | 88 | 12.0 | 29.3 |
| sepia_vegetation | EPSG:3857 | 12 | 12 | 2145 | 1395 | 123 | 10.1 | 18.5 |
| sepia_vegetation | EPSG:3857 | 12 | 12 | 2185 | 1359 | 82 | 10.5 | 20.1 |
| sepia_vegetation | EPSG:3857 | 12 | 12 | 2182 | 1350 | 72 | 11.6 | 11.9 |
| sepia_vegetation | EPSG:3857 | 13 | 13 | 4337 | 2664 | 63 | 9.3 | 6.9 |
| sepia_vegetation | EPSG:3857 | 13 | 13 | 4321 | 2726 | 90 | 9.1 | 15.7 |
| sepia_vegetation | EPSG:3857 | 13 | 13 | 4368 | 2716 | 62 | 12.7 | 5.9 |
| sepia_vegetation | EPSG:3857 | 13 | 13 | 4371 | 2722 | 72 | 12.0 | 10.0 |
| sepia_vegetation | EPSG:3857 | 13 | 13 | 4355 | 2798 | 64 | 11.4 | 13.6 |
| sepia_vegetation | EPSG:3857 | 14 | 14 | 8610 | 5528 | 58 | 9.1 | 5.4 |
| sepia_vegetation | EPSG:3857 | 14 | 14 | 8580 | 5544 | 79 | 12.0 | 18.6 |
| sepia_vegetation | EPSG:3857 | 14 | 14 | 8584 | 5531 | 49 | 10.2 | 2.2 |
| sepia_vegetation | EPSG:3857 | 14 | 14 | 8640 | 5551 | 49 | 10.2 | 1.3 |
| sepia_vegetation | EPSG:3857 | 14 | 14 | 8619 | 5339 | 49 | 9.3 | 6.7 |
| sepia_vegetation | EPSG:3857 | 16 | 16 | 34794 | 21746 | 51 | 10.2 | 5.2 |
| sepia_vegetation | EPSG:3857 | 16 | 16 | 34396 | 21605 | 51 | 9.5 | 5.4 |
| sepia_vegetation | EPSG:3857 | 16 | 16 | 34718 | 21657 | 47 | 9.5 | 5.3 |
| sepia_vegetation | EPSG:3857 | 16 | 16 | 34429 | 21350 | 51 | 11.3 | 5.0 |
| sepia_vegetation | EPSG:3857 | 16 | 16 | 34985 | 22085 | 43 | 9.8 | 5.1 |
| sepia_vegetation | EPSG:3857 | 18 | 18 | 137317 | 89546 | 40 | 8.7 | 0.3 |
| sepia_vegetation | EPSG:3857 | 18 | 18 | 137380 | 86898 | 44 | 9.9 | 2.5 |
| sepia_vegetation | EPSG:3857 | 18 | 18 | 140341 | 87356 | 44 | 13.2 | 1.0 |
| sepia_vegetation | EPSG:3857 | 18 | 18 | 137052 | 86460 | 46 | 8.5 | 0.4 |
| sepia_vegetation | EPSG:3857 | 18 | 18 | 137079 | 85468 | 39 | 10.2 | 0.5 |

</details>

## 2. Per layer, theme `default_std`, in-process

One tile per zoom and CRS, rendered with a single Mapnik layer active at a time; layers Mapnik does not query at that scale are left out. `render` is the wall time of that render (query + draw); `db` is planning + execution of the same query under EXPLAIN ANALYZE; `rows` is what the query returns; `scans` are the plan's scan nodes. Layers sorted by render time.

### EPSG:3857 z8 (8) 135/87: render 167 ms, encode 17.6 ms, 47 KB, 10 layers, db sum 137 ms

| layer | render ms | db ms | rows | scans |
|---|---|---|---|---|
| landcover_osm_polygon_z9 | 76 | 21 | 9841 | Bitmap Heap Scan osm_polygon_z9; Bitmap Index Scan osm_polygon_z9_geom_idx |
| roads_fill_osm_line_z9 | 25 | 11 | 3543 | Bitmap Heap Scan osm_line_z9; Bitmap Index Scan osm_line_z9_geom_idx |
| rail_osm_line_z9 | 23 | 10 | 4224 | Bitmap Heap Scan osm_line_z9; Bitmap Index Scan osm_line_z9_geom_idx |
| landuse_osm_polygon_z9 | 22 | 10 | 2803 | Bitmap Heap Scan osm_polygon_z9; Bitmap Index Scan osm_polygon_z9_geom_idx |
| places_osm_label | 19 | 38 | 5 | Bitmap Heap Scan osm_label; Bitmap Index Scan osm_label_places_idx |
| boundaries_osm_line_z9 | 12 | 9 | 156 | Bitmap Heap Scan osm_line_z9; Bitmap Index Scan osm_line_z9_geom_idx |
| protected_osm_polygon_z9 | 11 | 8 | 249 | Bitmap Heap Scan osm_polygon_z9; Bitmap Index Scan osm_polygon_z9_geom_idx |
| water_osm_polygon_z9 | 10 | 12 | 108 | Bitmap Heap Scan osm_polygon_z9; Bitmap Index Scan osm_polygon_z9_geom_idx |
| waterways_osm_line_z9 | 9 | 8 | 429 | Bitmap Heap Scan osm_line_z9; Bitmap Index Scan osm_line_z9_geom_idx |
| ocean_osm_polygon_z9 | 7 | 9 | 0 | Bitmap Heap Scan osm_polygon_z9; Bitmap Index Scan osm_polygon_z9_geom_idx |

### EPSG:3857 z10 (10) 535/347: render 374 ms, encode 19.7 ms, 39 KB, 15 layers, db sum 360 ms

| layer | render ms | db ms | rows | scans |
|---|---|---|---|---|
| roads_fill_osm_line_z12 | 71 | 26 | 11031 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| roads_casing_osm_line_z12 | 70 | 27 | 11031 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| labels_area_osm_label | 47 | 82 | 4 | Bitmap Heap Scan osm_label; Bitmap Index Scan osm_label_geom_idx |
| shields_osm_line_z12 | 40 | 35 | 86 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| landcover_osm_polygon_z12 | 38 | 26 | 4660 | Bitmap Heap Scan osm_polygon_z12; Bitmap Index Scan osm_polygon_z12_geom_idx |
| landuse_osm_polygon_z12 | 24 | 22 | 729 | Bitmap Heap Scan osm_polygon_z12; Bitmap Index Scan osm_polygon_z12_geom_idx |
| protected_osm_polygon_z12 | 23 | 18 | 134 | Bitmap Heap Scan osm_polygon_z12; Bitmap Index Scan osm_polygon_z12_geom_idx |
| rail_osm_line_z12 | 23 | 17 | 2090 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| water_osm_polygon_z12 | 19 | 16 | 68 | Bitmap Heap Scan osm_polygon_z12; Bitmap Index Scan osm_polygon_z12_geom_idx |
| waterways_osm_line_z12 | 16 | 20 | 65 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| boundaries_osm_line_z12 | 16 | 13 | 160 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| landuse_osm_line_z12 | 16 | 19 | 0 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| aeroways_osm_line_z12 | 16 | 18 | 6 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| ocean_osm_polygon_z12 | 14 | 19 | 0 | Bitmap Heap Scan osm_polygon_z12; Bitmap Index Scan osm_polygon_z12_geom_idx |
| places_osm_label | 8 | 2 | 19 | Index Scan osm_label_places_idx |

### EPSG:3857 z12 (12) 2158/1391: render 37 ms, encode 14.3 ms, 22 KB, 20 layers, db sum 24 ms

| layer | render ms | db ms | rows | scans |
|---|---|---|---|---|
| landcover_osm_polygon_z12 | 9 | 3 | 1521 | Index Scan osm_polygon_z12_geom_idx |
| places_osm_label | 3 | 1 | 4 | Index Scan osm_label_places_idx |
| shields_osm_line_z12 | 3 | 2 | 1 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| labels_area_osm_label | 2 | 3 | 0 | Index Scan osm_label_geom_idx |
| roads_casing_osm_line_z12 | 2 | 1 | 269 | Index Scan osm_line_z12_geom_idx |
| roads_fill_osm_line_z12 | 2 | 1 | 270 | Index Scan osm_line_z12_geom_idx |
| protected_osm_polygon_z12 | 2 | 1 | 3 | Index Scan osm_polygon_z12_geom_idx |
| landuse_osm_polygon_z12 | 2 | 1 | 16 | Index Scan osm_polygon_z12_geom_idx |
| ocean_osm_polygon_z12 | 2 | 2 | 0 | Index Scan osm_polygon_z12_geom_idx |
| waterways_osm_line_z12 | 1 | 1 | 85 | Index Scan osm_line_z12_geom_idx |
| boundaries_osm_line_z12 | 1 | 1 | 21 | Index Scan osm_line_z12_geom_idx |
| water_osm_polygon_z12 | 1 | 1 | 4 | Index Scan osm_polygon_z12_geom_idx |
| landuse_osm_line_z12 | 1 | 1 | 0 | Index Scan osm_line_z12_geom_idx |
| labels_line_osm_line_z12 | 1 | 1 | 4 | Index Scan osm_line_z12_geom_idx |
| rail_osm_line_z12 | 1 | 1 | 10 | Index Scan osm_line_z12_geom_idx |
| tunnels_fill_osm_line_z12 | 1 | 1 | 2 | Index Scan osm_line_z12_geom_idx |
| bridges_casing_osm_line_z12 | 1 | 1 | 1 | Index Scan osm_line_z12_geom_idx |
| tunnels_casing_osm_line_z12 | 1 | 1 | 0 | Index Scan osm_line_z12_geom_idx |
| bridges_fill_osm_line_z12 | 1 | 1 | 1 | Index Scan osm_line_z12_geom_idx |
| aeroways_osm_line_z12 | 1 | 1 | 0 | Index Scan osm_line_z12_geom_idx |

### EPSG:3857 z14 (14) 8610/5528: render 37 ms, encode 7.8 ms, 13 KB, 23 layers, db sum 31 ms

| layer | render ms | db ms | rows | scans |
|---|---|---|---|---|
| shields_osm_line | 4 | 3 | 2 | Index Scan osm_line_shields_idx |
| labels_area_osm_label | 4 | 3 | 0 | Index Scan osm_label_geom_idx |
| roads_fill_osm_line | 3 | 3 | 260 | Index Scan osm_line_geom_idx |
| protected_osm_polygon | 3 | 1 | 1 | Index Scan osm_polygon_protected_idx |
| buildings_osm_building | 3 | 2 | 678 | Index Scan osm_building_geom_idx |
| labels_line_osm_line | 2 | 2 | 3 | Index Scan osm_line_labels_idx |
| waterways_osm_line | 2 | 1 | 26 | Index Scan osm_line_waterways_idx |
| landcover_osm_polygon | 2 | 1 | 29 | Index Scan osm_polygon_geom_idx |
| places_osm_label | 2 | 1 | 1 | Index Scan osm_label_places_idx |
| roads_casing_osm_line | 2 | 1 | 108 | Index Scan osm_line_roads_casing_idx |
| landuse_osm_polygon | 2 | 2 | 11 | Index Scan osm_polygon_landuse_idx |
| boundaries_osm_line | 2 | 1 | 1 | Index Scan osm_line_boundaries_idx |
| bridges_fill_osm_line | 1 | 1 | 0 | Index Scan osm_line_bridges_casing_idx |
| water_osm_polygon | 1 | 1 | 4 | Index Scan osm_polygon_water_idx |
| bridges_casing_osm_line | 1 | 1 | 0 | Index Scan osm_line_bridges_casing_idx |
| tunnels_fill_osm_line | 1 | 1 | 1 | Index Scan osm_line_tunnels_casing_idx |
| tunnels_casing_osm_line | 1 | 1 | 1 | Index Scan osm_line_tunnels_casing_idx |
| landuse_osm_line | 1 | 1 | 0 | Index Scan osm_line_landuse_idx |
| places_osm_line | 1 | 1 | 0 | Index Scan osm_line_places_idx |
| roads_fill_osm_polygon | 1 | 1 | 0 | Index Scan osm_polygon_roads_fill_idx |
| rail_osm_line | 1 | 1 | 0 | Index Scan osm_line_rail_idx |
| ocean_osm_polygon | 1 | 1 | 0 | Index Scan osm_polygon_ocean_idx |
| aeroways_osm_line | 1 | 1 | 0 | Index Scan osm_line_aeroways_idx |

### EPSG:3857 z16 (16) 34794/21746: render 34 ms, encode 6.0 ms, 9 KB, 23 layers, db sum 29 ms

| layer | render ms | db ms | rows | scans |
|---|---|---|---|---|
| labels_line_osm_line | 5 | 1 | 4 | Index Scan osm_line_labels_idx |
| landcover_osm_polygon | 3 | 2 | 10 | Index Scan osm_polygon_geom_idx |
| shields_osm_line | 3 | 2 | 1 | Index Scan osm_line_shields_idx |
| roads_fill_osm_line | 3 | 2 | 30 | Index Scan osm_line_geom_idx |
| labels_area_osm_label | 3 | 4 | 0 | Index Scan osm_label_geom_idx |
| landuse_osm_polygon | 2 | 2 | 4 | Index Scan osm_polygon_landuse_idx |
| protected_osm_polygon | 2 | 1 | 1 | Index Scan osm_polygon_protected_idx |
| waterways_osm_line | 2 | 1 | 2 | Index Scan osm_line_waterways_idx |
| boundaries_osm_line | 2 | 1 | 1 | Index Scan osm_line_boundaries_idx |
| ocean_osm_polygon | 2 | 1 | 0 | Index Scan osm_polygon_ocean_idx |
| aeroways_osm_line | 2 | 1 | 0 | Index Scan osm_line_aeroways_idx |
| water_osm_polygon | 2 | 1 | 0 | Index Scan osm_polygon_water_idx |
| roads_casing_osm_line | 2 | 1 | 8 | Index Scan osm_line_roads_casing_idx |
| tunnels_fill_osm_line | 2 | 1 | 0 | Index Scan osm_line_tunnels_casing_idx |
| rail_osm_line | 1 | 1 | 1 | Index Scan osm_line_rail_idx |
| tunnels_casing_osm_line | 1 | 1 | 0 | Index Scan osm_line_tunnels_casing_idx |
| roads_fill_osm_polygon | 1 | 1 | 0 | Index Scan osm_polygon_roads_fill_idx |
| bridges_fill_osm_line | 1 | 1 | 2 | Index Scan osm_line_bridges_casing_idx |
| bridges_casing_osm_line | 1 | 1 | 1 | Index Scan osm_line_bridges_casing_idx |
| places_osm_label | 1 | 1 | 0 | Index Scan osm_label_places_idx |
| landuse_osm_line | 1 | 1 | 0 | Index Scan osm_line_landuse_idx |
| places_osm_line | 1 | 1 | 0 | Index Scan osm_line_places_idx |
| buildings_osm_building | 1 | 1 | 5 | Index Scan osm_building_geom_idx |

