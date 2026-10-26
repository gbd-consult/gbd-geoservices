# Render profile -- 2026-09-30 12:21 UTC

- server http://127.0.0.1:8000, styles `/data/styles/de_sh_20260930_110143/UTM32N`, mapnik 4.3.2, PostgreSQL 17.5 (Debian 17.5-1.pgdg110+1)
- postgres: effective_cache_size=4GB, jit=off, max_parallel_workers_per_gather=2, random_page_cost=4, shared_buffers=2GB, work_mem=64MB
- hardware: aarch64 x 8, 15.8 GB RAM, linux 7.0.12-linuxkit aarch64 (dev stack, Docker Desktop on macOS)
- tile box (lon/lat, given): 8.300 53.400 -- 11.300 55.000, seed 42, 5 tiles with buildings per zoom
- themes: dark, dark_max, dark_min, default, default_max, default_min, hico, hico_max, hico_min, light, light_max, light_min
- crs: EPSG:25832 (UTM32N)

## 1. HTTP: uncached render vs cache hit

Render ms are min / median / max over all themes and tiles at that zoom; hit ms and KB are medians. For a non-3857 CRS "zoom" is the 3857 zoom the tile was picked for; the level actually requested is the closest scale of that TileMatrixSet (in parentheses), and two picks that land in the same coarse tile are fetched once. The first render after a cache clear is consistently slow, so unreported warm-up tiles per CRS are fetched first.

### EPSG:25832

| zoom | level | tiles | render ms | hit ms | KB |
|---|---|---|---|---|---|
| 8 | 3 | 36 | 51 / 82 / 93 | 3.2 | 10 |
| 10 | 5 | 60 | 30 / 51 / 91 | 3.1 | 30 |
| 12 | 7 | 60 | 29 / 52 / 87 | 3.1 | 27 |
| 13 | 8 | 60 | 31 / 47 / 68 | 3.2 | 26 |
| 14 | 9 | 60 | 23 / 54 / 92 | 3.2 | 19 |
| 16 | 11 | 60 | 21 / 31 / 60 | 3.0 | 9 |
| 18 | 13 | 60 | 18 / 28 / 73 | 3.0 | 5 |

| theme | crs | tiles | render ms | z<=12 render ms | z>12 render ms |
|---|---|---|---|---|---|
| dark | EPSG:25832 | 33 | 26 / 52 / 90 | 32 / 56 / 90 | 26 / 43 / 73 |
| dark_max | EPSG:25832 | 33 | 25 / 49 / 92 | 35 / 58 / 92 | 25 / 37 / 92 |
| dark_min | EPSG:25832 | 33 | 18 / 42 / 87 | 29 / 50 / 87 | 18 / 32 / 60 |
| default | EPSG:25832 | 33 | 26 / 52 / 93 | 32 / 58 / 93 | 26 / 40 / 69 |
| default_max | EPSG:25832 | 33 | 25 / 47 / 88 | 34 / 58 / 88 | 25 / 38 / 65 |
| default_min | EPSG:25832 | 33 | 21 / 41 / 84 | 30 / 47 / 84 | 21 / 32 / 60 |
| hico | EPSG:25832 | 33 | 25 / 49 / 93 | 34 / 57 / 93 | 25 / 38 / 75 |
| hico_max | EPSG:25832 | 33 | 27 / 49 / 91 | 33 / 56 / 91 | 27 / 36 / 65 |
| hico_min | EPSG:25832 | 33 | 18 / 42 / 82 | 30 / 49 / 82 | 18 / 32 / 68 |
| light | EPSG:25832 | 33 | 26 / 48 / 88 | 31 / 54 / 88 | 26 / 37 / 66 |
| light_max | EPSG:25832 | 33 | 26 / 46 / 91 | 33 / 57 / 91 | 26 / 37 / 66 |
| light_min | EPSG:25832 | 33 | 18 / 43 / 84 | 30 / 55 / 84 | 18 / 32 / 64 |

Total render time for the 396 tiles: 18.7 s.

<details><summary>Every tile</summary>

| theme | crs | zoom | level | col | row | render ms | hit ms | KB |
|---|---|---|---|---|---|---|---|---|
| dark | EPSG:25832 | 8 | 3 | 2 | 2 | 84 | 3.3 | 9.9 |
| dark | EPSG:25832 | 8 | 3 | 2 | 1 | 90 | 2.9 | 15.3 |
| dark | EPSG:25832 | 8 | 3 | 3 | 1 | 56 | 2.9 | 5.4 |
| dark | EPSG:25832 | 10 | 5 | 11 | 7 | 58 | 3.2 | 31.1 |
| dark | EPSG:25832 | 10 | 5 | 10 | 8 | 52 | 3.1 | 32.9 |
| dark | EPSG:25832 | 10 | 5 | 9 | 6 | 32 | 2.9 | 24.5 |
| dark | EPSG:25832 | 10 | 5 | 12 | 8 | 48 | 2.9 | 21.9 |
| dark | EPSG:25832 | 10 | 5 | 11 | 8 | 66 | 3.7 | 38.8 |
| dark | EPSG:25832 | 12 | 7 | 50 | 31 | 51 | 3.1 | 23.2 |
| dark | EPSG:25832 | 12 | 7 | 45 | 34 | 57 | 3.4 | 31.9 |
| dark | EPSG:25832 | 12 | 7 | 42 | 35 | 52 | 3.2 | 28.2 |
| dark | EPSG:25832 | 12 | 7 | 38 | 29 | 38 | 2.9 | 12.6 |
| dark | EPSG:25832 | 12 | 7 | 48 | 32 | 73 | 4.1 | 31.5 |
| dark | EPSG:25832 | 13 | 8 | 94 | 61 | 54 | 3.9 | 23.6 |
| dark | EPSG:25832 | 13 | 8 | 81 | 59 | 54 | 3.7 | 30.4 |
| dark | EPSG:25832 | 13 | 8 | 88 | 72 | 68 | 3.1 | 39.8 |
| dark | EPSG:25832 | 13 | 8 | 82 | 59 | 37 | 2.9 | 25.1 |
| dark | EPSG:25832 | 13 | 8 | 96 | 61 | 48 | 2.8 | 28.3 |
| dark | EPSG:25832 | 14 | 9 | 194 | 124 | 64 | 3.3 | 20.7 |
| dark | EPSG:25832 | 14 | 9 | 146 | 101 | 53 | 3.0 | 26.1 |
| dark | EPSG:25832 | 14 | 9 | 193 | 146 | 27 | 2.8 | 12.8 |
| dark | EPSG:25832 | 14 | 9 | 175 | 123 | 60 | 3.1 | 20.7 |
| dark | EPSG:25832 | 14 | 9 | 161 | 104 | 32 | 3.0 | 19.3 |
| dark | EPSG:25832 | 16 | 11 | 688 | 570 | 29 | 2.8 | 12.2 |
| dark | EPSG:25832 | 16 | 11 | 699 | 439 | 55 | 3.1 | 8.2 |
| dark | EPSG:25832 | 16 | 11 | 682 | 541 | 50 | 3.1 | 31.4 |
| dark | EPSG:25832 | 16 | 11 | 687 | 554 | 29 | 3.1 | 8.5 |
| dark | EPSG:25832 | 16 | 11 | 647 | 439 | 26 | 3.0 | 9.3 |
| dark | EPSG:25832 | 18 | 13 | 2752 | 2221 | 29 | 2.8 | 2.9 |
| dark | EPSG:25832 | 18 | 13 | 2482 | 1626 | 26 | 3.1 | 2.6 |
| dark | EPSG:25832 | 18 | 13 | 2970 | 2106 | 27 | 2.8 | 6.2 |
| dark | EPSG:25832 | 18 | 13 | 2331 | 1629 | 73 | 3.1 | 8.1 |
| dark | EPSG:25832 | 18 | 13 | 2571 | 2041 | 31 | 3.6 | 11.0 |
| dark_max | EPSG:25832 | 8 | 3 | 2 | 2 | 86 | 3.7 | 9.9 |
| dark_max | EPSG:25832 | 8 | 3 | 2 | 1 | 92 | 3.2 | 15.3 |
| dark_max | EPSG:25832 | 8 | 3 | 3 | 1 | 58 | 4.7 | 5.4 |
| dark_max | EPSG:25832 | 10 | 5 | 11 | 7 | 60 | 3.3 | 32.1 |
| dark_max | EPSG:25832 | 10 | 5 | 10 | 8 | 54 | 4.3 | 33.0 |
| dark_max | EPSG:25832 | 10 | 5 | 9 | 6 | 35 | 3.5 | 25.4 |
| dark_max | EPSG:25832 | 10 | 5 | 12 | 8 | 49 | 2.9 | 22.7 |
| dark_max | EPSG:25832 | 10 | 5 | 11 | 8 | 68 | 3.2 | 38.8 |
| dark_max | EPSG:25832 | 12 | 7 | 50 | 31 | 52 | 3.3 | 23.2 |
| dark_max | EPSG:25832 | 12 | 7 | 45 | 34 | 58 | 3.1 | 31.9 |
| dark_max | EPSG:25832 | 12 | 7 | 42 | 35 | 53 | 3.9 | 28.6 |
| dark_max | EPSG:25832 | 12 | 7 | 38 | 29 | 48 | 4.3 | 12.6 |
| dark_max | EPSG:25832 | 12 | 7 | 48 | 32 | 78 | 3.3 | 31.5 |
| dark_max | EPSG:25832 | 13 | 8 | 94 | 61 | 46 | 3.4 | 23.6 |
| dark_max | EPSG:25832 | 13 | 8 | 81 | 59 | 47 | 3.2 | 30.4 |
| dark_max | EPSG:25832 | 13 | 8 | 88 | 72 | 61 | 3.2 | 39.9 |
| dark_max | EPSG:25832 | 13 | 8 | 82 | 59 | 40 | 3.2 | 25.1 |
| dark_max | EPSG:25832 | 13 | 8 | 96 | 61 | 51 | 3.3 | 28.3 |
| dark_max | EPSG:25832 | 14 | 9 | 194 | 124 | 92 | 3.2 | 20.7 |
| dark_max | EPSG:25832 | 14 | 9 | 146 | 101 | 59 | 3.6 | 26.1 |
| dark_max | EPSG:25832 | 14 | 9 | 193 | 146 | 30 | 3.0 | 12.8 |
| dark_max | EPSG:25832 | 14 | 9 | 175 | 123 | 62 | 3.6 | 20.7 |
| dark_max | EPSG:25832 | 14 | 9 | 161 | 104 | 35 | 2.9 | 19.3 |
| dark_max | EPSG:25832 | 16 | 11 | 688 | 570 | 34 | 3.2 | 12.2 |
| dark_max | EPSG:25832 | 16 | 11 | 699 | 439 | 59 | 3.1 | 8.2 |
| dark_max | EPSG:25832 | 16 | 11 | 682 | 541 | 47 | 3.0 | 31.4 |
| dark_max | EPSG:25832 | 16 | 11 | 687 | 554 | 31 | 2.9 | 8.5 |
| dark_max | EPSG:25832 | 16 | 11 | 647 | 439 | 25 | 3.0 | 9.3 |
| dark_max | EPSG:25832 | 18 | 13 | 2752 | 2221 | 30 | 3.0 | 2.9 |
| dark_max | EPSG:25832 | 18 | 13 | 2482 | 1626 | 28 | 3.0 | 2.6 |
| dark_max | EPSG:25832 | 18 | 13 | 2970 | 2106 | 30 | 2.9 | 6.8 |
| dark_max | EPSG:25832 | 18 | 13 | 2331 | 1629 | 35 | 3.4 | 8.1 |
| dark_max | EPSG:25832 | 18 | 13 | 2571 | 2041 | 32 | 3.4 | 11.0 |
| dark_min | EPSG:25832 | 8 | 3 | 2 | 2 | 79 | 3.3 | 9.8 |
| dark_min | EPSG:25832 | 8 | 3 | 2 | 1 | 83 | 3.9 | 15.3 |
| dark_min | EPSG:25832 | 8 | 3 | 3 | 1 | 58 | 3.5 | 5.2 |
| dark_min | EPSG:25832 | 10 | 5 | 11 | 7 | 56 | 3.9 | 31.0 |
| dark_min | EPSG:25832 | 10 | 5 | 10 | 8 | 49 | 3.1 | 32.4 |
| dark_min | EPSG:25832 | 10 | 5 | 9 | 6 | 31 | 3.0 | 25.4 |
| dark_min | EPSG:25832 | 10 | 5 | 12 | 8 | 42 | 3.1 | 21.4 |
| dark_min | EPSG:25832 | 10 | 5 | 11 | 8 | 67 | 3.4 | 38.9 |
| dark_min | EPSG:25832 | 12 | 7 | 50 | 31 | 46 | 2.8 | 22.3 |
| dark_min | EPSG:25832 | 12 | 7 | 45 | 34 | 50 | 3.7 | 29.4 |
| dark_min | EPSG:25832 | 12 | 7 | 42 | 35 | 45 | 3.2 | 26.8 |
| dark_min | EPSG:25832 | 12 | 7 | 38 | 29 | 29 | 2.9 | 11.8 |
| dark_min | EPSG:25832 | 12 | 7 | 48 | 32 | 87 | 3.4 | 30.5 |
| dark_min | EPSG:25832 | 13 | 8 | 94 | 61 | 42 | 3.3 | 22.3 |
| dark_min | EPSG:25832 | 13 | 8 | 81 | 59 | 37 | 3.2 | 19.3 |
| dark_min | EPSG:25832 | 13 | 8 | 88 | 72 | 55 | 3.3 | 38.5 |
| dark_min | EPSG:25832 | 13 | 8 | 82 | 59 | 31 | 3.4 | 18.1 |
| dark_min | EPSG:25832 | 13 | 8 | 96 | 61 | 45 | 3.1 | 26.9 |
| dark_min | EPSG:25832 | 14 | 9 | 194 | 124 | 60 | 3.2 | 16.7 |
| dark_min | EPSG:25832 | 14 | 9 | 146 | 101 | 49 | 3.1 | 22.9 |
| dark_min | EPSG:25832 | 14 | 9 | 193 | 146 | 23 | 3.4 | 8.9 |
| dark_min | EPSG:25832 | 14 | 9 | 175 | 123 | 58 | 3.6 | 18.4 |
| dark_min | EPSG:25832 | 14 | 9 | 161 | 104 | 33 | 3.2 | 18.4 |
| dark_min | EPSG:25832 | 16 | 11 | 688 | 570 | 29 | 3.1 | 10.7 |
| dark_min | EPSG:25832 | 16 | 11 | 699 | 439 | 50 | 3.0 | 7.9 |
| dark_min | EPSG:25832 | 16 | 11 | 682 | 541 | 38 | 3.0 | 22.6 |
| dark_min | EPSG:25832 | 16 | 11 | 687 | 554 | 24 | 2.9 | 5.8 |
| dark_min | EPSG:25832 | 16 | 11 | 647 | 439 | 22 | 3.0 | 8.5 |
| dark_min | EPSG:25832 | 18 | 13 | 2752 | 2221 | 24 | 3.1 | 2.9 |
| dark_min | EPSG:25832 | 18 | 13 | 2482 | 1626 | 18 | 3.0 | 1.2 |
| dark_min | EPSG:25832 | 18 | 13 | 2970 | 2106 | 22 | 2.9 | 4.7 |
| dark_min | EPSG:25832 | 18 | 13 | 2331 | 1629 | 21 | 2.8 | 4.5 |
| dark_min | EPSG:25832 | 18 | 13 | 2571 | 2041 | 24 | 2.9 | 6.9 |
| default | EPSG:25832 | 8 | 3 | 2 | 2 | 85 | 3.3 | 10.9 |
| default | EPSG:25832 | 8 | 3 | 2 | 1 | 93 | 3.0 | 16.4 |
| default | EPSG:25832 | 8 | 3 | 3 | 1 | 57 | 3.1 | 6.0 |
| default | EPSG:25832 | 10 | 5 | 11 | 7 | 58 | 3.0 | 32.1 |
| default | EPSG:25832 | 10 | 5 | 10 | 8 | 52 | 3.9 | 33.2 |
| default | EPSG:25832 | 10 | 5 | 9 | 6 | 32 | 3.2 | 24.6 |
| default | EPSG:25832 | 10 | 5 | 12 | 8 | 48 | 3.4 | 22.0 |
| default | EPSG:25832 | 10 | 5 | 11 | 8 | 70 | 3.3 | 40.2 |
| default | EPSG:25832 | 12 | 7 | 50 | 31 | 52 | 3.3 | 23.3 |
| default | EPSG:25832 | 12 | 7 | 45 | 34 | 59 | 3.5 | 31.2 |
| default | EPSG:25832 | 12 | 7 | 42 | 35 | 80 | 9.0 | 27.5 |
| default | EPSG:25832 | 12 | 7 | 38 | 29 | 40 | 2.9 | 12.3 |
| default | EPSG:25832 | 12 | 7 | 48 | 32 | 71 | 3.4 | 30.6 |
| default | EPSG:25832 | 13 | 8 | 94 | 61 | 44 | 4.0 | 22.3 |
| default | EPSG:25832 | 13 | 8 | 81 | 59 | 56 | 3.4 | 29.7 |
| default | EPSG:25832 | 13 | 8 | 88 | 72 | 60 | 3.3 | 36.8 |
| default | EPSG:25832 | 13 | 8 | 82 | 59 | 47 | 3.3 | 24.0 |
| default | EPSG:25832 | 13 | 8 | 96 | 61 | 59 | 3.0 | 27.0 |
| default | EPSG:25832 | 14 | 9 | 194 | 124 | 69 | 5.6 | 20.0 |
| default | EPSG:25832 | 14 | 9 | 146 | 101 | 60 | 3.3 | 25.0 |
| default | EPSG:25832 | 14 | 9 | 193 | 146 | 29 | 4.0 | 12.1 |
| default | EPSG:25832 | 14 | 9 | 175 | 123 | 63 | 3.0 | 19.6 |
| default | EPSG:25832 | 14 | 9 | 161 | 104 | 36 | 3.5 | 18.8 |
| default | EPSG:25832 | 16 | 11 | 688 | 570 | 32 | 4.0 | 11.8 |
| default | EPSG:25832 | 16 | 11 | 699 | 439 | 59 | 3.3 | 8.4 |
| default | EPSG:25832 | 16 | 11 | 682 | 541 | 46 | 3.1 | 30.9 |
| default | EPSG:25832 | 16 | 11 | 687 | 554 | 30 | 4.2 | 8.0 |
| default | EPSG:25832 | 16 | 11 | 647 | 439 | 26 | 2.9 | 8.4 |
| default | EPSG:25832 | 18 | 13 | 2752 | 2221 | 29 | 3.1 | 2.9 |
| default | EPSG:25832 | 18 | 13 | 2482 | 1626 | 27 | 3.0 | 2.6 |
| default | EPSG:25832 | 18 | 13 | 2970 | 2106 | 29 | 2.9 | 6.0 |
| default | EPSG:25832 | 18 | 13 | 2331 | 1629 | 35 | 3.0 | 8.7 |
| default | EPSG:25832 | 18 | 13 | 2571 | 2041 | 31 | 3.2 | 11.2 |
| default_max | EPSG:25832 | 8 | 3 | 2 | 2 | 82 | 2.8 | 10.9 |
| default_max | EPSG:25832 | 8 | 3 | 2 | 1 | 88 | 3.3 | 16.4 |
| default_max | EPSG:25832 | 8 | 3 | 3 | 1 | 58 | 3.4 | 6.0 |
| default_max | EPSG:25832 | 10 | 5 | 11 | 7 | 58 | 3.4 | 32.9 |
| default_max | EPSG:25832 | 10 | 5 | 10 | 8 | 51 | 3.5 | 33.1 |
| default_max | EPSG:25832 | 10 | 5 | 9 | 6 | 34 | 2.9 | 25.4 |
| default_max | EPSG:25832 | 10 | 5 | 12 | 8 | 47 | 3.0 | 22.8 |
| default_max | EPSG:25832 | 10 | 5 | 11 | 8 | 69 | 3.3 | 40.3 |
| default_max | EPSG:25832 | 12 | 7 | 50 | 31 | 84 | 3.1 | 23.3 |
| default_max | EPSG:25832 | 12 | 7 | 45 | 34 | 59 | 3.4 | 31.2 |
| default_max | EPSG:25832 | 12 | 7 | 42 | 35 | 54 | 3.4 | 27.8 |
| default_max | EPSG:25832 | 12 | 7 | 38 | 29 | 39 | 3.6 | 12.3 |
| default_max | EPSG:25832 | 12 | 7 | 48 | 32 | 71 | 3.0 | 30.6 |
| default_max | EPSG:25832 | 13 | 8 | 94 | 61 | 44 | 3.0 | 22.3 |
| default_max | EPSG:25832 | 13 | 8 | 81 | 59 | 46 | 3.2 | 29.7 |
| default_max | EPSG:25832 | 13 | 8 | 88 | 72 | 61 | 3.1 | 36.8 |
| default_max | EPSG:25832 | 13 | 8 | 82 | 59 | 41 | 3.2 | 24.0 |
| default_max | EPSG:25832 | 13 | 8 | 96 | 61 | 54 | 3.1 | 27.0 |
| default_max | EPSG:25832 | 14 | 9 | 194 | 124 | 65 | 3.2 | 20.0 |
| default_max | EPSG:25832 | 14 | 9 | 146 | 101 | 56 | 3.0 | 25.0 |
| default_max | EPSG:25832 | 14 | 9 | 193 | 146 | 28 | 2.9 | 12.1 |
| default_max | EPSG:25832 | 14 | 9 | 175 | 123 | 62 | 3.5 | 19.6 |
| default_max | EPSG:25832 | 14 | 9 | 161 | 104 | 35 | 3.2 | 18.8 |
| default_max | EPSG:25832 | 16 | 11 | 688 | 570 | 32 | 2.9 | 11.8 |
| default_max | EPSG:25832 | 16 | 11 | 699 | 439 | 58 | 3.2 | 8.4 |
| default_max | EPSG:25832 | 16 | 11 | 682 | 541 | 47 | 3.0 | 30.9 |
| default_max | EPSG:25832 | 16 | 11 | 687 | 554 | 30 | 2.8 | 8.0 |
| default_max | EPSG:25832 | 16 | 11 | 647 | 439 | 25 | 2.8 | 8.4 |
| default_max | EPSG:25832 | 18 | 13 | 2752 | 2221 | 29 | 3.0 | 2.9 |
| default_max | EPSG:25832 | 18 | 13 | 2482 | 1626 | 26 | 2.7 | 2.6 |
| default_max | EPSG:25832 | 18 | 13 | 2970 | 2106 | 28 | 2.8 | 6.4 |
| default_max | EPSG:25832 | 18 | 13 | 2331 | 1629 | 34 | 3.4 | 8.7 |
| default_max | EPSG:25832 | 18 | 13 | 2571 | 2041 | 31 | 2.9 | 11.2 |
| default_min | EPSG:25832 | 8 | 3 | 2 | 2 | 75 | 3.3 | 10.5 |
| default_min | EPSG:25832 | 8 | 3 | 2 | 1 | 84 | 3.7 | 15.9 |
| default_min | EPSG:25832 | 8 | 3 | 3 | 1 | 54 | 2.8 | 5.7 |
| default_min | EPSG:25832 | 10 | 5 | 11 | 7 | 52 | 2.9 | 31.8 |
| default_min | EPSG:25832 | 10 | 5 | 10 | 8 | 47 | 2.9 | 32.9 |
| default_min | EPSG:25832 | 10 | 5 | 9 | 6 | 30 | 2.9 | 24.9 |
| default_min | EPSG:25832 | 10 | 5 | 12 | 8 | 41 | 2.9 | 21.4 |
| default_min | EPSG:25832 | 10 | 5 | 11 | 8 | 76 | 3.1 | 40.1 |
| default_min | EPSG:25832 | 12 | 7 | 50 | 31 | 43 | 2.9 | 23.1 |
| default_min | EPSG:25832 | 12 | 7 | 45 | 34 | 46 | 3.0 | 30.6 |
| default_min | EPSG:25832 | 12 | 7 | 42 | 35 | 41 | 2.9 | 25.8 |
| default_min | EPSG:25832 | 12 | 7 | 38 | 29 | 36 | 3.7 | 11.5 |
| default_min | EPSG:25832 | 12 | 7 | 48 | 32 | 62 | 3.3 | 30.9 |
| default_min | EPSG:25832 | 13 | 8 | 94 | 61 | 38 | 3.1 | 22.4 |
| default_min | EPSG:25832 | 13 | 8 | 81 | 59 | 33 | 3.4 | 18.1 |
| default_min | EPSG:25832 | 13 | 8 | 88 | 72 | 55 | 3.2 | 36.0 |
| default_min | EPSG:25832 | 13 | 8 | 82 | 59 | 60 | 3.5 | 17.8 |
| default_min | EPSG:25832 | 13 | 8 | 96 | 61 | 47 | 3.0 | 25.5 |
| default_min | EPSG:25832 | 14 | 9 | 194 | 124 | 60 | 3.5 | 16.8 |
| default_min | EPSG:25832 | 14 | 9 | 146 | 101 | 51 | 3.2 | 21.7 |
| default_min | EPSG:25832 | 14 | 9 | 193 | 146 | 23 | 3.1 | 8.8 |
| default_min | EPSG:25832 | 14 | 9 | 175 | 123 | 59 | 3.1 | 18.8 |
| default_min | EPSG:25832 | 14 | 9 | 161 | 104 | 32 | 3.0 | 19.0 |
| default_min | EPSG:25832 | 16 | 11 | 688 | 570 | 26 | 3.0 | 11.1 |
| default_min | EPSG:25832 | 16 | 11 | 699 | 439 | 48 | 3.0 | 8.2 |
| default_min | EPSG:25832 | 16 | 11 | 682 | 541 | 39 | 3.1 | 23.6 |
| default_min | EPSG:25832 | 16 | 11 | 687 | 554 | 25 | 3.5 | 6.2 |
| default_min | EPSG:25832 | 16 | 11 | 647 | 439 | 27 | 3.3 | 7.9 |
| default_min | EPSG:25832 | 18 | 13 | 2752 | 2221 | 23 | 3.0 | 2.9 |
| default_min | EPSG:25832 | 18 | 13 | 2482 | 1626 | 21 | 3.3 | 1.5 |
| default_min | EPSG:25832 | 18 | 13 | 2970 | 2106 | 21 | 2.8 | 4.9 |
| default_min | EPSG:25832 | 18 | 13 | 2331 | 1629 | 21 | 2.9 | 4.9 |
| default_min | EPSG:25832 | 18 | 13 | 2571 | 2041 | 25 | 2.8 | 7.2 |
| hico | EPSG:25832 | 8 | 3 | 2 | 2 | 84 | 2.9 | 11.1 |
| hico | EPSG:25832 | 8 | 3 | 2 | 1 | 93 | 3.2 | 17.1 |
| hico | EPSG:25832 | 8 | 3 | 3 | 1 | 57 | 3.3 | 7.6 |
| hico | EPSG:25832 | 10 | 5 | 11 | 7 | 57 | 3.3 | 30.2 |
| hico | EPSG:25832 | 10 | 5 | 10 | 8 | 51 | 3.3 | 32.0 |
| hico | EPSG:25832 | 10 | 5 | 9 | 6 | 34 | 3.5 | 24.2 |
| hico | EPSG:25832 | 10 | 5 | 12 | 8 | 49 | 3.2 | 21.6 |
| hico | EPSG:25832 | 10 | 5 | 11 | 8 | 71 | 2.9 | 37.5 |
| hico | EPSG:25832 | 12 | 7 | 50 | 31 | 49 | 2.9 | 24.4 |
| hico | EPSG:25832 | 12 | 7 | 45 | 34 | 60 | 3.4 | 32.6 |
| hico | EPSG:25832 | 12 | 7 | 42 | 35 | 52 | 3.7 | 28.4 |
| hico | EPSG:25832 | 12 | 7 | 38 | 29 | 38 | 2.9 | 13.7 |
| hico | EPSG:25832 | 12 | 7 | 48 | 32 | 70 | 3.5 | 32.3 |
| hico | EPSG:25832 | 13 | 8 | 94 | 61 | 47 | 2.9 | 24.2 |
| hico | EPSG:25832 | 13 | 8 | 81 | 59 | 45 | 3.4 | 30.0 |
| hico | EPSG:25832 | 13 | 8 | 88 | 72 | 62 | 3.1 | 37.3 |
| hico | EPSG:25832 | 13 | 8 | 82 | 59 | 40 | 3.4 | 24.7 |
| hico | EPSG:25832 | 13 | 8 | 96 | 61 | 50 | 3.1 | 27.9 |
| hico | EPSG:25832 | 14 | 9 | 194 | 124 | 75 | 4.7 | 20.2 |
| hico | EPSG:25832 | 14 | 9 | 146 | 101 | 60 | 3.9 | 26.0 |
| hico | EPSG:25832 | 14 | 9 | 193 | 146 | 31 | 4.5 | 13.1 |
| hico | EPSG:25832 | 14 | 9 | 175 | 123 | 72 | 4.0 | 20.7 |
| hico | EPSG:25832 | 14 | 9 | 161 | 104 | 34 | 2.9 | 20.4 |
| hico | EPSG:25832 | 16 | 11 | 688 | 570 | 31 | 3.0 | 12.5 |
| hico | EPSG:25832 | 16 | 11 | 699 | 439 | 59 | 3.1 | 8.7 |
| hico | EPSG:25832 | 16 | 11 | 682 | 541 | 47 | 3.2 | 30.7 |
| hico | EPSG:25832 | 16 | 11 | 687 | 554 | 30 | 2.8 | 8.4 |
| hico | EPSG:25832 | 16 | 11 | 647 | 439 | 25 | 2.7 | 9.3 |
| hico | EPSG:25832 | 18 | 13 | 2752 | 2221 | 30 | 2.9 | 3.9 |
| hico | EPSG:25832 | 18 | 13 | 2482 | 1626 | 28 | 3.3 | 3.6 |
| hico | EPSG:25832 | 18 | 13 | 2970 | 2106 | 28 | 3.6 | 7.0 |
| hico | EPSG:25832 | 18 | 13 | 2331 | 1629 | 36 | 2.8 | 10.4 |
| hico | EPSG:25832 | 18 | 13 | 2571 | 2041 | 29 | 3.1 | 11.4 |
| hico_max | EPSG:25832 | 8 | 3 | 2 | 2 | 88 | 4.0 | 11.1 |
| hico_max | EPSG:25832 | 8 | 3 | 2 | 1 | 91 | 3.2 | 17.1 |
| hico_max | EPSG:25832 | 8 | 3 | 3 | 1 | 56 | 3.0 | 7.6 |
| hico_max | EPSG:25832 | 10 | 5 | 11 | 7 | 76 | 8.5 | 30.2 |
| hico_max | EPSG:25832 | 10 | 5 | 10 | 8 | 51 | 3.2 | 32.0 |
| hico_max | EPSG:25832 | 10 | 5 | 9 | 6 | 33 | 3.0 | 25.1 |
| hico_max | EPSG:25832 | 10 | 5 | 12 | 8 | 49 | 3.1 | 21.6 |
| hico_max | EPSG:25832 | 10 | 5 | 11 | 8 | 70 | 3.7 | 37.5 |
| hico_max | EPSG:25832 | 12 | 7 | 50 | 31 | 51 | 3.0 | 24.4 |
| hico_max | EPSG:25832 | 12 | 7 | 45 | 34 | 57 | 3.0 | 32.6 |
| hico_max | EPSG:25832 | 12 | 7 | 42 | 35 | 53 | 2.9 | 28.4 |
| hico_max | EPSG:25832 | 12 | 7 | 38 | 29 | 39 | 3.2 | 13.7 |
| hico_max | EPSG:25832 | 12 | 7 | 48 | 32 | 67 | 3.6 | 32.3 |
| hico_max | EPSG:25832 | 13 | 8 | 94 | 61 | 44 | 2.9 | 24.2 |
| hico_max | EPSG:25832 | 13 | 8 | 81 | 59 | 42 | 2.8 | 30.0 |
| hico_max | EPSG:25832 | 13 | 8 | 88 | 72 | 60 | 3.1 | 37.3 |
| hico_max | EPSG:25832 | 13 | 8 | 82 | 59 | 37 | 2.9 | 24.7 |
| hico_max | EPSG:25832 | 13 | 8 | 96 | 61 | 51 | 3.2 | 27.9 |
| hico_max | EPSG:25832 | 14 | 9 | 194 | 124 | 65 | 3.2 | 20.2 |
| hico_max | EPSG:25832 | 14 | 9 | 146 | 101 | 54 | 3.2 | 26.0 |
| hico_max | EPSG:25832 | 14 | 9 | 193 | 146 | 28 | 2.9 | 13.1 |
| hico_max | EPSG:25832 | 14 | 9 | 175 | 123 | 59 | 3.0 | 20.7 |
| hico_max | EPSG:25832 | 14 | 9 | 161 | 104 | 33 | 3.1 | 20.4 |
| hico_max | EPSG:25832 | 16 | 11 | 688 | 570 | 32 | 3.1 | 12.5 |
| hico_max | EPSG:25832 | 16 | 11 | 699 | 439 | 57 | 3.1 | 8.7 |
| hico_max | EPSG:25832 | 16 | 11 | 682 | 541 | 47 | 3.5 | 30.7 |
| hico_max | EPSG:25832 | 16 | 11 | 687 | 554 | 31 | 3.1 | 8.4 |
| hico_max | EPSG:25832 | 16 | 11 | 647 | 439 | 27 | 3.0 | 9.3 |
| hico_max | EPSG:25832 | 18 | 13 | 2752 | 2221 | 29 | 2.8 | 3.9 |
| hico_max | EPSG:25832 | 18 | 13 | 2482 | 1626 | 27 | 2.8 | 3.6 |
| hico_max | EPSG:25832 | 18 | 13 | 2970 | 2106 | 29 | 2.7 | 7.2 |
| hico_max | EPSG:25832 | 18 | 13 | 2331 | 1629 | 35 | 2.8 | 10.4 |
| hico_max | EPSG:25832 | 18 | 13 | 2571 | 2041 | 30 | 3.0 | 11.4 |
| hico_min | EPSG:25832 | 8 | 3 | 2 | 2 | 75 | 3.1 | 11.0 |
| hico_min | EPSG:25832 | 8 | 3 | 2 | 1 | 82 | 3.2 | 16.7 |
| hico_min | EPSG:25832 | 8 | 3 | 3 | 1 | 51 | 3.7 | 7.3 |
| hico_min | EPSG:25832 | 10 | 5 | 11 | 7 | 60 | 3.4 | 29.5 |
| hico_min | EPSG:25832 | 10 | 5 | 10 | 8 | 47 | 3.0 | 31.8 |
| hico_min | EPSG:25832 | 10 | 5 | 9 | 6 | 30 | 2.7 | 25.0 |
| hico_min | EPSG:25832 | 10 | 5 | 12 | 8 | 42 | 2.9 | 20.7 |
| hico_min | EPSG:25832 | 10 | 5 | 11 | 8 | 65 | 3.5 | 37.7 |
| hico_min | EPSG:25832 | 12 | 7 | 50 | 31 | 44 | 2.9 | 24.1 |
| hico_min | EPSG:25832 | 12 | 7 | 45 | 34 | 49 | 3.0 | 31.7 |
| hico_min | EPSG:25832 | 12 | 7 | 42 | 35 | 41 | 3.3 | 27.0 |
| hico_min | EPSG:25832 | 12 | 7 | 38 | 29 | 31 | 2.9 | 13.1 |
| hico_min | EPSG:25832 | 12 | 7 | 48 | 32 | 59 | 3.0 | 32.8 |
| hico_min | EPSG:25832 | 13 | 8 | 94 | 61 | 68 | 3.4 | 23.3 |
| hico_min | EPSG:25832 | 13 | 8 | 81 | 59 | 38 | 3.5 | 20.0 |
| hico_min | EPSG:25832 | 13 | 8 | 88 | 72 | 57 | 3.8 | 37.7 |
| hico_min | EPSG:25832 | 13 | 8 | 82 | 59 | 32 | 2.9 | 19.1 |
| hico_min | EPSG:25832 | 13 | 8 | 96 | 61 | 47 | 3.0 | 27.3 |
| hico_min | EPSG:25832 | 14 | 9 | 194 | 124 | 61 | 3.7 | 18.0 |
| hico_min | EPSG:25832 | 14 | 9 | 146 | 101 | 51 | 3.0 | 23.6 |
| hico_min | EPSG:25832 | 14 | 9 | 193 | 146 | 24 | 3.5 | 9.9 |
| hico_min | EPSG:25832 | 14 | 9 | 175 | 123 | 58 | 3.5 | 20.3 |
| hico_min | EPSG:25832 | 14 | 9 | 161 | 104 | 32 | 3.2 | 20.7 |
| hico_min | EPSG:25832 | 16 | 11 | 688 | 570 | 27 | 3.4 | 12.2 |
| hico_min | EPSG:25832 | 16 | 11 | 699 | 439 | 48 | 2.9 | 8.5 |
| hico_min | EPSG:25832 | 16 | 11 | 682 | 541 | 38 | 3.2 | 24.4 |
| hico_min | EPSG:25832 | 16 | 11 | 687 | 554 | 25 | 2.9 | 7.3 |
| hico_min | EPSG:25832 | 16 | 11 | 647 | 439 | 21 | 2.8 | 9.2 |
| hico_min | EPSG:25832 | 18 | 13 | 2752 | 2221 | 22 | 2.9 | 3.9 |
| hico_min | EPSG:25832 | 18 | 13 | 2482 | 1626 | 18 | 2.8 | 1.8 |
| hico_min | EPSG:25832 | 18 | 13 | 2970 | 2106 | 20 | 2.8 | 5.8 |
| hico_min | EPSG:25832 | 18 | 13 | 2331 | 1629 | 21 | 2.9 | 5.9 |
| hico_min | EPSG:25832 | 18 | 13 | 2571 | 2041 | 24 | 3.1 | 7.3 |
| light | EPSG:25832 | 8 | 3 | 2 | 2 | 81 | 3.1 | 9.0 |
| light | EPSG:25832 | 8 | 3 | 2 | 1 | 88 | 3.2 | 13.1 |
| light | EPSG:25832 | 8 | 3 | 3 | 1 | 56 | 3.1 | 4.9 |
| light | EPSG:25832 | 10 | 5 | 11 | 7 | 54 | 3.4 | 29.4 |
| light | EPSG:25832 | 10 | 5 | 10 | 8 | 49 | 2.9 | 30.9 |
| light | EPSG:25832 | 10 | 5 | 9 | 6 | 31 | 3.1 | 21.9 |
| light | EPSG:25832 | 10 | 5 | 12 | 8 | 44 | 2.9 | 21.1 |
| light | EPSG:25832 | 10 | 5 | 11 | 8 | 72 | 3.1 | 37.3 |
| light | EPSG:25832 | 12 | 7 | 50 | 31 | 50 | 3.0 | 21.2 |
| light | EPSG:25832 | 12 | 7 | 45 | 34 | 55 | 2.9 | 29.4 |
| light | EPSG:25832 | 12 | 7 | 42 | 35 | 48 | 2.8 | 27.1 |
| light | EPSG:25832 | 12 | 7 | 38 | 29 | 35 | 2.8 | 12.3 |
| light | EPSG:25832 | 12 | 7 | 48 | 32 | 70 | 3.1 | 28.6 |
| light | EPSG:25832 | 13 | 8 | 94 | 61 | 45 | 3.0 | 21.7 |
| light | EPSG:25832 | 13 | 8 | 81 | 59 | 42 | 2.9 | 28.6 |
| light | EPSG:25832 | 13 | 8 | 88 | 72 | 57 | 3.1 | 36.3 |
| light | EPSG:25832 | 13 | 8 | 82 | 59 | 38 | 3.4 | 23.8 |
| light | EPSG:25832 | 13 | 8 | 96 | 61 | 50 | 3.0 | 26.1 |
| light | EPSG:25832 | 14 | 9 | 194 | 124 | 66 | 3.4 | 19.2 |
| light | EPSG:25832 | 14 | 9 | 146 | 101 | 54 | 3.3 | 24.7 |
| light | EPSG:25832 | 14 | 9 | 193 | 146 | 29 | 3.0 | 11.7 |
| light | EPSG:25832 | 14 | 9 | 175 | 123 | 61 | 3.6 | 19.5 |
| light | EPSG:25832 | 14 | 9 | 161 | 104 | 33 | 2.9 | 17.4 |
| light | EPSG:25832 | 16 | 11 | 688 | 570 | 31 | 2.9 | 11.3 |
| light | EPSG:25832 | 16 | 11 | 699 | 439 | 60 | 4.3 | 7.0 |
| light | EPSG:25832 | 16 | 11 | 682 | 541 | 48 | 3.3 | 26.6 |
| light | EPSG:25832 | 16 | 11 | 687 | 554 | 33 | 3.3 | 7.7 |
| light | EPSG:25832 | 16 | 11 | 647 | 439 | 26 | 3.2 | 6.8 |
| light | EPSG:25832 | 18 | 13 | 2752 | 2221 | 32 | 3.0 | 2.3 |
| light | EPSG:25832 | 18 | 13 | 2482 | 1626 | 30 | 2.8 | 1.9 |
| light | EPSG:25832 | 18 | 13 | 2970 | 2106 | 31 | 3.1 | 5.3 |
| light | EPSG:25832 | 18 | 13 | 2331 | 1629 | 36 | 3.1 | 6.7 |
| light | EPSG:25832 | 18 | 13 | 2571 | 2041 | 30 | 2.7 | 8.7 |
| light_max | EPSG:25832 | 8 | 3 | 2 | 2 | 85 | 2.8 | 9.0 |
| light_max | EPSG:25832 | 8 | 3 | 2 | 1 | 91 | 3.2 | 13.1 |
| light_max | EPSG:25832 | 8 | 3 | 3 | 1 | 57 | 3.5 | 4.9 |
| light_max | EPSG:25832 | 10 | 5 | 11 | 7 | 58 | 3.0 | 30.3 |
| light_max | EPSG:25832 | 10 | 5 | 10 | 8 | 50 | 3.1 | 30.8 |
| light_max | EPSG:25832 | 10 | 5 | 9 | 6 | 33 | 2.7 | 22.8 |
| light_max | EPSG:25832 | 10 | 5 | 12 | 8 | 46 | 3.3 | 22.1 |
| light_max | EPSG:25832 | 10 | 5 | 11 | 8 | 91 | 3.6 | 37.3 |
| light_max | EPSG:25832 | 12 | 7 | 50 | 31 | 51 | 3.2 | 21.2 |
| light_max | EPSG:25832 | 12 | 7 | 45 | 34 | 60 | 4.1 | 29.4 |
| light_max | EPSG:25832 | 12 | 7 | 42 | 35 | 53 | 3.3 | 27.4 |
| light_max | EPSG:25832 | 12 | 7 | 38 | 29 | 38 | 2.9 | 12.3 |
| light_max | EPSG:25832 | 12 | 7 | 48 | 32 | 65 | 3.1 | 28.6 |
| light_max | EPSG:25832 | 13 | 8 | 94 | 61 | 43 | 2.8 | 21.7 |
| light_max | EPSG:25832 | 13 | 8 | 81 | 59 | 42 | 3.1 | 28.6 |
| light_max | EPSG:25832 | 13 | 8 | 88 | 72 | 59 | 3.3 | 36.3 |
| light_max | EPSG:25832 | 13 | 8 | 82 | 59 | 37 | 2.8 | 23.8 |
| light_max | EPSG:25832 | 13 | 8 | 96 | 61 | 50 | 2.9 | 26.1 |
| light_max | EPSG:25832 | 14 | 9 | 194 | 124 | 66 | 3.0 | 19.2 |
| light_max | EPSG:25832 | 14 | 9 | 146 | 101 | 55 | 3.2 | 24.7 |
| light_max | EPSG:25832 | 14 | 9 | 193 | 146 | 28 | 2.9 | 11.7 |
| light_max | EPSG:25832 | 14 | 9 | 175 | 123 | 60 | 3.2 | 19.5 |
| light_max | EPSG:25832 | 14 | 9 | 161 | 104 | 34 | 3.1 | 17.4 |
| light_max | EPSG:25832 | 16 | 11 | 688 | 570 | 31 | 3.0 | 11.3 |
| light_max | EPSG:25832 | 16 | 11 | 699 | 439 | 56 | 3.0 | 7.0 |
| light_max | EPSG:25832 | 16 | 11 | 682 | 541 | 46 | 2.9 | 26.6 |
| light_max | EPSG:25832 | 16 | 11 | 687 | 554 | 30 | 2.8 | 7.7 |
| light_max | EPSG:25832 | 16 | 11 | 647 | 439 | 26 | 3.0 | 6.8 |
| light_max | EPSG:25832 | 18 | 13 | 2752 | 2221 | 29 | 3.1 | 2.3 |
| light_max | EPSG:25832 | 18 | 13 | 2482 | 1626 | 26 | 2.7 | 1.9 |
| light_max | EPSG:25832 | 18 | 13 | 2970 | 2106 | 30 | 3.6 | 5.7 |
| light_max | EPSG:25832 | 18 | 13 | 2331 | 1629 | 37 | 3.3 | 6.7 |
| light_max | EPSG:25832 | 18 | 13 | 2571 | 2041 | 32 | 3.7 | 8.7 |
| light_min | EPSG:25832 | 8 | 3 | 2 | 2 | 78 | 3.3 | 8.7 |
| light_min | EPSG:25832 | 8 | 3 | 2 | 1 | 84 | 3.2 | 13.1 |
| light_min | EPSG:25832 | 8 | 3 | 3 | 1 | 55 | 3.9 | 4.8 |
| light_min | EPSG:25832 | 10 | 5 | 11 | 7 | 56 | 3.7 | 28.4 |
| light_min | EPSG:25832 | 10 | 5 | 10 | 8 | 48 | 3.1 | 30.2 |
| light_min | EPSG:25832 | 10 | 5 | 9 | 6 | 32 | 3.4 | 22.3 |
| light_min | EPSG:25832 | 10 | 5 | 12 | 8 | 47 | 2.8 | 20.0 |
| light_min | EPSG:25832 | 10 | 5 | 11 | 8 | 64 | 3.0 | 36.9 |
| light_min | EPSG:25832 | 12 | 7 | 50 | 31 | 45 | 3.1 | 20.0 |
| light_min | EPSG:25832 | 12 | 7 | 45 | 34 | 82 | 3.5 | 26.9 |
| light_min | EPSG:25832 | 12 | 7 | 42 | 35 | 43 | 2.9 | 24.5 |
| light_min | EPSG:25832 | 12 | 7 | 38 | 29 | 30 | 3.0 | 9.7 |
| light_min | EPSG:25832 | 12 | 7 | 48 | 32 | 59 | 3.6 | 28.0 |
| light_min | EPSG:25832 | 13 | 8 | 94 | 61 | 39 | 3.4 | 20.0 |
| light_min | EPSG:25832 | 13 | 8 | 81 | 59 | 35 | 3.5 | 17.6 |
| light_min | EPSG:25832 | 13 | 8 | 88 | 72 | 64 | 4.2 | 34.8 |
| light_min | EPSG:25832 | 13 | 8 | 82 | 59 | 34 | 3.2 | 17.4 |
| light_min | EPSG:25832 | 13 | 8 | 96 | 61 | 45 | 3.4 | 24.4 |
| light_min | EPSG:25832 | 14 | 9 | 194 | 124 | 64 | 4.0 | 14.3 |
| light_min | EPSG:25832 | 14 | 9 | 146 | 101 | 53 | 3.3 | 20.9 |
| light_min | EPSG:25832 | 14 | 9 | 193 | 146 | 24 | 3.0 | 7.1 |
| light_min | EPSG:25832 | 14 | 9 | 175 | 123 | 60 | 3.4 | 16.3 |
| light_min | EPSG:25832 | 14 | 9 | 161 | 104 | 31 | 3.3 | 16.2 |
| light_min | EPSG:25832 | 16 | 11 | 688 | 570 | 29 | 3.1 | 9.8 |
| light_min | EPSG:25832 | 16 | 11 | 699 | 439 | 49 | 3.2 | 6.3 |
| light_min | EPSG:25832 | 16 | 11 | 682 | 541 | 40 | 3.3 | 18.9 |
| light_min | EPSG:25832 | 16 | 11 | 687 | 554 | 24 | 3.0 | 4.5 |
| light_min | EPSG:25832 | 16 | 11 | 647 | 439 | 24 | 2.9 | 5.9 |
| light_min | EPSG:25832 | 18 | 13 | 2752 | 2221 | 22 | 3.4 | 2.3 |
| light_min | EPSG:25832 | 18 | 13 | 2482 | 1626 | 18 | 2.7 | 0.8 |
| light_min | EPSG:25832 | 18 | 13 | 2970 | 2106 | 19 | 3.0 | 4.1 |
| light_min | EPSG:25832 | 18 | 13 | 2331 | 1629 | 21 | 3.4 | 3.9 |
| light_min | EPSG:25832 | 18 | 13 | 2571 | 2041 | 24 | 3.0 | 4.9 |

</details>

## 2. Per layer, theme `default`, in-process

One tile per zoom and CRS, rendered with a single Mapnik layer active at a time; layers Mapnik does not query at that scale are left out. `render` is the wall time of that render (query + draw); `db` is planning + execution of the same query under EXPLAIN ANALYZE; `rows` is what the query returns; `scans` are the plan's scan nodes. Layers sorted by render time.

### EPSG:25832 z8 (3) 2/2: render 76 ms, encode 4.9 ms, 25 KB, 6 layers, db sum 36 ms

| layer | render ms | db ms | rows | scans |
|---|---|---|---|---|
| landcover_osm_polygon_z9 | 51 | 12 | 10400 | Seq Scan osm_polygon_z9 |
| water_osm_polygon_z9 | 7 | 4 | 231 | Seq Scan osm_polygon_z9 |
| protected_osm_polygon_z9 | 7 | 4 | 250 | Seq Scan osm_polygon_z9 |
| ocean_osm_polygon_z9 | 6 | 12 | 10 | Seq Scan osm_polygon_z9 |
| roads_fill_osm_line_z9 | 5 | 3 | 1545 | Seq Scan osm_line_z9 |
| boundaries_osm_line_z9 | 3 | 1 | 13 | Seq Scan osm_line_z9 |

### EPSG:25832 z10 (5) 11/7: render 47 ms, encode 11.5 ms, 80 KB, 10 layers, db sum 22 ms

| layer | render ms | db ms | rows | scans |
|---|---|---|---|---|
| landcover_osm_polygon_z9 | 19 | 4 | 3521 | Bitmap Heap Scan osm_polygon_z9; Bitmap Index Scan osm_polygon_z9_geom_idx |
| landuse_osm_polygon_z9 | 6 | 2 | 627 | Bitmap Heap Scan osm_polygon_z9; Bitmap Index Scan osm_polygon_z9_geom_idx |
| roads_fill_osm_line_z9 | 5 | 1 | 1109 | Bitmap Heap Scan osm_line_z9; Bitmap Index Scan osm_line_z9_geom_idx |
| places_osm_label | 5 | 5 | 1 | Bitmap Heap Scan osm_label; Bitmap Index Scan osm_label_places_idx |
| ocean_osm_polygon_z9 | 4 | 3 | 2 | Bitmap Heap Scan osm_polygon_z9; Bitmap Index Scan osm_polygon_z9_geom_idx |
| water_osm_polygon_z9 | 4 | 2 | 109 | Bitmap Heap Scan osm_polygon_z9; Bitmap Index Scan osm_polygon_z9_geom_idx |
| protected_osm_polygon_z9 | 3 | 2 | 36 | Bitmap Heap Scan osm_polygon_z9; Bitmap Index Scan osm_polygon_z9_geom_idx |
| rail_osm_line_z9 | 3 | 1 | 383 | Bitmap Heap Scan osm_line_z9; Bitmap Index Scan osm_line_z9_geom_idx |
| waterways_osm_line_z9 | 3 | 1 | 62 | Bitmap Heap Scan osm_line_z9; Bitmap Index Scan osm_line_z9_geom_idx |
| boundaries_osm_line_z9 | 3 | 1 | 25 | Bitmap Heap Scan osm_line_z9; Bitmap Index Scan osm_line_z9_geom_idx |

### EPSG:25832 z12 (7) 50/31: render 39 ms, encode 8.9 ms, 56 KB, 14 layers, db sum 23 ms

| layer | render ms | db ms | rows | scans |
|---|---|---|---|---|
| landcover_osm_polygon_z12 | 37 | 3 | 2321 | Bitmap Heap Scan osm_polygon_z12; Bitmap Index Scan osm_polygon_z12_geom_idx |
| ocean_osm_polygon_z12 | 8 | 2 | 2 | Bitmap Heap Scan osm_polygon_z12; Bitmap Index Scan osm_polygon_z12_geom_idx |
| labels_area_osm_label | 4 | 3 | 1 | Bitmap Heap Scan osm_label; Bitmap Index Scan osm_label_geom_idx |
| roads_casing_osm_line_z12 | 4 | 2 | 458 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| landuse_osm_polygon_z12 | 4 | 2 | 158 | Bitmap Heap Scan osm_polygon_z12; Bitmap Index Scan osm_polygon_z12_geom_idx |
| roads_fill_osm_line_z12 | 4 | 2 | 458 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| water_osm_polygon_z12 | 3 | 2 | 18 | Bitmap Heap Scan osm_polygon_z12; Bitmap Index Scan osm_polygon_z12_geom_idx |
| waterways_osm_line_z12 | 3 | 2 | 8 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| boundaries_osm_line_z12 | 3 | 1 | 49 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| rail_osm_line_z12 | 3 | 1 | 0 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| protected_osm_polygon_z12 | 3 | 2 | 2 | Bitmap Heap Scan osm_polygon_z12; Bitmap Index Scan osm_polygon_z12_geom_idx |
| aeroways_osm_line_z12 | 2 | 1 | 2 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| shields_osm_line_z12 | 2 | 1 | 0 | Bitmap Heap Scan osm_line_z12; Bitmap Index Scan osm_line_z12_geom_idx |
| places_osm_label | 2 | 1 | 2 | Index Scan osm_label_places_idx |

### EPSG:25832 z14 (9) 194/124: render 53 ms, encode 7.1 ms, 49 KB, 21 layers, db sum 20 ms

| layer | render ms | db ms | rows | scans |
|---|---|---|---|---|
| ocean_osm_polygon | 26 | 4 | 1 | Index Scan osm_polygon_ocean_idx |
| landcover_osm_polygon | 7 | 1 | 578 | Index Scan osm_polygon_geom_idx |
| roads_fill_osm_line | 4 | 1 | 237 | Index Scan osm_line_geom_idx |
| protected_osm_polygon | 4 | 1 | 1 | Index Scan osm_polygon_protected_idx |
| labels_area_osm_label | 4 | 1 | 0 | Index Scan osm_label_geom_idx |
| waterways_osm_line | 3 | 2 | 129 | Index Scan osm_line_waterways_idx |
| landuse_osm_polygon | 3 | 1 | 40 | Index Scan osm_polygon_landuse_idx |
| roads_casing_osm_line | 3 | 1 | 47 | Index Scan osm_line_roads_casing_idx |
| shields_osm_line | 3 | 1 | 2 | Index Scan osm_line_shields_idx |
| buildings_osm_building | 2 | 1 | 254 | Index Scan osm_building_geom_idx |
| boundaries_osm_line | 2 | 1 | 10 | Index Scan osm_line_boundaries_idx |
| tunnels_fill_osm_line | 2 | 1 | 0 | Index Scan osm_line_tunnels_casing_idx |
| bridges_casing_osm_line | 2 | 1 | 2 | Index Scan osm_line_bridges_casing_idx |
| rail_osm_line | 2 | 1 | 2 | Index Scan osm_line_rail_idx |
| water_osm_polygon | 2 | 1 | 31 | Index Scan osm_polygon_water_idx |
| labels_line_osm_line | 2 | 1 | 2 | Index Scan osm_line_labels_idx |
| places_osm_label | 2 | 1 | 1 | Index Scan osm_label_places_idx |
| aeroways_osm_line | 2 | 0 | 0 | Index Scan osm_line_aeroways_idx |
| bridges_fill_osm_line | 2 | 1 | 5 | Index Scan osm_line_bridges_casing_idx |
| tunnels_casing_osm_line | 2 | 0 | 0 | Index Scan osm_line_tunnels_casing_idx |
| roads_fill_osm_polygon | 2 | 0 | 0 | Index Scan osm_polygon_roads_fill_idx |

### EPSG:25832 z16 (11) 688/570: render 22 ms, encode 5.1 ms, 30 KB, 21 layers, db sum 13 ms

| layer | render ms | db ms | rows | scans |
|---|---|---|---|---|
| ocean_osm_polygon | 5 | 1 | 1 | Index Scan osm_polygon_ocean_idx |
| labels_line_osm_line | 3 | 1 | 7 | Index Scan osm_line_labels_idx |
| labels_area_osm_label | 3 | 1 | 0 | Index Scan osm_label_geom_idx |
| buildings_osm_building | 3 | 1 | 141 | Index Scan osm_building_geom_idx |
| places_osm_label | 3 | 1 | 0 | Index Scan osm_label_places_idx |
| rail_osm_line | 2 | 1 | 0 | Index Scan osm_line_rail_idx |
| landuse_osm_polygon | 2 | 1 | 8 | Index Scan osm_polygon_landuse_idx |
| bridges_casing_osm_line | 2 | 1 | 0 | Index Scan osm_line_bridges_casing_idx |
| roads_casing_osm_line | 2 | 1 | 16 | Index Scan osm_line_roads_casing_idx |
| landcover_osm_polygon | 2 | 1 | 42 | Index Scan osm_polygon_geom_idx |
| bridges_fill_osm_line | 2 | 1 | 0 | Index Scan osm_line_bridges_casing_idx |
| roads_fill_osm_line | 2 | 1 | 20 | Index Scan osm_line_geom_idx |
| shields_osm_line | 2 | 1 | 2 | Index Scan osm_line_shields_idx |
| boundaries_osm_line | 2 | 1 | 1 | Index Scan osm_line_boundaries_idx |
| waterways_osm_line | 2 | 1 | 43 | Index Scan osm_line_waterways_idx |
| protected_osm_polygon | 2 | 0 | 0 | Index Scan osm_polygon_protected_idx |
| water_osm_polygon | 2 | 1 | 2 | Index Scan osm_polygon_water_idx |
| tunnels_casing_osm_line | 2 | 0 | 0 | Index Scan osm_line_tunnels_casing_idx |
| roads_fill_osm_polygon | 2 | 0 | 0 | Index Scan osm_polygon_roads_fill_idx |
| tunnels_fill_osm_line | 2 | 1 | 0 | Index Scan osm_line_tunnels_casing_idx |
| aeroways_osm_line | 2 | 0 | 0 | Index Scan osm_line_aeroways_idx |

