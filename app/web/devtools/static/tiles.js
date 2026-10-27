// The Tiles tab: which tiles the shared map draws, and which URL they come
// through.
//
// The server compiles one XML per theme *per grid* and serves WMTS in both
// bindings -- so the tab reads the public `/metadata`, builds a
// CRS per grid from `/devtools/api/grids`, and offers four request modes
// that must all draw the identical map. A mode that differs is a bug in
// that protocol's addressing, which is what the switch is for.
//
// The tile layer drawn here is the base layer for both tabs, so it keeps
// running while the Search tab is in front; only the controls hide.

import * as api from './api.js';
import { lang, t } from './i18n.js';
import * as mapview from './mapview.js';
import { registerCollector, writeStateToUrl } from './urlstate.js';

const WEB_MERCATOR = 'GoogleMapsCompatible';

// `detail` as /metadata reports it -> the option value.
const DETAILS = ['min', 'nav', 'std', 'max', 'topographic', 'vegetation'];

const colorSelect = document.getElementById('colorTheme');
const detailSelect = document.getElementById('detailLevel');
const detailField = document.getElementById('detailField');
const modeRadios = document.querySelectorAll('input[name="mode"]');
const formatSelect = document.getElementById('format');
const gridSelect = document.getElementById('grid');
const gridHint = document.getElementById('gridHint');
const debugGridCheckbox = document.getElementById('debugGrid');
const urlTemplateBox = document.getElementById('urlTemplate');
const themeHint = document.getElementById('themeHint');
const tierBox = document.getElementById('tierHint');
const statusBox = document.getElementById('status');

let themes = [];            // [{name, color, detail, generation}]
let themesError = null;     // why /metadata failed, e.g. a missing key; null once it answered
let grids = {};             // identifier -> {crs, native, proj4, origin, resolutions, ...}
const formats = JSON.parse(document.querySelector('meta[name="formats"]').content);

// Set while the Search tab is in front. Result geometry and drawn shapes
// are EPSG:4326 and the map draws them through Leaflet's own projection,
// which only exists for Web Mercator -- so searching pins the map to it
// rather than reprojecting results into a test grid.
let webMercatorLock = false;

function currentMode() {
  return document.querySelector('input[name="mode"]:checked').value;
}

function currentDetail() {
  return detailSelect.value || 'std';
}

function currentTheme() {
  const match = themes.find(
    (theme) => theme.color === colorSelect.value && theme.detail === currentDetail());
  return match ?? null;
}

function currentFormat() {
  return formatSelect.value in formats ? formatSelect.value : 'png';
}

// XYZ is Web Mercator by definition, so the grid picker applies to WMTS
// and WMS only -- and not while searching (see webMercatorLock).
function currentGridId() {
  if (webMercatorLock || currentMode() === 'xyz') {
    return WEB_MERCATOR;
  }
  return gridSelect.value in grids ? gridSelect.value : WEB_MERCATOR;
}

// All four address the same tile. In every configured grid level N *is*
// the quadtree level N, so XYZ z/x/y and WMTS TILEMATRIX/TILECOL/TILEROW
// are the same three numbers in a different spelling. WMS has no tile
// address: each tile is a GetMap of its own bbox in the grid's CRS, which
// the server renders with that grid's XML and never caches.
function urlTemplateFor(mode, theme, gridId, format, version) {
  const bust = `v=${version}`;
  if (mode === 'wms') {
    return `/wms?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=${theme}&STYLES=`
      + `&CRS=${grids[gridId]?.crs ?? 'EPSG:3857'}&BBOX={bbox}&WIDTH=256&HEIGHT=256`
      + `&FORMAT=${encodeURIComponent(formats[format])}&${bust}${api.keyParam('&')}`;
  }
  if (mode === 'wmts-kvp') {
    return `/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=${theme}`
      + `&TILEMATRIXSET=${gridId}&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}`
      + `&FORMAT=${encodeURIComponent(formats[format])}&${bust}${api.keyParam('&')}`;
  }
  if (mode === 'wmts-rest') {
    return `/wmts/${theme}/${gridId}/{z}/{x}/{y}.${format}?${bust}${api.keyParam('&')}`;
  }
  return `/xyz/${theme}/{z}/{x}/{y}.${format}?${bust}${api.keyParam('&')}`;
}

function crsFor(gridId) {
  const grid = grids[gridId];
  if (!grid || grid.native || !grid.proj4) {
    return L.CRS.EPSG3857;
  }
  return new L.Proj.CRS(grid.crs, grid.proj4, {
    origin: grid.origin,
    resolutions: grid.resolutions,
  });
}

function maxZoomFor(gridId) {
  const grid = grids[gridId];
  return grid ? grid.resolutions.length - 1 : 18;
}

// Where the grid ends, so the layer never asks for a tile past the edge.
// Null for Web Mercator, which Leaflet bounds by itself.
function matrixSizeFor(gridId) {
  const grid = grids[gridId];
  if (!grid || grid.native) {
    return null;
  }
  return (z) => (z < 0 || z >= grid.matrix_widths.length
    ? null
    : { width: grid.matrix_widths[z], height: grid.matrix_heights[z] });
}

export function refreshTiles() {
  const theme = currentTheme();
  const gridId = currentGridId();
  mapview.ensureMap({ id: gridId, crs: crsFor(gridId), maxZoom: maxZoomFor(gridId) });
  if (!theme) {
    urlTemplateBox.textContent = '—';
    mapview.setLegend(null);
    setStatus(false, themesError ?? t('no_themes'));
    return;
  }
  // The theme's generation, not a counter: it changes exactly when the
  // server reloads the theme, which is exactly when cached tiles go stale.
  const template = urlTemplateFor(currentMode(), theme.name, gridId, currentFormat(),
                                  theme.generation);
  // The key is shown masked: this box is for reading and copying the
  // shape of a request, and a screenshot of it is how keys leak.
  urlTemplateBox.textContent = template.replace(/key=[^&]*/, 'key=…');
  mapview.setTileLayer(template, {
    maxZoom: maxZoomFor(gridId),
    matrixSize: matrixSizeFor(gridId),
  });
  // `v` as for the tiles: a recompile writes a new legend under the same URL.
  mapview.setLegend({
    url: `/legend/${theme.name}.png?lang=${lang}&v=${theme.generation}`,
    title: `${t('legend')} · ${theme.name}`,
  });
  syncDebugGrid();
  updateHints();
  writeStateToUrl();
}

function syncDebugGrid() {
  const gridId = currentGridId();
  mapview.setDebugGrid(debugGridCheckbox.checked, {
    maxZoom: maxZoomFor(gridId),
    matrixSize: matrixSizeFor(gridId),
  });
}

export function setWebMercatorLock(locked) {
  if (webMercatorLock === locked) {
    return;
  }
  webMercatorLock = locked;
  syncGridControl();
  refreshTiles();
}

function syncGridControl() {
  gridSelect.disabled = webMercatorLock || currentMode() === 'xyz';
}

function updateHints() {
  const theme = currentTheme();
  const gridId = currentGridId();
  if (theme) {
    themeHint.textContent = t('theme_hint', { name: theme.name, color: theme.color, detail: theme.detail });
  }
  const grid = grids[gridId];
  if (!grid) {
    gridHint.textContent = '';
  } else {
    const values = { crs: grid.crs, levels: grid.resolutions.length, depth: grid.precache_depth };
    gridHint.textContent = t(grid.precache_depth != null ? 'grid_precached' : 'grid_levels', values);
  }
  updateTier();
}

// Which cache tier the tiles on screen come from. "Why is this zoom slow"
// is usually the answer to this, so it is shown rather than inferred.
function updateTier() {
  const map = mapview.getMap();
  const grid = grids[currentGridId()];
  if (!map || !grid || grid.precache_depth == null) {
    tierBox.textContent = '';
    return;
  }
  const zoom = Math.round(map.getZoom());
  tierBox.textContent = t(zoom <= grid.precache_depth ? 'tier_precache' : 'tier_on_demand', { zoom });
}

function themesMessage(error) {
  return error.status === 401 || error.status === 403
    ? t('themes_error_key', { message: error.message })
    : t('themes_error', { message: error.message });
}

function setStatus(ok, text) {
  statusBox.textContent = text;
  statusBox.className = ok ? 'ok' : 'err';
}

function populateThemeControls(selected) {
  const colors = [...new Set(themes.map((theme) => theme.color))].sort();
  colorSelect.innerHTML = '';
  for (const color of colors) {
    const option = document.createElement('option');
    option.value = color;
    option.textContent = color;
    colorSelect.appendChild(option);
  }
  const wanted = themes.find((theme) => theme.name === selected);
  if (wanted) {
    colorSelect.value = wanted.color;
    detailSelect.value = wanted.detail;
  } else if (colors.includes('default')) {
    colorSelect.value = 'default';
  }
  syncDetailAvailability();
}

// Greys out the details the chosen colour has no theme for, and moves the
// selection off one that just became unavailable -- otherwise currentTheme()
// resolves to nothing and the map goes blank without saying why.
function syncDetailAvailability() {
  const available = new Set(themes
    .filter((theme) => theme.color === colorSelect.value)
    .map((theme) => theme.detail));
  for (const option of detailSelect.options) {
    option.disabled = !available.has(option.value);
  }
  if (!available.has(currentDetail())) {
    detailSelect.value = available.has('std') ? 'std' : DETAILS.find((l) => available.has(l));
  }
  detailField.classList.toggle('hidden', available.size < 2);
}

function populateGrids(selected) {
  gridSelect.innerHTML = '';
  for (const [id, grid] of Object.entries(grids)) {
    const option = document.createElement('option');
    option.value = id;
    option.textContent = `${id} (${grid.crs})`;
    // A grid without a proj4 definition cannot be drawn in the browser;
    // it is still served, so it is listed, but not offered.
    option.disabled = !grid.native && !grid.proj4;
    gridSelect.appendChild(option);
  }
  gridSelect.value = selected in grids ? selected : WEB_MERCATOR;
}

// The themes from /metadata, with each one's generation from /status --
// the tile URLs' `?v=`. /status needs a key; without one every generation
// is 0 and the tiles are still drawn.
async function fetchThemes() {
  const metadata = await api.request('/metadata');
  let generations = {};
  try {
    const status = await api.request('/status');
    generations = Object.fromEntries(status.themes.map((theme) => [theme.id, theme.generation]));
  } catch {
    // no key yet: generation 0
  }
  return metadata.themes.map((theme) => ({
    name: theme.id, color: theme.palette, detail: theme.detail,
    generation: generations[theme.id] ?? 0,
  }));
}

// Re-reads the themes. Called at start and when the viewer asks, so a theme
// recompiled and reloaded while the page is open is picked up -- its
// generation changes, and so does every tile URL.
export async function reloadThemes() {
  const selected = currentTheme()?.name;
  try {
    themes = await fetchThemes();
    themesError = null;
    populateThemeControls(selected);
    refreshTiles();
    setStatus(true, t('themes_count', { count: themes.length }));
  } catch (error) {
    themesError = themesMessage(error);
    setStatus(false, themesError);
  }
}

export async function init(state) {
  registerCollector(() => ({
    theme: currentTheme()?.name,
    mode: currentMode(),
    format: currentFormat(),
    grid: currentMode() === 'xyz' ? '' : gridSelect.value,
    debug: debugGridCheckbox.checked ? '1' : '',
    legend: mapview.isLegendOpen() ? '1' : '',
  }));
  // Before listening: the themes are not loaded yet, and a URL written now
  // would lose the one the page was opened with.
  mapview.setLegendOpen(state.legend === '1');
  mapview.on('legend', writeStateToUrl);

  // The mode, format and debug grid are rendered as the URL sets them.
  for (const radio of modeRadios) {
    radio.addEventListener('change', () => {
      syncGridControl();
      refreshTiles();
    });
  }
  colorSelect.addEventListener('change', () => {
    syncDetailAvailability();
    refreshTiles();
  });
  detailSelect.addEventListener('change', refreshTiles);
  formatSelect.addEventListener('change', refreshTiles);
  gridSelect.addEventListener('change', refreshTiles);
  debugGridCheckbox.addEventListener('change', () => {
    syncDebugGrid();
    writeStateToUrl();
  });
  document.getElementById('reloadThemes').addEventListener('click', reloadThemes);
  mapview.on('move', updateTier);
  mapview.on('tileerror', () => setStatus(false, t('tile_failed')));

  // Apart: a failed /metadata must not also cost the grids -- without them every grid is Web
  // Mercator with Leaflet's default of z18.
  try {
    grids = await api.request('/devtools/api/grids');
  } catch (error) {
    setStatus(false, t('grids_error', { message: error.message }));
  }
  try {
    themes = await fetchThemes();
  } catch (error) {
    themesError = themesMessage(error);
  }
  populateGrids(state.grid);
  populateThemeControls(state.theme);
  syncGridControl();
  refreshTiles();
}
