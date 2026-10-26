# Render profile -- 2026-09-30 12:20 UTC

- server http://127.0.0.1:8000, styles `/data/styles/de_sh_20260930_110143/GoogleMapsCompatible`, mapnik 4.3.2, PostgreSQL 17.5 (Debian 17.5-1.pgdg110+1)
- postgres: effective_cache_size=4GB, jit=off, max_parallel_workers_per_gather=2, random_page_cost=4, shared_buffers=2GB, work_mem=64MB
- hardware: aarch64 x 8, 15.8 GB RAM, linux 7.0.12-linuxkit aarch64 (dev stack, Docker Desktop on macOS)
- tile box (lon/lat, given): 8.300 53.400 -- 11.300 55.000, seed 42, 5 tiles with buildings per zoom
- themes: dark, dark_max, dark_min, default, default_max, default_min, hico, hico_max, hico_min, light, light_max, light_min
- crs: EPSG:3857 (GoogleMapsCompatible)

## 1. HTTP: uncached render vs cache hit

Render ms are min / median / max over all themes and tiles at that zoom; hit ms and KB are medians. For a non-3857 CRS "zoom" is the 3857 zoom the tile was picked for; the level actually requested is the closest scale of that TileMatrixSet (in parentheses), and two picks that land in the same coarse tile are fetched once. The first render after a cache clear is consistently slow, so unreported warm-up tiles per CRS are fetched first.

### EPSG:3857

| zoom | level | tiles | render ms | hit ms | KB |
|---|---|---|---|---|---|
| 8 | 8 | 60 | 14 / 49 / 96 | 3.4 | 20 |
| 10 | 10 | 60 | 18 / 65 / 113 | 3.4 | 27 |
| 12 | 12 | 60 | 20 / 34 / 80 | 3.3 | 26 |
| 13 | 13 | 60 | 20 / 35 / 47 | 3.3 | 15 |
| 14 | 14 | 60 | 19 / 27 / 59 | 3.3 | 13 |
| 16 | 16 | 60 | 18 / 26 / 35 | 3.2 | 10 |
| 18 | 18 | 60 | 17 / 25 / 37 | 3.2 | 3 |

| theme | crs | tiles | render ms | z<=12 render ms | z>12 render ms |
|---|---|---|---|---|---|
| dark | EPSG:3857 | 35 | 18 / 33 / 113 | 18 / 51 / 113 | 23 / 29 / 45 |
| dark_max | EPSG:3857 | 35 | 17 / 31 / 80 | 17 / 43 / 80 | 22 / 29 / 37 |
| dark_min | EPSG:3857 | 35 | 14 / 24 / 67 | 14 / 44 / 67 | 18 / 21 / 40 |
| default | EPSG:3857 | 35 | 17 / 35 / 82 | 17 / 46 / 82 | 23 / 31 / 59 |
| default_max | EPSG:3857 | 35 | 20 / 34 / 85 | 20 / 47 / 85 | 22 / 29 / 39 |
| default_min | EPSG:3857 | 35 | 14 / 27 / 65 | 14 / 43 / 65 | 17 / 23 / 40 |
| hico | EPSG:3857 | 35 | 17 / 34 / 96 | 17 / 49 / 96 | 23 / 28 / 39 |
| hico_max | EPSG:3857 | 35 | 17 / 33 / 87 | 17 / 45 / 87 | 23 / 28 / 39 |
| hico_min | EPSG:3857 | 35 | 15 / 26 / 65 | 15 / 42 / 65 | 19 / 23 / 47 |
| light | EPSG:3857 | 35 | 16 / 33 / 88 | 16 / 48 / 88 | 22 / 28 / 42 |
| light_max | EPSG:3857 | 35 | 16 / 30 / 85 | 16 / 45 / 85 | 22 / 28 / 37 |
| light_min | EPSG:3857 | 35 | 16 / 26 / 67 | 16 / 41 / 67 | 17 / 22 / 42 |

Total render time for the 420 tiles: 15.4 s.

<details><summary>Every tile</summary>

| theme | crs | zoom | level | col | row | render ms | hit ms | KB |
|---|---|---|---|---|---|---|---|---|
| dark | EPSG:3857 | 8 | 8 | 135 | 82 | 68 | 3.4 | 30.6 |
| dark | EPSG:3857 | 8 | 8 | 134 | 82 | 47 | 3.5 | 20.1 |
| dark | EPSG:3857 | 8 | 8 | 135 | 81 | 55 | 4.2 | 19.9 |
| dark | EPSG:3857 | 8 | 8 | 134 | 81 | 64 | 3.6 | 36.6 |
| dark | EPSG:3857 | 8 | 8 | 136 | 81 | 18 | 3.2 | 3.4 |
| dark | EPSG:3857 | 10 | 10 | 540 | 326 | 89 | 3.5 | 26.9 |
| dark | EPSG:3857 | 10 | 10 | 538 | 329 | 113 | 3.2 | 27.8 |
| dark | EPSG:3857 | 10 | 10 | 537 | 324 | 68 | 3.4 | 27.3 |
| dark | EPSG:3857 | 10 | 10 | 543 | 329 | 32 | 3.2 | 5.8 |
| dark | EPSG:3857 | 10 | 10 | 541 | 328 | 86 | 3.2 | 35.3 |
| dark | EPSG:3857 | 12 | 12 | 2173 | 1312 | 23 | 3.3 | 2.8 |
| dark | EPSG:3857 | 12 | 12 | 2161 | 1318 | 51 | 33.9 | 34.6 |
| dark | EPSG:3857 | 12 | 12 | 2156 | 1319 | 46 | 3.8 | 32.0 |
| dark | EPSG:3857 | 12 | 12 | 2146 | 1307 | 32 | 3.1 | 18.7 |
| dark | EPSG:3857 | 12 | 12 | 2169 | 1313 | 35 | 3.4 | 28.3 |
| dark | EPSG:3857 | 13 | 13 | 4331 | 2620 | 39 | 3.6 | 15.2 |
| dark | EPSG:3857 | 13 | 13 | 4303 | 2613 | 40 | 3.3 | 26.4 |
| dark | EPSG:3857 | 13 | 13 | 4319 | 2642 | 45 | 3.2 | 27.1 |
| dark | EPSG:3857 | 13 | 13 | 4305 | 2613 | 28 | 3.5 | 13.8 |
| dark | EPSG:3857 | 13 | 13 | 4336 | 2620 | 40 | 3.4 | 16.9 |
| dark | EPSG:3857 | 14 | 14 | 8676 | 5241 | 30 | 3.3 | 12.6 |
| dark | EPSG:3857 | 14 | 14 | 8572 | 5191 | 30 | 3.2 | 14.8 |
| dark | EPSG:3857 | 14 | 14 | 8674 | 5291 | 24 | 3.0 | 6.8 |
| dark | EPSG:3857 | 14 | 14 | 8634 | 5238 | 34 | 3.2 | 22.0 |
| dark | EPSG:3857 | 14 | 14 | 8605 | 5198 | 26 | 3.2 | 12.8 |
| dark | EPSG:3857 | 16 | 16 | 34510 | 21123 | 25 | 3.1 | 10.9 |
| dark | EPSG:3857 | 16 | 16 | 34537 | 20837 | 29 | 3.3 | 4.8 |
| dark | EPSG:3857 | 16 | 16 | 34498 | 21060 | 28 | 3.4 | 17.7 |
| dark | EPSG:3857 | 16 | 16 | 34509 | 21090 | 26 | 3.2 | 10.8 |
| dark | EPSG:3857 | 16 | 16 | 34423 | 20838 | 23 | 3.0 | 4.3 |
| dark | EPSG:3857 | 18 | 18 | 138041 | 84364 | 26 | 3.1 | 2.2 |
| dark | EPSG:3857 | 18 | 18 | 137453 | 83057 | 25 | 3.0 | 1.4 |
| dark | EPSG:3857 | 18 | 18 | 138517 | 84120 | 24 | 3.7 | 3.4 |
| dark | EPSG:3857 | 18 | 18 | 137119 | 83066 | 37 | 3.8 | 5.6 |
| dark | EPSG:3857 | 18 | 18 | 137650 | 83970 | 33 | 3.9 | 10.5 |
| dark_max | EPSG:3857 | 8 | 8 | 135 | 82 | 68 | 3.6 | 31.0 |
| dark_max | EPSG:3857 | 8 | 8 | 134 | 82 | 43 | 3.1 | 20.6 |
| dark_max | EPSG:3857 | 8 | 8 | 135 | 81 | 50 | 3.2 | 21.0 |
| dark_max | EPSG:3857 | 8 | 8 | 134 | 81 | 62 | 3.5 | 37.1 |
| dark_max | EPSG:3857 | 8 | 8 | 136 | 81 | 17 | 3.3 | 6.8 |
| dark_max | EPSG:3857 | 10 | 10 | 540 | 326 | 79 | 3.4 | 27.4 |
| dark_max | EPSG:3857 | 10 | 10 | 538 | 329 | 80 | 3.6 | 27.8 |
| dark_max | EPSG:3857 | 10 | 10 | 537 | 324 | 57 | 3.4 | 27.3 |
| dark_max | EPSG:3857 | 10 | 10 | 543 | 329 | 26 | 3.4 | 5.8 |
| dark_max | EPSG:3857 | 10 | 10 | 541 | 328 | 76 | 3.3 | 35.4 |
| dark_max | EPSG:3857 | 12 | 12 | 2173 | 1312 | 23 | 3.3 | 2.8 |
| dark_max | EPSG:3857 | 12 | 12 | 2161 | 1318 | 42 | 3.6 | 34.6 |
| dark_max | EPSG:3857 | 12 | 12 | 2156 | 1319 | 40 | 3.6 | 32.0 |
| dark_max | EPSG:3857 | 12 | 12 | 2146 | 1307 | 29 | 3.2 | 18.7 |
| dark_max | EPSG:3857 | 12 | 12 | 2169 | 1313 | 33 | 3.4 | 28.3 |
| dark_max | EPSG:3857 | 13 | 13 | 4331 | 2620 | 36 | 3.3 | 15.2 |
| dark_max | EPSG:3857 | 13 | 13 | 4303 | 2613 | 33 | 3.1 | 26.4 |
| dark_max | EPSG:3857 | 13 | 13 | 4319 | 2642 | 37 | 3.4 | 27.1 |
| dark_max | EPSG:3857 | 13 | 13 | 4305 | 2613 | 26 | 3.1 | 13.8 |
| dark_max | EPSG:3857 | 13 | 13 | 4336 | 2620 | 35 | 3.3 | 16.9 |
| dark_max | EPSG:3857 | 14 | 14 | 8676 | 5241 | 30 | 3.1 | 12.6 |
| dark_max | EPSG:3857 | 14 | 14 | 8572 | 5191 | 26 | 3.3 | 14.8 |
| dark_max | EPSG:3857 | 14 | 14 | 8674 | 5291 | 22 | 3.0 | 6.8 |
| dark_max | EPSG:3857 | 14 | 14 | 8634 | 5238 | 35 | 3.5 | 22.0 |
| dark_max | EPSG:3857 | 14 | 14 | 8605 | 5198 | 27 | 3.2 | 12.8 |
| dark_max | EPSG:3857 | 16 | 16 | 34510 | 21123 | 28 | 3.5 | 10.9 |
| dark_max | EPSG:3857 | 16 | 16 | 34537 | 20837 | 31 | 3.6 | 4.8 |
| dark_max | EPSG:3857 | 16 | 16 | 34498 | 21060 | 29 | 3.0 | 17.7 |
| dark_max | EPSG:3857 | 16 | 16 | 34509 | 21090 | 26 | 3.2 | 10.8 |
| dark_max | EPSG:3857 | 16 | 16 | 34423 | 20838 | 22 | 3.0 | 4.3 |
| dark_max | EPSG:3857 | 18 | 18 | 138041 | 84364 | 30 | 3.4 | 2.2 |
| dark_max | EPSG:3857 | 18 | 18 | 137453 | 83057 | 24 | 3.1 | 1.4 |
| dark_max | EPSG:3857 | 18 | 18 | 138517 | 84120 | 26 | 3.0 | 4.0 |
| dark_max | EPSG:3857 | 18 | 18 | 137119 | 83066 | 35 | 3.0 | 5.6 |
| dark_max | EPSG:3857 | 18 | 18 | 137650 | 83970 | 26 | 3.3 | 10.5 |
| dark_min | EPSG:3857 | 8 | 8 | 135 | 82 | 56 | 3.6 | 30.2 |
| dark_min | EPSG:3857 | 8 | 8 | 134 | 82 | 44 | 3.3 | 20.3 |
| dark_min | EPSG:3857 | 8 | 8 | 135 | 81 | 46 | 3.3 | 19.2 |
| dark_min | EPSG:3857 | 8 | 8 | 134 | 81 | 54 | 3.3 | 36.9 |
| dark_min | EPSG:3857 | 8 | 8 | 136 | 81 | 14 | 3.2 | 3.2 |
| dark_min | EPSG:3857 | 10 | 10 | 540 | 326 | 67 | 4.3 | 26.6 |
| dark_min | EPSG:3857 | 10 | 10 | 538 | 329 | 63 | 3.4 | 27.9 |
| dark_min | EPSG:3857 | 10 | 10 | 537 | 324 | 48 | 3.5 | 27.2 |
| dark_min | EPSG:3857 | 10 | 10 | 543 | 329 | 19 | 3.1 | 3.2 |
| dark_min | EPSG:3857 | 10 | 10 | 541 | 328 | 64 | 3.5 | 34.4 |
| dark_min | EPSG:3857 | 12 | 12 | 2173 | 1312 | 20 | 3.1 | 2.7 |
| dark_min | EPSG:3857 | 12 | 12 | 2161 | 1318 | 39 | 3.3 | 33.6 |
| dark_min | EPSG:3857 | 12 | 12 | 2156 | 1319 | 32 | 3.1 | 26.3 |
| dark_min | EPSG:3857 | 12 | 12 | 2146 | 1307 | 21 | 2.9 | 13.6 |
| dark_min | EPSG:3857 | 12 | 12 | 2169 | 1313 | 29 | 3.1 | 26.5 |
| dark_min | EPSG:3857 | 13 | 13 | 4331 | 2620 | 29 | 3.0 | 11.3 |
| dark_min | EPSG:3857 | 13 | 13 | 4303 | 2613 | 30 | 3.2 | 14.1 |
| dark_min | EPSG:3857 | 13 | 13 | 4319 | 2642 | 40 | 3.2 | 24.4 |
| dark_min | EPSG:3857 | 13 | 13 | 4305 | 2613 | 20 | 2.9 | 11.3 |
| dark_min | EPSG:3857 | 13 | 13 | 4336 | 2620 | 29 | 3.3 | 15.2 |
| dark_min | EPSG:3857 | 14 | 14 | 8676 | 5241 | 26 | 3.2 | 10.9 |
| dark_min | EPSG:3857 | 14 | 14 | 8572 | 5191 | 21 | 3.1 | 11.2 |
| dark_min | EPSG:3857 | 14 | 14 | 8674 | 5291 | 19 | 3.3 | 4.3 |
| dark_min | EPSG:3857 | 14 | 14 | 8634 | 5238 | 30 | 3.1 | 17.8 |
| dark_min | EPSG:3857 | 14 | 14 | 8605 | 5198 | 21 | 3.2 | 12.2 |
| dark_min | EPSG:3857 | 16 | 16 | 34510 | 21123 | 21 | 3.3 | 9.7 |
| dark_min | EPSG:3857 | 16 | 16 | 34537 | 20837 | 24 | 3.1 | 4.3 |
| dark_min | EPSG:3857 | 16 | 16 | 34498 | 21060 | 24 | 3.4 | 11.5 |
| dark_min | EPSG:3857 | 16 | 16 | 34509 | 21090 | 22 | 3.2 | 9.5 |
| dark_min | EPSG:3857 | 16 | 16 | 34423 | 20838 | 18 | 3.1 | 4.1 |
| dark_min | EPSG:3857 | 18 | 18 | 138041 | 84364 | 20 | 3.8 | 2.2 |
| dark_min | EPSG:3857 | 18 | 18 | 137453 | 83057 | 18 | 3.2 | 0.5 |
| dark_min | EPSG:3857 | 18 | 18 | 138517 | 84120 | 20 | 3.4 | 2.9 |
| dark_min | EPSG:3857 | 18 | 18 | 137119 | 83066 | 18 | 3.0 | 3.2 |
| dark_min | EPSG:3857 | 18 | 18 | 137650 | 83970 | 20 | 3.0 | 7.0 |
| default | EPSG:3857 | 8 | 8 | 135 | 82 | 61 | 3.4 | 31.7 |
| default | EPSG:3857 | 8 | 8 | 134 | 82 | 46 | 3.3 | 20.7 |
| default | EPSG:3857 | 8 | 8 | 135 | 81 | 48 | 3.2 | 20.4 |
| default | EPSG:3857 | 8 | 8 | 134 | 81 | 60 | 4.7 | 36.0 |
| default | EPSG:3857 | 8 | 8 | 136 | 81 | 17 | 3.5 | 3.5 |
| default | EPSG:3857 | 10 | 10 | 540 | 326 | 82 | 4.4 | 26.4 |
| default | EPSG:3857 | 10 | 10 | 538 | 329 | 79 | 3.4 | 27.8 |
| default | EPSG:3857 | 10 | 10 | 537 | 324 | 55 | 3.3 | 26.4 |
| default | EPSG:3857 | 10 | 10 | 543 | 329 | 26 | 3.3 | 5.9 |
| default | EPSG:3857 | 10 | 10 | 541 | 328 | 75 | 3.2 | 32.9 |
| default | EPSG:3857 | 12 | 12 | 2173 | 1312 | 20 | 3.1 | 2.4 |
| default | EPSG:3857 | 12 | 12 | 2161 | 1318 | 46 | 3.3 | 33.1 |
| default | EPSG:3857 | 12 | 12 | 2156 | 1319 | 40 | 3.8 | 31.8 |
| default | EPSG:3857 | 12 | 12 | 2146 | 1307 | 29 | 3.4 | 18.3 |
| default | EPSG:3857 | 12 | 12 | 2169 | 1313 | 35 | 3.2 | 27.2 |
| default | EPSG:3857 | 13 | 13 | 4331 | 2620 | 40 | 3.5 | 14.4 |
| default | EPSG:3857 | 13 | 13 | 4303 | 2613 | 34 | 3.3 | 25.4 |
| default | EPSG:3857 | 13 | 13 | 4319 | 2642 | 39 | 3.3 | 26.0 |
| default | EPSG:3857 | 13 | 13 | 4305 | 2613 | 32 | 3.7 | 13.5 |
| default | EPSG:3857 | 13 | 13 | 4336 | 2620 | 37 | 3.3 | 16.2 |
| default | EPSG:3857 | 14 | 14 | 8676 | 5241 | 33 | 3.3 | 12.4 |
| default | EPSG:3857 | 14 | 14 | 8572 | 5191 | 28 | 3.3 | 13.8 |
| default | EPSG:3857 | 14 | 14 | 8674 | 5291 | 23 | 3.2 | 6.6 |
| default | EPSG:3857 | 14 | 14 | 8634 | 5238 | 36 | 3.7 | 20.5 |
| default | EPSG:3857 | 14 | 14 | 8605 | 5198 | 59 | 3.6 | 12.6 |
| default | EPSG:3857 | 16 | 16 | 34510 | 21123 | 28 | 3.3 | 10.9 |
| default | EPSG:3857 | 16 | 16 | 34537 | 20837 | 35 | 4.2 | 4.6 |
| default | EPSG:3857 | 16 | 16 | 34498 | 21060 | 30 | 3.5 | 17.5 |
| default | EPSG:3857 | 16 | 16 | 34509 | 21090 | 27 | 3.2 | 11.0 |
| default | EPSG:3857 | 16 | 16 | 34423 | 20838 | 23 | 3.6 | 3.4 |
| default | EPSG:3857 | 18 | 18 | 138041 | 84364 | 28 | 3.5 | 2.2 |
| default | EPSG:3857 | 18 | 18 | 137453 | 83057 | 26 | 3.4 | 1.3 |
| default | EPSG:3857 | 18 | 18 | 138517 | 84120 | 27 | 3.2 | 3.4 |
| default | EPSG:3857 | 18 | 18 | 137119 | 83066 | 36 | 3.2 | 5.4 |
| default | EPSG:3857 | 18 | 18 | 137650 | 83970 | 28 | 4.0 | 10.7 |
| default_max | EPSG:3857 | 8 | 8 | 135 | 82 | 68 | 3.5 | 32.1 |
| default_max | EPSG:3857 | 8 | 8 | 134 | 82 | 47 | 3.3 | 21.0 |
| default_max | EPSG:3857 | 8 | 8 | 135 | 81 | 50 | 3.2 | 21.0 |
| default_max | EPSG:3857 | 8 | 8 | 134 | 81 | 63 | 3.6 | 36.4 |
| default_max | EPSG:3857 | 8 | 8 | 136 | 81 | 20 | 3.3 | 6.9 |
| default_max | EPSG:3857 | 10 | 10 | 540 | 326 | 85 | 3.4 | 26.5 |
| default_max | EPSG:3857 | 10 | 10 | 538 | 329 | 82 | 3.9 | 27.9 |
| default_max | EPSG:3857 | 10 | 10 | 537 | 324 | 56 | 3.6 | 26.4 |
| default_max | EPSG:3857 | 10 | 10 | 543 | 329 | 26 | 3.2 | 5.9 |
| default_max | EPSG:3857 | 10 | 10 | 541 | 328 | 82 | 4.0 | 33.0 |
| default_max | EPSG:3857 | 12 | 12 | 2173 | 1312 | 24 | 3.2 | 2.4 |
| default_max | EPSG:3857 | 12 | 12 | 2161 | 1318 | 43 | 4.1 | 33.1 |
| default_max | EPSG:3857 | 12 | 12 | 2156 | 1319 | 42 | 3.5 | 31.8 |
| default_max | EPSG:3857 | 12 | 12 | 2146 | 1307 | 29 | 3.6 | 18.3 |
| default_max | EPSG:3857 | 12 | 12 | 2169 | 1313 | 35 | 3.4 | 27.2 |
| default_max | EPSG:3857 | 13 | 13 | 4331 | 2620 | 35 | 3.5 | 14.4 |
| default_max | EPSG:3857 | 13 | 13 | 4303 | 2613 | 36 | 3.5 | 25.4 |
| default_max | EPSG:3857 | 13 | 13 | 4319 | 2642 | 39 | 3.3 | 26.0 |
| default_max | EPSG:3857 | 13 | 13 | 4305 | 2613 | 28 | 3.3 | 13.5 |
| default_max | EPSG:3857 | 13 | 13 | 4336 | 2620 | 35 | 3.8 | 16.2 |
| default_max | EPSG:3857 | 14 | 14 | 8676 | 5241 | 36 | 3.2 | 12.4 |
| default_max | EPSG:3857 | 14 | 14 | 8572 | 5191 | 28 | 3.2 | 13.8 |
| default_max | EPSG:3857 | 14 | 14 | 8674 | 5291 | 24 | 3.6 | 6.6 |
| default_max | EPSG:3857 | 14 | 14 | 8634 | 5238 | 35 | 3.2 | 20.5 |
| default_max | EPSG:3857 | 14 | 14 | 8605 | 5198 | 26 | 3.0 | 12.6 |
| default_max | EPSG:3857 | 16 | 16 | 34510 | 21123 | 26 | 3.6 | 10.9 |
| default_max | EPSG:3857 | 16 | 16 | 34537 | 20837 | 31 | 3.5 | 4.6 |
| default_max | EPSG:3857 | 16 | 16 | 34498 | 21060 | 30 | 3.2 | 17.5 |
| default_max | EPSG:3857 | 16 | 16 | 34509 | 21090 | 27 | 3.4 | 11.0 |
| default_max | EPSG:3857 | 16 | 16 | 34423 | 20838 | 22 | 3.1 | 3.4 |
| default_max | EPSG:3857 | 18 | 18 | 138041 | 84364 | 27 | 3.6 | 2.2 |
| default_max | EPSG:3857 | 18 | 18 | 137453 | 83057 | 24 | 3.0 | 1.3 |
| default_max | EPSG:3857 | 18 | 18 | 138517 | 84120 | 25 | 3.0 | 3.9 |
| default_max | EPSG:3857 | 18 | 18 | 137119 | 83066 | 34 | 3.0 | 5.4 |
| default_max | EPSG:3857 | 18 | 18 | 137650 | 83970 | 29 | 3.3 | 10.7 |
| default_min | EPSG:3857 | 8 | 8 | 135 | 82 | 60 | 3.4 | 31.5 |
| default_min | EPSG:3857 | 8 | 8 | 134 | 82 | 43 | 3.1 | 20.5 |
| default_min | EPSG:3857 | 8 | 8 | 135 | 81 | 44 | 3.2 | 19.8 |
| default_min | EPSG:3857 | 8 | 8 | 134 | 81 | 56 | 3.6 | 35.9 |
| default_min | EPSG:3857 | 8 | 8 | 136 | 81 | 14 | 3.0 | 3.2 |
| default_min | EPSG:3857 | 10 | 10 | 540 | 326 | 65 | 3.4 | 26.0 |
| default_min | EPSG:3857 | 10 | 10 | 538 | 329 | 61 | 3.3 | 27.1 |
| default_min | EPSG:3857 | 10 | 10 | 537 | 324 | 46 | 3.2 | 26.5 |
| default_min | EPSG:3857 | 10 | 10 | 543 | 329 | 18 | 3.1 | 3.5 |
| default_min | EPSG:3857 | 10 | 10 | 541 | 328 | 63 | 3.3 | 33.6 |
| default_min | EPSG:3857 | 12 | 12 | 2173 | 1312 | 20 | 3.4 | 2.3 |
| default_min | EPSG:3857 | 12 | 12 | 2161 | 1318 | 40 | 3.3 | 32.0 |
| default_min | EPSG:3857 | 12 | 12 | 2156 | 1319 | 39 | 3.7 | 27.1 |
| default_min | EPSG:3857 | 12 | 12 | 2146 | 1307 | 23 | 3.5 | 13.0 |
| default_min | EPSG:3857 | 12 | 12 | 2169 | 1313 | 31 | 3.5 | 25.6 |
| default_min | EPSG:3857 | 13 | 13 | 4331 | 2620 | 32 | 3.2 | 11.7 |
| default_min | EPSG:3857 | 13 | 13 | 4303 | 2613 | 31 | 3.1 | 13.6 |
| default_min | EPSG:3857 | 13 | 13 | 4319 | 2642 | 40 | 3.7 | 23.6 |
| default_min | EPSG:3857 | 13 | 13 | 4305 | 2613 | 21 | 3.3 | 11.2 |
| default_min | EPSG:3857 | 13 | 13 | 4336 | 2620 | 30 | 3.3 | 14.9 |
| default_min | EPSG:3857 | 14 | 14 | 8676 | 5241 | 28 | 3.5 | 11.0 |
| default_min | EPSG:3857 | 14 | 14 | 8572 | 5191 | 22 | 3.0 | 11.2 |
| default_min | EPSG:3857 | 14 | 14 | 8674 | 5291 | 19 | 3.2 | 4.0 |
| default_min | EPSG:3857 | 14 | 14 | 8634 | 5238 | 31 | 3.4 | 17.3 |
| default_min | EPSG:3857 | 14 | 14 | 8605 | 5198 | 23 | 3.2 | 12.4 |
| default_min | EPSG:3857 | 16 | 16 | 34510 | 21123 | 21 | 3.2 | 10.3 |
| default_min | EPSG:3857 | 16 | 16 | 34537 | 20837 | 27 | 3.2 | 4.0 |
| default_min | EPSG:3857 | 16 | 16 | 34498 | 21060 | 23 | 3.1 | 12.5 |
| default_min | EPSG:3857 | 16 | 16 | 34509 | 21090 | 23 | 3.7 | 10.2 |
| default_min | EPSG:3857 | 16 | 16 | 34423 | 20838 | 21 | 3.8 | 3.2 |
| default_min | EPSG:3857 | 18 | 18 | 138041 | 84364 | 21 | 3.6 | 2.2 |
| default_min | EPSG:3857 | 18 | 18 | 137453 | 83057 | 18 | 3.2 | 0.9 |
| default_min | EPSG:3857 | 18 | 18 | 138517 | 84120 | 19 | 3.2 | 2.9 |
| default_min | EPSG:3857 | 18 | 18 | 137119 | 83066 | 17 | 3.0 | 3.0 |
| default_min | EPSG:3857 | 18 | 18 | 137650 | 83970 | 20 | 3.1 | 7.1 |
| hico | EPSG:3857 | 8 | 8 | 135 | 82 | 96 | 11.4 | 30.4 |
| hico | EPSG:3857 | 8 | 8 | 134 | 82 | 54 | 3.3 | 20.3 |
| hico | EPSG:3857 | 8 | 8 | 135 | 81 | 49 | 3.5 | 20.0 |
| hico | EPSG:3857 | 8 | 8 | 134 | 81 | 70 | 3.6 | 35.0 |
| hico | EPSG:3857 | 8 | 8 | 136 | 81 | 17 | 3.6 | 4.5 |
| hico | EPSG:3857 | 10 | 10 | 540 | 326 | 87 | 3.6 | 27.1 |
| hico | EPSG:3857 | 10 | 10 | 538 | 329 | 85 | 3.7 | 27.9 |
| hico | EPSG:3857 | 10 | 10 | 537 | 324 | 60 | 3.5 | 27.7 |
| hico | EPSG:3857 | 10 | 10 | 543 | 329 | 26 | 3.2 | 5.3 |
| hico | EPSG:3857 | 10 | 10 | 541 | 328 | 84 | 3.7 | 35.8 |
| hico | EPSG:3857 | 12 | 12 | 2173 | 1312 | 21 | 3.0 | 3.2 |
| hico | EPSG:3857 | 12 | 12 | 2161 | 1318 | 43 | 3.1 | 35.2 |
| hico | EPSG:3857 | 12 | 12 | 2156 | 1319 | 40 | 3.3 | 32.9 |
| hico | EPSG:3857 | 12 | 12 | 2146 | 1307 | 29 | 3.8 | 18.6 |
| hico | EPSG:3857 | 12 | 12 | 2169 | 1313 | 36 | 3.1 | 27.8 |
| hico | EPSG:3857 | 13 | 13 | 4331 | 2620 | 36 | 3.6 | 15.1 |
| hico | EPSG:3857 | 13 | 13 | 4303 | 2613 | 34 | 3.3 | 25.7 |
| hico | EPSG:3857 | 13 | 13 | 4319 | 2642 | 38 | 4.0 | 26.5 |
| hico | EPSG:3857 | 13 | 13 | 4305 | 2613 | 28 | 4.5 | 14.2 |
| hico | EPSG:3857 | 13 | 13 | 4336 | 2620 | 39 | 3.2 | 17.5 |
| hico | EPSG:3857 | 14 | 14 | 8676 | 5241 | 35 | 3.3 | 13.0 |
| hico | EPSG:3857 | 14 | 14 | 8572 | 5191 | 28 | 3.7 | 14.8 |
| hico | EPSG:3857 | 14 | 14 | 8674 | 5291 | 24 | 3.5 | 6.7 |
| hico | EPSG:3857 | 14 | 14 | 8634 | 5238 | 36 | 4.2 | 21.8 |
| hico | EPSG:3857 | 14 | 14 | 8605 | 5198 | 28 | 3.3 | 13.8 |
| hico | EPSG:3857 | 16 | 16 | 34510 | 21123 | 31 | 4.0 | 11.4 |
| hico | EPSG:3857 | 16 | 16 | 34537 | 20837 | 31 | 3.2 | 5.1 |
| hico | EPSG:3857 | 16 | 16 | 34498 | 21060 | 28 | 3.3 | 20.3 |
| hico | EPSG:3857 | 16 | 16 | 34509 | 21090 | 25 | 3.2 | 11.4 |
| hico | EPSG:3857 | 16 | 16 | 34423 | 20838 | 23 | 3.4 | 4.8 |
| hico | EPSG:3857 | 18 | 18 | 138041 | 84364 | 26 | 3.2 | 2.8 |
| hico | EPSG:3857 | 18 | 18 | 137453 | 83057 | 24 | 3.6 | 1.9 |
| hico | EPSG:3857 | 18 | 18 | 138517 | 84120 | 27 | 3.6 | 4.0 |
| hico | EPSG:3857 | 18 | 18 | 137119 | 83066 | 37 | 3.9 | 6.6 |
| hico | EPSG:3857 | 18 | 18 | 137650 | 83970 | 28 | 3.2 | 11.1 |
| hico_max | EPSG:3857 | 8 | 8 | 135 | 82 | 65 | 3.1 | 30.5 |
| hico_max | EPSG:3857 | 8 | 8 | 134 | 82 | 45 | 3.4 | 20.4 |
| hico_max | EPSG:3857 | 8 | 8 | 135 | 81 | 52 | 3.6 | 20.1 |
| hico_max | EPSG:3857 | 8 | 8 | 134 | 81 | 66 | 3.6 | 35.2 |
| hico_max | EPSG:3857 | 8 | 8 | 136 | 81 | 17 | 3.5 | 5.9 |
| hico_max | EPSG:3857 | 10 | 10 | 540 | 326 | 87 | 3.4 | 27.1 |
| hico_max | EPSG:3857 | 10 | 10 | 538 | 329 | 80 | 3.6 | 27.9 |
| hico_max | EPSG:3857 | 10 | 10 | 537 | 324 | 85 | 3.8 | 27.7 |
| hico_max | EPSG:3857 | 10 | 10 | 543 | 329 | 28 | 3.3 | 5.3 |
| hico_max | EPSG:3857 | 10 | 10 | 541 | 328 | 82 | 4.0 | 35.7 |
| hico_max | EPSG:3857 | 12 | 12 | 2173 | 1312 | 25 | 3.2 | 3.2 |
| hico_max | EPSG:3857 | 12 | 12 | 2161 | 1318 | 45 | 3.8 | 35.2 |
| hico_max | EPSG:3857 | 12 | 12 | 2156 | 1319 | 41 | 3.4 | 32.9 |
| hico_max | EPSG:3857 | 12 | 12 | 2146 | 1307 | 28 | 3.6 | 18.6 |
| hico_max | EPSG:3857 | 12 | 12 | 2169 | 1313 | 35 | 3.5 | 27.8 |
| hico_max | EPSG:3857 | 13 | 13 | 4331 | 2620 | 39 | 3.4 | 15.1 |
| hico_max | EPSG:3857 | 13 | 13 | 4303 | 2613 | 36 | 3.3 | 25.7 |
| hico_max | EPSG:3857 | 13 | 13 | 4319 | 2642 | 38 | 3.1 | 26.5 |
| hico_max | EPSG:3857 | 13 | 13 | 4305 | 2613 | 27 | 3.2 | 14.2 |
| hico_max | EPSG:3857 | 13 | 13 | 4336 | 2620 | 35 | 3.2 | 17.5 |
| hico_max | EPSG:3857 | 14 | 14 | 8676 | 5241 | 36 | 3.5 | 13.0 |
| hico_max | EPSG:3857 | 14 | 14 | 8572 | 5191 | 29 | 3.5 | 14.8 |
| hico_max | EPSG:3857 | 14 | 14 | 8674 | 5291 | 23 | 3.5 | 6.7 |
| hico_max | EPSG:3857 | 14 | 14 | 8634 | 5238 | 36 | 3.3 | 21.8 |
| hico_max | EPSG:3857 | 14 | 14 | 8605 | 5198 | 25 | 3.1 | 13.8 |
| hico_max | EPSG:3857 | 16 | 16 | 34510 | 21123 | 28 | 3.5 | 11.4 |
| hico_max | EPSG:3857 | 16 | 16 | 34537 | 20837 | 30 | 3.8 | 5.1 |
| hico_max | EPSG:3857 | 16 | 16 | 34498 | 21060 | 30 | 3.0 | 20.3 |
| hico_max | EPSG:3857 | 16 | 16 | 34509 | 21090 | 26 | 3.0 | 11.4 |
| hico_max | EPSG:3857 | 16 | 16 | 34423 | 20838 | 23 | 3.2 | 4.8 |
| hico_max | EPSG:3857 | 18 | 18 | 138041 | 84364 | 28 | 3.2 | 2.8 |
| hico_max | EPSG:3857 | 18 | 18 | 137453 | 83057 | 26 | 3.2 | 1.9 |
| hico_max | EPSG:3857 | 18 | 18 | 138517 | 84120 | 26 | 3.0 | 4.6 |
| hico_max | EPSG:3857 | 18 | 18 | 137119 | 83066 | 33 | 3.6 | 6.6 |
| hico_max | EPSG:3857 | 18 | 18 | 137650 | 83970 | 27 | 3.4 | 11.1 |
| hico_min | EPSG:3857 | 8 | 8 | 135 | 82 | 65 | 3.4 | 30.4 |
| hico_min | EPSG:3857 | 8 | 8 | 134 | 82 | 42 | 3.7 | 20.1 |
| hico_min | EPSG:3857 | 8 | 8 | 135 | 81 | 46 | 3.5 | 19.2 |
| hico_min | EPSG:3857 | 8 | 8 | 134 | 81 | 57 | 3.6 | 35.7 |
| hico_min | EPSG:3857 | 8 | 8 | 136 | 81 | 15 | 3.1 | 4.1 |
| hico_min | EPSG:3857 | 10 | 10 | 540 | 326 | 64 | 3.6 | 27.2 |
| hico_min | EPSG:3857 | 10 | 10 | 538 | 329 | 63 | 3.5 | 27.6 |
| hico_min | EPSG:3857 | 10 | 10 | 537 | 324 | 49 | 3.1 | 27.9 |
| hico_min | EPSG:3857 | 10 | 10 | 543 | 329 | 19 | 3.3 | 3.5 |
| hico_min | EPSG:3857 | 10 | 10 | 541 | 328 | 64 | 4.1 | 35.4 |
| hico_min | EPSG:3857 | 12 | 12 | 2173 | 1312 | 20 | 3.1 | 3.3 |
| hico_min | EPSG:3857 | 12 | 12 | 2161 | 1318 | 42 | 3.5 | 34.2 |
| hico_min | EPSG:3857 | 12 | 12 | 2156 | 1319 | 36 | 3.3 | 29.4 |
| hico_min | EPSG:3857 | 12 | 12 | 2146 | 1307 | 22 | 3.1 | 14.3 |
| hico_min | EPSG:3857 | 12 | 12 | 2169 | 1313 | 31 | 3.2 | 27.8 |
| hico_min | EPSG:3857 | 13 | 13 | 4331 | 2620 | 31 | 3.4 | 12.9 |
| hico_min | EPSG:3857 | 13 | 13 | 4303 | 2613 | 32 | 3.9 | 15.8 |
| hico_min | EPSG:3857 | 13 | 13 | 4319 | 2642 | 47 | 3.5 | 25.5 |
| hico_min | EPSG:3857 | 13 | 13 | 4305 | 2613 | 23 | 3.2 | 12.2 |
| hico_min | EPSG:3857 | 13 | 13 | 4336 | 2620 | 32 | 3.3 | 16.3 |
| hico_min | EPSG:3857 | 14 | 14 | 8676 | 5241 | 27 | 3.5 | 11.9 |
| hico_min | EPSG:3857 | 14 | 14 | 8572 | 5191 | 23 | 3.2 | 12.5 |
| hico_min | EPSG:3857 | 14 | 14 | 8674 | 5291 | 22 | 3.7 | 4.3 |
| hico_min | EPSG:3857 | 14 | 14 | 8634 | 5238 | 33 | 3.4 | 19.3 |
| hico_min | EPSG:3857 | 14 | 14 | 8605 | 5198 | 22 | 3.1 | 13.5 |
| hico_min | EPSG:3857 | 16 | 16 | 34510 | 21123 | 22 | 3.3 | 11.0 |
| hico_min | EPSG:3857 | 16 | 16 | 34537 | 20837 | 26 | 3.4 | 4.9 |
| hico_min | EPSG:3857 | 16 | 16 | 34498 | 21060 | 22 | 3.0 | 13.7 |
| hico_min | EPSG:3857 | 16 | 16 | 34509 | 21090 | 25 | 4.0 | 10.8 |
| hico_min | EPSG:3857 | 16 | 16 | 34423 | 20838 | 21 | 3.3 | 4.8 |
| hico_min | EPSG:3857 | 18 | 18 | 138041 | 84364 | 22 | 3.7 | 2.8 |
| hico_min | EPSG:3857 | 18 | 18 | 137453 | 83057 | 19 | 3.1 | 1.0 |
| hico_min | EPSG:3857 | 18 | 18 | 138517 | 84120 | 19 | 3.7 | 3.6 |
| hico_min | EPSG:3857 | 18 | 18 | 137119 | 83066 | 21 | 3.3 | 3.9 |
| hico_min | EPSG:3857 | 18 | 18 | 137650 | 83970 | 22 | 3.3 | 7.7 |
| light | EPSG:3857 | 8 | 8 | 135 | 82 | 62 | 3.4 | 29.8 |
| light | EPSG:3857 | 8 | 8 | 134 | 82 | 45 | 3.2 | 19.7 |
| light | EPSG:3857 | 8 | 8 | 135 | 81 | 48 | 3.3 | 18.6 |
| light | EPSG:3857 | 8 | 8 | 134 | 81 | 88 | 4.0 | 33.6 |
| light | EPSG:3857 | 8 | 8 | 136 | 81 | 16 | 3.0 | 3.2 |
| light | EPSG:3857 | 10 | 10 | 540 | 326 | 82 | 3.5 | 25.3 |
| light | EPSG:3857 | 10 | 10 | 538 | 329 | 80 | 3.5 | 27.1 |
| light | EPSG:3857 | 10 | 10 | 537 | 324 | 54 | 3.5 | 25.2 |
| light | EPSG:3857 | 10 | 10 | 543 | 329 | 27 | 3.3 | 5.7 |
| light | EPSG:3857 | 10 | 10 | 541 | 328 | 77 | 3.5 | 33.1 |
| light | EPSG:3857 | 12 | 12 | 2173 | 1312 | 21 | 3.3 | 2.2 |
| light | EPSG:3857 | 12 | 12 | 2161 | 1318 | 44 | 4.0 | 32.3 |
| light | EPSG:3857 | 12 | 12 | 2156 | 1319 | 42 | 3.8 | 30.1 |
| light | EPSG:3857 | 12 | 12 | 2146 | 1307 | 30 | 5.4 | 18.3 |
| light | EPSG:3857 | 12 | 12 | 2169 | 1313 | 80 | 4.0 | 26.4 |
| light | EPSG:3857 | 13 | 13 | 4331 | 2620 | 39 | 3.8 | 13.4 |
| light | EPSG:3857 | 13 | 13 | 4303 | 2613 | 35 | 4.2 | 24.5 |
| light | EPSG:3857 | 13 | 13 | 4319 | 2642 | 42 | 3.4 | 25.7 |
| light | EPSG:3857 | 13 | 13 | 4305 | 2613 | 28 | 3.8 | 12.9 |
| light | EPSG:3857 | 13 | 13 | 4336 | 2620 | 38 | 3.9 | 14.1 |
| light | EPSG:3857 | 14 | 14 | 8676 | 5241 | 34 | 3.7 | 10.9 |
| light | EPSG:3857 | 14 | 14 | 8572 | 5191 | 28 | 3.3 | 13.5 |
| light | EPSG:3857 | 14 | 14 | 8674 | 5291 | 25 | 3.7 | 5.7 |
| light | EPSG:3857 | 14 | 14 | 8634 | 5238 | 37 | 3.7 | 19.7 |
| light | EPSG:3857 | 14 | 14 | 8605 | 5198 | 27 | 3.5 | 11.0 |
| light | EPSG:3857 | 16 | 16 | 34510 | 21123 | 25 | 3.2 | 9.7 |
| light | EPSG:3857 | 16 | 16 | 34537 | 20837 | 30 | 3.2 | 3.5 |
| light | EPSG:3857 | 16 | 16 | 34498 | 21060 | 28 | 3.3 | 13.9 |
| light | EPSG:3857 | 16 | 16 | 34509 | 21090 | 25 | 3.1 | 9.0 |
| light | EPSG:3857 | 16 | 16 | 34423 | 20838 | 22 | 3.2 | 3.0 |
| light | EPSG:3857 | 18 | 18 | 138041 | 84364 | 25 | 3.1 | 1.5 |
| light | EPSG:3857 | 18 | 18 | 137453 | 83057 | 24 | 3.2 | 1.1 |
| light | EPSG:3857 | 18 | 18 | 138517 | 84120 | 24 | 3.2 | 3.0 |
| light | EPSG:3857 | 18 | 18 | 137119 | 83066 | 33 | 3.3 | 4.4 |
| light | EPSG:3857 | 18 | 18 | 137650 | 83970 | 26 | 2.9 | 8.6 |
| light_max | EPSG:3857 | 8 | 8 | 135 | 82 | 61 | 3.5 | 30.1 |
| light_max | EPSG:3857 | 8 | 8 | 134 | 82 | 44 | 3.2 | 20.1 |
| light_max | EPSG:3857 | 8 | 8 | 135 | 81 | 46 | 3.1 | 19.7 |
| light_max | EPSG:3857 | 8 | 8 | 134 | 81 | 61 | 3.2 | 34.0 |
| light_max | EPSG:3857 | 8 | 8 | 136 | 81 | 16 | 3.0 | 6.2 |
| light_max | EPSG:3857 | 10 | 10 | 540 | 326 | 85 | 3.6 | 25.6 |
| light_max | EPSG:3857 | 10 | 10 | 538 | 329 | 74 | 3.4 | 27.1 |
| light_max | EPSG:3857 | 10 | 10 | 537 | 324 | 57 | 3.7 | 25.2 |
| light_max | EPSG:3857 | 10 | 10 | 543 | 329 | 27 | 3.6 | 5.7 |
| light_max | EPSG:3857 | 10 | 10 | 541 | 328 | 75 | 3.4 | 33.2 |
| light_max | EPSG:3857 | 12 | 12 | 2173 | 1312 | 24 | 3.4 | 2.2 |
| light_max | EPSG:3857 | 12 | 12 | 2161 | 1318 | 45 | 3.5 | 32.3 |
| light_max | EPSG:3857 | 12 | 12 | 2156 | 1319 | 41 | 3.2 | 30.1 |
| light_max | EPSG:3857 | 12 | 12 | 2146 | 1307 | 28 | 3.3 | 18.3 |
| light_max | EPSG:3857 | 12 | 12 | 2169 | 1313 | 34 | 3.2 | 26.4 |
| light_max | EPSG:3857 | 13 | 13 | 4331 | 2620 | 34 | 3.2 | 13.4 |
| light_max | EPSG:3857 | 13 | 13 | 4303 | 2613 | 31 | 3.0 | 24.5 |
| light_max | EPSG:3857 | 13 | 13 | 4319 | 2642 | 37 | 3.3 | 25.7 |
| light_max | EPSG:3857 | 13 | 13 | 4305 | 2613 | 24 | 3.5 | 12.9 |
| light_max | EPSG:3857 | 13 | 13 | 4336 | 2620 | 34 | 3.4 | 14.1 |
| light_max | EPSG:3857 | 14 | 14 | 8676 | 5241 | 30 | 3.3 | 10.9 |
| light_max | EPSG:3857 | 14 | 14 | 8572 | 5191 | 26 | 3.0 | 13.5 |
| light_max | EPSG:3857 | 14 | 14 | 8674 | 5291 | 22 | 2.9 | 5.7 |
| light_max | EPSG:3857 | 14 | 14 | 8634 | 5238 | 34 | 3.3 | 19.7 |
| light_max | EPSG:3857 | 14 | 14 | 8605 | 5198 | 27 | 3.2 | 11.0 |
| light_max | EPSG:3857 | 16 | 16 | 34510 | 21123 | 29 | 3.2 | 9.7 |
| light_max | EPSG:3857 | 16 | 16 | 34537 | 20837 | 29 | 3.2 | 3.5 |
| light_max | EPSG:3857 | 16 | 16 | 34498 | 21060 | 29 | 3.2 | 13.9 |
| light_max | EPSG:3857 | 16 | 16 | 34509 | 21090 | 26 | 3.0 | 9.0 |
| light_max | EPSG:3857 | 16 | 16 | 34423 | 20838 | 22 | 3.1 | 3.0 |
| light_max | EPSG:3857 | 18 | 18 | 138041 | 84364 | 26 | 3.0 | 1.5 |
| light_max | EPSG:3857 | 18 | 18 | 137453 | 83057 | 24 | 3.0 | 1.1 |
| light_max | EPSG:3857 | 18 | 18 | 138517 | 84120 | 23 | 3.0 | 3.4 |
| light_max | EPSG:3857 | 18 | 18 | 137119 | 83066 | 32 | 3.1 | 4.4 |
| light_max | EPSG:3857 | 18 | 18 | 137650 | 83970 | 25 | 3.8 | 8.6 |
| light_min | EPSG:3857 | 8 | 8 | 135 | 82 | 61 | 4.0 | 28.9 |
| light_min | EPSG:3857 | 8 | 8 | 134 | 82 | 41 | 3.5 | 19.4 |
| light_min | EPSG:3857 | 8 | 8 | 135 | 81 | 44 | 3.3 | 17.6 |
| light_min | EPSG:3857 | 8 | 8 | 134 | 81 | 56 | 3.8 | 33.6 |
| light_min | EPSG:3857 | 8 | 8 | 136 | 81 | 16 | 3.6 | 3.0 |
| light_min | EPSG:3857 | 10 | 10 | 540 | 326 | 67 | 4.5 | 24.3 |
| light_min | EPSG:3857 | 10 | 10 | 538 | 329 | 66 | 4.3 | 26.6 |
| light_min | EPSG:3857 | 10 | 10 | 537 | 324 | 53 | 3.6 | 25.3 |
| light_min | EPSG:3857 | 10 | 10 | 543 | 329 | 19 | 3.1 | 3.1 |
| light_min | EPSG:3857 | 10 | 10 | 541 | 328 | 64 | 3.3 | 32.4 |
| light_min | EPSG:3857 | 12 | 12 | 2173 | 1312 | 20 | 3.5 | 2.1 |
| light_min | EPSG:3857 | 12 | 12 | 2161 | 1318 | 39 | 3.5 | 30.6 |
| light_min | EPSG:3857 | 12 | 12 | 2156 | 1319 | 34 | 3.3 | 23.7 |
| light_min | EPSG:3857 | 12 | 12 | 2146 | 1307 | 23 | 3.1 | 12.4 |
| light_min | EPSG:3857 | 12 | 12 | 2169 | 1313 | 31 | 3.2 | 25.2 |
| light_min | EPSG:3857 | 13 | 13 | 4331 | 2620 | 30 | 3.1 | 8.8 |
| light_min | EPSG:3857 | 13 | 13 | 4303 | 2613 | 33 | 3.1 | 12.0 |
| light_min | EPSG:3857 | 13 | 13 | 4319 | 2642 | 42 | 3.4 | 23.1 |
| light_min | EPSG:3857 | 13 | 13 | 4305 | 2613 | 22 | 3.2 | 9.6 |
| light_min | EPSG:3857 | 13 | 13 | 4336 | 2620 | 30 | 4.0 | 11.0 |
| light_min | EPSG:3857 | 14 | 14 | 8676 | 5241 | 27 | 3.2 | 9.0 |
| light_min | EPSG:3857 | 14 | 14 | 8572 | 5191 | 22 | 3.2 | 9.8 |
| light_min | EPSG:3857 | 14 | 14 | 8674 | 5291 | 20 | 3.3 | 3.2 |
| light_min | EPSG:3857 | 14 | 14 | 8634 | 5238 | 30 | 3.2 | 15.5 |
| light_min | EPSG:3857 | 14 | 14 | 8605 | 5198 | 22 | 3.3 | 9.9 |
| light_min | EPSG:3857 | 16 | 16 | 34510 | 21123 | 23 | 4.0 | 8.2 |
| light_min | EPSG:3857 | 16 | 16 | 34537 | 20837 | 26 | 3.1 | 2.9 |
| light_min | EPSG:3857 | 16 | 16 | 34498 | 21060 | 22 | 3.7 | 9.6 |
| light_min | EPSG:3857 | 16 | 16 | 34509 | 21090 | 22 | 3.3 | 7.5 |
| light_min | EPSG:3857 | 16 | 16 | 34423 | 20838 | 20 | 3.3 | 2.9 |
| light_min | EPSG:3857 | 18 | 18 | 138041 | 84364 | 18 | 3.4 | 1.5 |
| light_min | EPSG:3857 | 18 | 18 | 137453 | 83057 | 17 | 3.0 | 0.4 |
| light_min | EPSG:3857 | 18 | 18 | 138517 | 84120 | 19 | 3.3 | 2.7 |
| light_min | EPSG:3857 | 18 | 18 | 137119 | 83066 | 18 | 3.2 | 2.6 |
| light_min | EPSG:3857 | 18 | 18 | 137650 | 83970 | 22 | 3.6 | 5.3 |

</details>

## 2. Per layer, theme `default`, in-process

One tile per zoom and CRS, rendered with a single Mapnik layer active at a time; layers Mapnik does not query at that scale are left out. `render` is the wall time of that render (query + draw); `db` is planning + execution of the same query under EXPLAIN ANALYZE; `rows` is what the query returns; `scans` are the plan's scan nodes. Layers sorted by render time.

### EPSG:3857 z8 (8) 135/82: render 50 ms, encode 10.4 ms, 84 KB, 10 layers, db sum 47 ms

| layer | render ms | db ms | rows | scans |
|---|---|---|---|---|
| landcover_osm_polygon_z9 | 15 | 8 | 6732 | Bitmap Heap Scan osm_polygon_z9; Bitmap Index Scan osm_polygon_z9_geom_idx |
| landuse_osm_polygon_z9 | 6 | 4 | 1407 | Bitmap Heap Scan osm_polygon_z9; Bitmap Index Scan osm_polygon_z9_geom_idx |
| roads_fill_osm_line_z9 | 5 | 3 | 1694 | Seq Scan osm_line_z9 |
| ocean_osm_polygon_z9 | 4 | 13 | 6 | Bitmap Heap Scan osm_polygon_z9; Bitmap Index Scan osm_polygon_z9_geom_idx |
| protected_osm_polygon_z9 | 4 | 2 | 171 | Bitmap Heap Scan osm_polygon_z9; Bitmap Index Scan osm_polygon_z9_geom_idx |
| places_osm_label | 4 | 7 | 2 | Index Scan osm_label_idx |
| water_osm_polygon_z9 | 4 | 3 | 176 | Bitmap Heap Scan osm_polygon_z9; Bitmap Index Scan osm_polygon_z9_geom_idx |
| rail_osm_line_z9 | 3 | 2 | 1023 | Seq Scan osm_line_z9 |
| waterways_osm_line_z9 | 3 | 2 | 149 | Bitmap Heap Scan osm_line_z9; Bitmap Index Scan osm_line_z9_geom_idx |
| boundaries_osm_line_z9 | 2 | 2 | 66 | Seq Scan osm_line_z9 |

### EPSG:3857 z10 (10) 540/326: render 67 ms, encode 10.2 ms, 71 KB, 14 layers, db sum 62 ms

| layer | render ms | db ms | rows | scans |
|---|---|---|---|---|
| labels_area_osm_label | 10 | 13 | 0 | Bitmap Heap Scan osm_label; Bitmap Index Scan osm_label_geom_idx |
| landcover_osm_polygon_z12 | 10 | 6 | 3634 | Bitmap Heap Scan osm_polygon_z12; Bitmap Index Scan osm_polygon_z12_geom_idx |
| roads_fill_osm_line_z12 | 8 | 5 | 3226 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| roads_casing_osm_line_z12 | 8 | 5 | 3226 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| landuse_osm_polygon_z12 | 4 | 4 | 405 | Bitmap Heap Scan osm_polygon_z12; Bitmap Index Scan osm_polygon_z12_geom_idx |
| ocean_osm_polygon_z12 | 4 | 5 | 1 | Bitmap Heap Scan osm_polygon_z12; Bitmap Index Scan osm_polygon_z12_geom_idx |
| protected_osm_polygon_z12 | 4 | 3 | 18 | Bitmap Heap Scan osm_polygon_z12; Bitmap Index Scan osm_polygon_z12_geom_idx |
| waterways_osm_line_z12 | 4 | 4 | 20 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| rail_osm_line_z12 | 4 | 3 | 161 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| boundaries_osm_line_z12 | 3 | 4 | 53 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| water_osm_polygon_z12 | 3 | 3 | 50 | Bitmap Heap Scan osm_polygon_z12; Bitmap Index Scan osm_polygon_z12_geom_idx |
| shields_osm_line_z12 | 3 | 3 | 0 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| aeroways_osm_line_z12 | 3 | 3 | 3 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| places_osm_label | 2 | 1 | 7 | Bitmap Heap Scan osm_label; Bitmap Index Scan osm_label_places_idx |

### EPSG:3857 z12 (12) 2173/1312: render 10 ms, encode 2.7 ms, 5 KB, 19 layers, db sum 8 ms

| layer | render ms | db ms | rows | scans |
|---|---|---|---|---|
| labels_area_osm_label | 2 | 1 | 0 | Index Scan osm_label_geom_idx |
| ocean_osm_polygon_z12 | 1 | 1 | 2 | Index Scan osm_polygon_z12_geom_idx |
| landcover_osm_polygon_z12 | 1 | 0 | 241 | Index Scan osm_polygon_z12_geom_idx |
| roads_casing_osm_line_z12 | 1 | 0 | 108 | Index Scan osm_line_z12_geom_idx |
| roads_fill_osm_line_z12 | 1 | 0 | 108 | Index Scan osm_line_z12_geom_idx |
| places_osm_label | 1 | 0 | 1 | Index Scan osm_label_places_idx |
| protected_osm_polygon_z12 | 1 | 0 | 1 | Index Scan osm_polygon_z12_geom_idx |
| waterways_osm_line_z12 | 1 | 0 | 67 | Index Scan osm_line_z12_geom_idx |
| tunnels_casing_osm_line_z12 | 1 | 0 | 0 | Index Scan osm_line_z12_geom_idx |
| water_osm_polygon_z12 | 1 | 0 | 8 | Index Scan osm_polygon_z12_geom_idx |
| landuse_osm_polygon_z12 | 1 | 0 | 16 | Index Scan osm_polygon_z12_geom_idx |
| labels_line_osm_line_z12 | 1 | 0 | 0 | Index Scan osm_line_z12_geom_idx |
| shields_osm_line_z12 | 1 | 0 | 0 | Index Scan osm_line_z12_geom_idx |
| bridges_casing_osm_line_z12 | 1 | 0 | 0 | Index Scan osm_line_z12_geom_idx |
| tunnels_fill_osm_line_z12 | 1 | 0 | 0 | Index Scan osm_line_z12_geom_idx |
| bridges_fill_osm_line_z12 | 0 | 0 | 0 | Index Scan osm_line_z12_geom_idx |
| boundaries_osm_line_z12 | 0 | 0 | 2 | Index Scan osm_line_z12_geom_idx |
| rail_osm_line_z12 | 0 | 0 | 0 | Index Scan osm_line_z12_geom_idx |
| aeroways_osm_line_z12 | 0 | 0 | 0 | Index Scan osm_line_z12_geom_idx |

### EPSG:3857 z14 (14) 8676/5241: render 19 ms, encode 5.1 ms, 27 KB, 21 layers, db sum 16 ms

| layer | render ms | db ms | rows | scans |
|---|---|---|---|---|
| ocean_osm_polygon | 4 | 3 | 1 | Index Scan osm_polygon_ocean_idx |
| landcover_osm_polygon | 2 | 1 | 108 | Index Scan osm_polygon_geom_idx |
| landuse_osm_polygon | 2 | 1 | 6 | Index Scan osm_polygon_landuse_idx |
| labels_area_osm_label | 1 | 1 | 0 | Index Scan osm_label_geom_idx |
| roads_fill_osm_line | 1 | 1 | 64 | Index Scan osm_line_geom_idx |
| protected_osm_polygon | 1 | 1 | 1 | Index Scan osm_polygon_protected_idx |
| water_osm_polygon | 1 | 1 | 16 | Index Scan osm_polygon_water_idx |
| places_osm_label | 1 | 0 | 1 | Index Scan osm_label_places_idx |
| roads_casing_osm_line | 1 | 1 | 31 | Index Scan osm_line_roads_casing_idx |
| labels_line_osm_line | 1 | 1 | 2 | Index Scan osm_line_labels_idx |
| waterways_osm_line | 1 | 2 | 24 | Index Scan osm_line_waterways_idx |
| shields_osm_line | 1 | 0 | 1 | Index Scan osm_line_shields_idx |
| buildings_osm_building | 1 | 0 | 100 | Index Scan osm_building_geom_idx |
| rail_osm_line | 1 | 0 | 1 | Index Scan osm_line_rail_idx |
| boundaries_osm_line | 1 | 0 | 2 | Index Scan osm_line_boundaries_idx |
| bridges_fill_osm_line | 1 | 0 | 0 | Index Scan osm_line_bridges_casing_idx |
| bridges_casing_osm_line | 1 | 0 | 0 | Index Scan osm_line_bridges_casing_idx |
| tunnels_fill_osm_line | 1 | 0 | 1 | Index Scan osm_line_tunnels_casing_idx |
| tunnels_casing_osm_line | 1 | 0 | 1 | Index Scan osm_line_tunnels_casing_idx |
| roads_fill_osm_polygon | 1 | 0 | 0 | Index Scan osm_polygon_roads_fill_idx |
| aeroways_osm_line | 1 | 0 | 0 | Index Scan osm_line_aeroways_idx |

### EPSG:3857 z16 (16) 34510/21123: render 13 ms, encode 4.5 ms, 25 KB, 21 layers, db sum 12 ms

| layer | render ms | db ms | rows | scans |
|---|---|---|---|---|
| labels_line_osm_line | 2 | 1 | 5 | Index Scan osm_line_labels_idx |
| labels_area_osm_label | 1 | 1 | 0 | Index Scan osm_label_geom_idx |
| landuse_osm_polygon | 1 | 1 | 4 | Index Scan osm_polygon_landuse_idx |
| shields_osm_line | 1 | 0 | 2 | Index Scan osm_line_shields_idx |
| roads_fill_osm_line | 1 | 1 | 14 | Index Scan osm_line_geom_idx |
| buildings_osm_building | 1 | 1 | 87 | Index Scan osm_building_geom_idx |
| waterways_osm_line | 1 | 1 | 18 | Index Scan osm_line_waterways_idx |
| rail_osm_line | 1 | 1 | 0 | Index Scan osm_line_rail_idx |
| water_osm_polygon | 1 | 1 | 2 | Index Scan osm_polygon_water_idx |
| boundaries_osm_line | 1 | 0 | 1 | Index Scan osm_line_boundaries_idx |
| ocean_osm_polygon | 1 | 1 | 1 | Index Scan osm_polygon_ocean_idx |
| roads_casing_osm_line | 1 | 1 | 11 | Index Scan osm_line_roads_casing_idx |
| aeroways_osm_line | 1 | 0 | 0 | Index Scan osm_line_aeroways_idx |
| landcover_osm_polygon | 1 | 1 | 17 | Index Scan osm_polygon_geom_idx |
| tunnels_fill_osm_line | 1 | 0 | 0 | Index Scan osm_line_tunnels_casing_idx |
| bridges_fill_osm_line | 1 | 1 | 0 | Index Scan osm_line_bridges_casing_idx |
| tunnels_casing_osm_line | 1 | 0 | 0 | Index Scan osm_line_tunnels_casing_idx |
| roads_fill_osm_polygon | 1 | 0 | 0 | Index Scan osm_polygon_roads_fill_idx |
| bridges_casing_osm_line | 1 | 0 | 0 | Index Scan osm_line_bridges_casing_idx |
| protected_osm_polygon | 1 | 0 | 0 | Index Scan osm_polygon_protected_idx |
| places_osm_label | 1 | 0 | 0 | Index Scan osm_label_places_idx |

