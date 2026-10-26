// The one map, shared by both tabs.
//
// Before the merge each dev page had its own Leaflet instance with its own
// base layer (the tiles page drew this server's own tiles, the search demo
// drew openstreetmap.org at 30% opacity). There is one map now, and it
// always shows this server's own tiles in the selected theme -- which is
// both more coherent and means the search tab exercises the tile server
// too, rather than quietly depending on a third-party one.
//
// This module owns the map object, its CRS lifecycle, the base tile layer,
// the debug grid, the legend panel and the draw tools. It deliberately does *not* own the
// search results: those are the search tab's layers, added through
// getMap(), and re-added on 'rebuild' (see below).

import { t } from './i18n.js';
import { layerToWkt, wktToLayer } from './wkt.js';

// Leaflet.draw's own tooltips and number format, in the page's language.
// Only the handlers of the four tools below; the plugin's edit toolbar is
// not used.
const DRAW_HANDLERS = L.drawLocal.draw.handlers;
DRAW_HANDLERS.polyline.tooltip = {
  start: t('draw_line_start'), cont: t('draw_line_cont'), end: t('draw_line_end'),
};
DRAW_HANDLERS.polyline.error = t('draw_line_error');
DRAW_HANDLERS.polygon.tooltip = {
  start: t('draw_shape_start'), cont: t('draw_shape_cont'), end: t('draw_shape_end'),
};
DRAW_HANDLERS.rectangle.tooltip.start = t('draw_rectangle_start');
DRAW_HANDLERS.circle.tooltip.start = t('draw_circle_start');
DRAW_HANDLERS.simpleshape.tooltip.end = t('draw_release');
L.drawLocal.format = { numeric: { delimiters: { decimal: t('decimal'), thousands: t('thousands') } } };

// Default view when neither the URL nor the imported extent gives one:
// Germany, which every configured grid covers.
const DEFAULT_CENTER = [51.1657, 10.4515];
const DEFAULT_ZOOM = 6;

// How many tiles beyond the visible extent to load ahead, so panning lands
// on tiles that are already fetched instead of showing them load in. On a
// 1920x1080 display the map pane holds ~35 tiles; each extra ring adds
// 256px of cover for roughly another 30-40 renders. Two rings cover the
// typical 200-600px mouse drag without tripling the request volume.
const TILE_BUFFER = 2;

// Retention has to outlast the buffer or the ring gets pruned the moment
// you pan into it. Leaflet computes its no-prune range as the *loaded*
// range +/- keepBuffer, so buffer+1 keeps everything through a one-tile
// pan and drops only the trailing column on a two-tile pan -- those are
// behind you, and Cache-Control makes re-fetching them free anyway.
const TILE_KEEP_BUFFER = TILE_BUFFER + 1;

// Wait for the map to settle before loading the ring, so buffer tiles never
// compete with visible ones -- neither for the browser's ~6 sockets per
// origin nor for the renderer's Mapnik pool slots.
const PREFETCH_IDLE_MS = 250;

// Ceiling on the ring, since the tile count grows with viewport area: on a
// 3840px-wide monitor an unclamped two-ring buffer would be 154 extra
// tiles. This keeps the full ring on ordinary displays and degrades to one
// ring on very large ones.
const MAX_PREFETCH_TILES = 96;

let map = null;
let tileLayer = null;
let debugGridLayer = null;
let drawItems = null;
let mapCrsId = null; // which TileMatrixSet id `map`'s current CRS matches

// Center/zoom for the *next* map object, taken from the URL at startup and
// consumed once by ensureMap(). Null the rest of the time: a later rebuild
// carries the outgoing map's own view over instead.
let pendingView = null;
// Where the home button goes: the imported area, when the server said.
let homeBounds = null;
// Whether the map still shows the home view: set by goHome, cleared by the
// next pan or zoom. A flag rather than a comparison of views, because
// resizing the map (invalidateSize, on every tab switch) shifts the centre
// without anyone moving it.
let atHome = false;

// Whatever setTileLayer was last told to draw, replayed after a rebuild --
// ensureMap() throws every layer away, and the caller shouldn't have to
// know that.
let lastTileSpec = null;
let lastGridSpec = null;

// The legend panel: whether it is open, and the legend it shows ({url,
// title}, or null while no theme is served). Kept here, not in the panel,
// which a rebuild throws away with the map.
let legendOpen = false;
let legendSpec = null;
let legendPanel = null;
let legendButton = null;

const listeners = { move: [], draw: [], rebuild: [], tileerror: [], legend: [] };

export function on(event, callback) {
  listeners[event].push(callback);
}

function emit(event) {
  for (const callback of listeners[event]) {
    callback();
  }
}

export function getMap() {
  return map;
}

export function setPendingView(view) {
  pendingView = view;
}

export function setHomeBounds(bounds) {
  homeBounds = bounds;
}

// Unanimated, so the flag is set after the fit's own movestart. The move it
// causes was already written with the position; the second 'move' writes
// the URL again, now without it.
export function goHome() {
  if (homeBounds) {
    map.fitBounds(homeBounds, { animate: false });
  } else {
    map.setView(DEFAULT_CENTER, DEFAULT_ZOOM, { animate: false });
  }
  atHome = true;
  emit('move');
}

// At home the URL carries no position, and a reload goes home again.
export function isAtHome() {
  return atHome;
}

// `_isValidTile` for both the tile layer and the debug grid below. Only ever
// *narrows* what Leaflet would accept, so EPSG:3857 behaviour is unchanged
// (and x-wrapping across the antimeridian still works, since a CRS that
// wraps an axis has no edge on it to fall off).
//
// Shared rather than copied, so the overlay traces exactly the tiles that
// get requested: for a non-3857 TileMatrixSet Leaflet has no bound of
// its own, and a grid without this would draw phantom cells past the edge of
// the matrix that no tile will ever appear in.
//
// Calls into L.GridLayer, which is where the method is defined --
// L.TileLayer inherits it unchanged, so this is the same base call for both.
function clampedIsValidTile(coords) {
  if (!L.GridLayer.prototype._isValidTile.call(this, coords)) {
    return false;
  }
  if (!this.options.matrixSize) {
    return true;
  }
  const size = this.options.matrixSize(coords.z);
  if (!size) {
    return false;
  }
  const crs = this._map.options.crs;
  if (!crs.wrapLng && (coords.x < 0 || coords.x >= size.width)) {
    return false;
  }
  if (!crs.wrapLat && (coords.y < 0 || coords.y >= size.height)) {
    return false;
  }
  return true;
}

// A tile layer that loads a ring of tiles beyond the visible extent, so the
// user doesn't watch tiles load in every time they pan.
//
// The ring is loaded by Leaflet itself rather than by a separate prefetcher
// firing its own requests, for two reasons: `this._tiles` is then the dedup
// (the server has no single-flight, so a tile requested twice is *rendered*
// twice, burning two Mapnik pool slots), and pan-away/zoom cancellation
// comes for free, since Leaflet aborts a pending tile when it prunes it.
//
// The ring is loaded only on a deliberate second pass once the map has
// settled (see _schedulePrefetch), so a drag issues exactly the requests an
// unbuffered layer would.
const BufferedTileLayer = L.TileLayer.extend({
  options: {
    keepBuffer: TILE_KEEP_BUFFER,
    // z -> {width, height}, or null to leave clamping entirely to Leaflet.
    matrixSize: null,
  },

  // The one override that grows the loaded extent. `_update` is the only
  // caller, so padding here affects loading and nothing else.
  //
  // Do NOT move this to `_pxBoundsToTileRange`, which looks like the more
  // natural hook: `_resetGrid` calls that same method to build
  // `_globalTileRange`, which is what `_isValidTile` uses to reject tiles
  // outside the world. Padding it would have Leaflet request y=-1 and
  // y=2**z, and the XYZ route 404s both.
  _getTiledPixelBounds: function (center) {
    const bounds = L.TileLayer.prototype._getTiledPixelBounds.call(this, center);
    if (!this._bufferActive) {
      return bounds;
    }
    const buffer = this._effectiveBuffer(bounds);
    if (buffer <= 0) {
      return bounds;
    }
    const tileSize = this.getTileSize();
    const pad = L.point(tileSize.x * buffer, tileSize.y * buffer);
    // Point.subtract/add return new points; `bounds` must not be mutated.
    return L.bounds(bounds.min.subtract(pad), bounds.max.add(pad));
  },

  // Shrink the ring on very large viewports, where a fixed buffer would mean
  // several hundred extra renders. Picks the widest ring whose extra tile
  // count still fits MAX_PREFETCH_TILES.
  _effectiveBuffer: function (bounds) {
    const range = L.TileLayer.prototype._pxBoundsToTileRange.call(this, bounds);
    const cols = range.max.x - range.min.x + 1;
    const rows = range.max.y - range.min.y + 1;
    for (let b = TILE_BUFFER; b > 0; b--) {
      if ((cols + 2 * b) * (rows + 2 * b) - cols * rows <= MAX_PREFETCH_TILES) {
        return b;
      }
    }
    return 0;
  },

  _isValidTile: clampedIsValidTile,

  onAdd: function (map_) {
    L.TileLayer.prototype.onAdd.call(this, map_);
    // Registered here rather than via getEvents(), so these run *after*
    // GridLayer's own handlers for the same event -- we want to schedule the
    // ring only once Leaflet has finished reacting to the move.
    this._map.on('movestart zoomstart', this._cancelPrefetch, this);
    this._map.on('moveend zoomend', this._schedulePrefetch, this);
    this.on('load', this._schedulePrefetch, this);
  },

  // setTileLayer() rebuilds the layer on every theme/mode/format/CRS change
  // and on every style save, so this runs often -- leaving a timer or a map
  // listener behind would leak a layer per edit.
  onRemove: function (map_) {
    this._cancelPrefetch();
    map_.off('movestart zoomstart', this._cancelPrefetch, this);
    map_.off('moveend zoomend', this._schedulePrefetch, this);
    this.off('load', this._schedulePrefetch, this);
    L.TileLayer.prototype.onRemove.call(this, map_);
  },

  _cancelPrefetch: function () {
    if (this._prefetchTimer) {
      clearTimeout(this._prefetchTimer);
      this._prefetchTimer = null;
    }
  },

  // Both triggers are needed. 'load' is the one that matters on a cold
  // cache: it guarantees the ring is requested only after every visible tile
  // has arrived. But a pan landing entirely on already-loaded tiles never
  // fires 'load' at all, and 'moveend' covers that.
  _schedulePrefetch: function () {
    this._cancelPrefetch();
    this._prefetchTimer = setTimeout(() => {
      this._prefetchTimer = null;
      this._runPrefetch();
    }, PREFETCH_IDLE_MS);
  },

  _runPrefetch: function () {
    if (!this._map || this._map._animatingZoom || this._tileZoom === undefined) {
      return;
    }
    if (this._bufferActive) {
      return;
    }
    // _update() builds and dispatches its whole queue synchronously, so the
    // flag cannot still be set when a later drag-driven _update() runs. It
    // skips tiles already in this._tiles, so this pass adds only the ring.
    this._bufferActive = true;
    try {
      this._update();
    } finally {
      this._bufferActive = false;
    }
  },
});

// Tile-boundary overlay for debugging: red cell outlines with each cell's
// z/x/y on it, drawn on the map's own grid so it labels exactly the tiles
// the layer above requests. The label reads the same in both request modes
// -- z/x/y are the {z}/{x}/{y} of the XYZ path and the
// TILEMATRIX/TILECOL/TILEROW of the WMTS query alike.
const DebugGridLayer = L.GridLayer.extend({
  options: {
    // Above the tile pane, so a tile that finishes loading later can't end
    // up covering the grid.
    pane: 'overlayPane',
    className: 'debug-grid',
    // z -> {width, height}, same contract as on BufferedTileLayer.
    matrixSize: null,
  },

  _isValidTile: clampedIsValidTile,

  createTile: function (coords) {
    const tile = L.DomUtil.create('div', 'debug-grid-tile');
    // The label needs its own element: the backing plate has to be sized to
    // the text, not to the whole 256px cell.
    const label = L.DomUtil.create('span', 'debug-grid-label', tile);
    label.textContent = `${coords.z}/${coords.x}/${coords.y}`;
    return tile;
  },
});

// Must match .map-toolbar-slider's width and its thumb pseudo-elements'
// width in devtools.css. A range input's thumb travels only
// trackLength - thumbSize (the browser never lets the thumb's own box cross
// the track's ends), so the track's filled part has to bake in that inset
// too, or the fill ends beside the thumb rather than under it. The thumb
// has no reliable default size across browsers, which is why it is pinned
// in CSS.
const SLIDER_TRACK_LENGTH = 140;
const SLIDER_THUMB_SIZE = 12;

// Where the thumb's center sits for a given zoom, as a 0-1 fraction of the
// whole track.
function sliderFraction(z, maxZoom) {
  if (maxZoom <= 0) {
    return 0.5;
  }
  const travel = SLIDER_TRACK_LENGTH - SLIDER_THUMB_SIZE;
  return (SLIDER_THUMB_SIZE / 2 + (z / maxZoom) * travel) / SLIDER_TRACK_LENGTH;
}

const ICONS = {
  zoomIn: '<path d="M8 3v10M3 8h10"/>',
  zoomOut: '<path d="M3 8h10"/>',
  home: '<path d="M2.5 8L8 3l5.5 5M4 7v6h3v-3.5h2V13h3V7"/>',
  polyline: '<path d="M2 13l4-7 4 4 4-7"/>',
  polygon: '<path d="M3 12L2 5l6-3 6 4-3 7z"/>',
  rectangle: '<rect x="2.5" y="3.5" width="11" height="9"/>',
  circle: '<circle cx="8" cy="8" r="5.5"/>',
  clear: '<path d="M4 4l8 8M12 4l-8 8"/>',
  legend: '<rect x="2" y="2.5" width="3" height="3"/><rect x="2" y="10.5" width="3" height="3"/>'
    + '<path d="M7.5 4h6.5M7.5 12h6.5M2 8h3M7.5 8h6.5"/>',
};

// polyline/polygon/rectangle/circle, no marker: every one of these is a
// search *area*, and a bare point has no area to intersect with.
// circlemarker is out for the same reason (it is a screen-radius
// decoration, not a ground distance, so it has no meaningful WKT).
const DRAW_TOOLS = [
  { icon: 'polyline', title: t('draw_line'), make: (m) => new L.Draw.Polyline(m, {}) },
  {
    icon: 'polygon',
    title: t('draw_polygon'),
    make: (m) => new L.Draw.Polygon(m, { allowIntersection: false, showArea: true }),
  },
  {
    icon: 'rectangle',
    title: t('draw_rectangle'),
    make: (m) => new L.Draw.Rectangle(m, { showArea: true }),
  },
  { icon: 'circle', title: t('draw_circle'), make: (m) => new L.Draw.Circle(m, {}) },
];

function toolbarButton(parent, icon, title, onClick) {
  const button = L.DomUtil.create('button', 'map-toolbar-button', parent);
  button.type = 'button';
  button.title = title;
  button.innerHTML = `<svg viewBox="0 0 16 16" aria-hidden="true">${ICONS[icon]}</svg>`;
  L.DomEvent.on(button, 'click', onClick);
  return button;
}

// The one control column on the map: zoom in/out with the current level
// between them, a slider for jumping straight to a level, the home button,
// the draw tools and the clear button. It replaces both Leaflet's zoom control and
// leaflet-draw's toolbar; the draw tools drive leaflet-draw's handlers
// directly. leaflet-draw's toolbar also offered edit and delete modes, but
// only one shape is ever held here, so a single clear button is the whole
// interaction.
const MapToolbar = L.Control.extend({
  options: { position: 'topleft', maxZoom: 0 },

  onAdd: function (map_) {
    const div = L.DomUtil.create('div', 'map-toolbar');
    const maxZoom = this.options.maxZoom;

    const zoomSection = L.DomUtil.create('div', 'map-toolbar-section', div);
    const zoomIn = toolbarButton(zoomSection, 'zoomIn', t('zoom_in'), () => map_.zoomIn());
    const value = L.DomUtil.create('div', 'map-toolbar-zoom', zoomSection);
    const zoomOut = toolbarButton(zoomSection, 'zoomOut', t('zoom_out'), () => map_.zoomOut());

    // Built from a horizontal <input type=range> rotated -90deg (see
    // devtools.css) rather than the nonstandard `orient="vertical"` /
    // `-webkit-appearance: slider-vertical` routes -- those disagree across
    // browsers on whether width/height swap meaning once vertical, whereas
    // a rotated horizontal input behaves identically everywhere. min sits
    // at the bottom and max at the top.
    const sliderSection = L.DomUtil.create('div', 'map-toolbar-section map-toolbar-slider-wrap', div);
    const slider = L.DomUtil.create('input', 'map-toolbar-slider', sliderSection);
    slider.type = 'range';
    slider.min = 0;
    slider.max = maxZoom;
    slider.step = 1;

    const homeSection = L.DomUtil.create('div', 'map-toolbar-section', div);
    toolbarButton(homeSection, 'home', t('home'), goHome);
    legendButton = toolbarButton(homeSection, 'legend', t('legend'),
                                 () => setLegendOpen(!legendOpen));
    legendButton.classList.toggle('active', legendOpen);

    const drawSection = L.DomUtil.create('div', 'map-toolbar-section', div);
    const tools = DRAW_TOOLS.map((tool) => {
      const handler = tool.make(map_);
      const button = toolbarButton(drawSection, tool.icon, tool.title, () => {
        if (handler.enabled()) {
          handler.disable();
          return;
        }
        for (const other of tools) {
          other.handler.disable();
        }
        handler.enable();
      });
      return { handler, button };
    });
    const markActive = () => {
      for (const { handler, button } of tools) {
        button.classList.toggle('active', handler.enabled());
      }
    };
    map_.on(`${L.Draw.Event.DRAWSTART} ${L.Draw.Event.DRAWSTOP}`, markActive);

    const clearSection = L.DomUtil.create('div', 'map-toolbar-section', div);
    toolbarButton(clearSection, 'clear', t('clear_shape'), () => clearDrawn());

    const update = () => {
      const z = Math.round(map_.getZoom());
      value.textContent = z;
      zoomIn.disabled = z >= map_.getMaxZoom();
      zoomOut.disabled = z <= map_.getMinZoom();
      // Only touch .value when it actually disagrees -- setting it while
      // the user is mid-drag would fight the browser's own thumb position.
      if (Number(slider.value) !== z) {
        slider.value = z;
      }
      // The track draws its own fill (see devtools.css) rather than relying
      // on the engine's progress fill, so it has to be told where the thumb
      // now is.
      slider.style.setProperty('--zoom-fill', `${sliderFraction(z, maxZoom) * 100}%`);
    };
    update();
    // 'zoom' (not just 'zoomend') so a button click, scroll, or a slider
    // drag all update the readout immediately rather than waiting for any
    // zoom animation.
    map_.on('zoom', update, this);

    // 'input' (not 'change'), so the map tracks the thumb continuously
    // while dragging. Unanimated, because update() -- and with it the
    // track's fill -- is driven by the map's 'zoom' event, which an
    // animated setZoom fires only once it has finished easing there: the
    // fill visibly trailed a step behind the thumb through a drag.
    L.DomEvent.on(slider, 'input', () => {
      map_.setZoom(Number(slider.value), { animate: false });
    });
    // Without these, a click or drag on the toolbar also pans the map
    // underneath, and a wheel scroll over it zooms the map -- the control
    // sits on top of the map pane, and Leaflet's own handlers listen on the
    // whole container beneath it.
    L.DomEvent.disableClickPropagation(div);
    L.DomEvent.disableScrollPropagation(div);

    return div;
  },
});

// The legend of the theme on the map, beside the toolbar. A control, so it
// moves and is thrown away with the map; its content is `legendSpec`.
const LegendPanel = L.Control.extend({
  options: { position: 'topright' },

  onAdd: function (map) {
    // Kept: `update` runs inside onAdd, before getContainer() has it.
    const div = this._div = L.DomUtil.create('div', 'legend-panel');
    const header = L.DomUtil.create('div', 'legend-panel-header', div);
    this._title = L.DomUtil.create('span', 'legend-panel-title', header);
    const close = L.DomUtil.create('button', 'legend-panel-close', header);
    close.type = 'button';
    close.title = t('legend_close');
    close.innerHTML = `<svg viewBox="0 0 16 16" aria-hidden="true">${ICONS.clear}</svg>`;
    L.DomEvent.on(close, 'click', () => setLegendOpen(false));
    const body = this._body = L.DomUtil.create('div', 'legend-panel-body', div);
    this._image = L.DomUtil.create('img', '', body);
    this._image.alt = t('legend');
    this._message = L.DomUtil.create('p', 'legend-panel-message hidden', body);
    // A missing legend is a style compile that predates it, not a broken
    // page: say so instead of showing a broken-image icon.
    L.DomEvent.on(this._image, 'error', () => this._show(t('legend_missing')));
    L.DomEvent.on(this._image, 'load', () => this._show(null));
    // As for the toolbar: a click or a scroll on the panel stays there.
    L.DomEvent.disableClickPropagation(div);
    L.DomEvent.disableScrollPropagation(div);
    map.on('resize', this._fit, this);
    this.update();
    return div;
  },

  onRemove: function (map) {
    map.off('resize', this._fit, this);
  },

  // A legend of every icon a theme draws is far taller than the map: the
  // body ends a control margin above the map's bottom and scrolls.
  _fit: function () {
    if (!this._map || !legendOpen) {
      return;
    }
    const top = this._body.getBoundingClientRect().top
      - this._map.getContainer().getBoundingClientRect().top;
    this._body.style.maxHeight = `${Math.max(this._map.getSize().y - top - 10, 80)}px`;
  },

  _show: function (message) {
    this._image.classList.toggle('hidden', message !== null);
    this._message.classList.toggle('hidden', message === null);
    this._message.textContent = message ?? '';
  },

  update: function () {
    this._div.classList.toggle('hidden', !legendOpen);
    this._title.textContent = legendSpec?.title ?? t('legend');
    if (!legendSpec) {
      this._image.removeAttribute('src');
      this._show('—');
    } else if (this._image.getAttribute('src') !== legendSpec.url) {
      this._image.src = legendSpec.url;
    }
    this._fit();
  },
});

// What the legend panel shows: {url, title}, or null when there is no theme.
export function setLegend(spec) {
  legendSpec = spec;
  legendPanel?.update();
}

export function setLegendOpen(open) {
  legendOpen = open;
  legendPanel?.update();
  legendButton?.classList.toggle('active', open);
  emit('legend');
}

export function isLegendOpen() {
  return legendOpen;
}

// Leaflet can't swap a live map's CRS, so switching to a differently-
// projected TileMatrixSet tears down and recreates the map object;
// switching theme/mode without a CRS change just swaps the tile layer.
// Either way the position is kept: the outgoing map's center and zoom are
// carried over (or `pendingView`, when the URL asked for a specific one), so
// a CRS switch shows the same place under the other projection instead of
// jumping back to the default view.
//
// It is the zoom *index* that carries, not the scale -- each TileMatrixSet
// defines its own resolution per level, so z8 in DE_EPSG_25832_ADV is not z8 in
// Web Mercator. The z in the URL means the same thing.
export function ensureMap(spec) {
  if (map && mapCrsId === spec.id) {
    return map;
  }
  // Read the outgoing view before remove(), which invalidates the map.
  const view = pendingView
    ?? (map ? { center: map.getCenter(), zoom: map.getZoom() } : null)
    ?? { center: DEFAULT_CENTER, zoom: DEFAULT_ZOOM };
  pendingView = null;

  // A rebuild throws every layer away, including the drawn shape -- so it
  // is serialized here and restored below, or drawing a polygon and then
  // switching CRS would silently lose it.
  const drawnWkt = getDrawnWkt();

  if (map) {
    map.remove();
  }
  map = L.map('map', { crs: spec.crs, zoomControl: false });
  // Registered before setView, so the initial view lands in the URL too.
  map.on('moveend zoomend', () => emit('move'));
  map.setView(view.center, Math.min(view.zoom, spec.maxZoom));
  // After setView, so a CRS switch at home stays home.
  map.on('movestart zoomstart', () => { atHome = false; });
  // Bottom-left ground-distance bar (5m/10m/20m/50m/.../1km/...), re-labeled
  // by Leaflet itself as the zoom level changes. Metric only -- this app has
  // no imperial-unit audience, and a second bar would just be clutter.
  L.control.scale({ position: 'bottomleft', imperial: false }).addTo(map);

  tileLayer = null;
  debugGridLayer = null;
  drawItems = null;
  mapCrsId = spec.id;

  initDraw();
  new MapToolbar({ maxZoom: spec.maxZoom }).addTo(map);
  legendPanel = new LegendPanel().addTo(map);
  if (drawnWkt) {
    setDrawnWkt(drawnWkt);
  }
  // Replay whatever the tabs had asked for before the rebuild.
  if (lastTileSpec) {
    setTileLayer(lastTileSpec.template, lastTileSpec.options);
  }
  if (lastGridSpec) {
    setDebugGrid(lastGridSpec.on, lastGridSpec.options);
  }
  emit('rebuild');
  return map;
}

export function setTileLayer(template, options) {
  // The same layer again is kept, not rebuilt: a rebuild drops every loaded
  // tile, and a tab switch asks for the layer it already has.
  const same = tileLayer && lastTileSpec?.template === template
    && JSON.stringify(lastTileSpec.options) === JSON.stringify(options);
  lastTileSpec = { template, options };
  if (!map || same) {
    return;
  }
  if (tileLayer) {
    map.removeLayer(tileLayer);
  }
  // BufferedTileLayer overrides Leaflet-private methods. They've been stable
  // since 1.0 and the version is pinned in the page's <script> tag, but a
  // future bump renaming one would otherwise break the page outright -- so
  // fall back to an unbuffered layer, which is how this behaved before.
  if (typeof L.TileLayer.prototype._getTiledPixelBounds === 'function') {
    tileLayer = new BufferedTileLayer(template, options);
  } else {
    console.warn(
      'Leaflet is missing _getTiledPixelBounds; falling back to an unbuffered '
      + 'tile layer (tiles will visibly load in when panning).'
    );
    tileLayer = L.tileLayer(template, options);
  }
  // Otherwise a failed tile request looks identical to a blank one.
  tileLayer.on('tileerror', (e) => {
    for (const callback of listeners.tileerror) {
      callback(e);
    }
  });
  // Below everything else: the draw layer and the search results have to
  // stay on top of the basemap.
  tileLayer.addTo(map);
  tileLayer.bringToBack();
}

// (Re)draws the debug grid. Kept separate from setTileLayer because the
// checkbox deliberately does *not* go through a tile refresh: that would
// bump the cache-busting ?v= and re-render the whole viewport plus the
// prefetch ring cold just to draw an overlay.
export function setDebugGrid(on, options) {
  lastGridSpec = { on, options };
  if (!map) {
    return;
  }
  if (debugGridLayer) {
    map.removeLayer(debugGridLayer);
    debugGridLayer = null;
  }
  if (!on) {
    return;
  }
  debugGridLayer = new DebugGridLayer(options);
  debugGridLayer.addTo(map);
}

// ---- draw tools -------------------------------------------------------

function initDraw() {
  drawItems = L.featureGroup().addTo(map);

  // Only ever one shape: a second drawn shape replaces the first rather than
  // adding to it. Two shapes would have to be combined into one WKT
  // GEOMETRYCOLLECTION for the server, and "the area I just drew" is what
  // the control actually means.
  map.on(L.Draw.Event.CREATED, (event) => {
    drawItems.clearLayers();
    drawItems.addLayer(event.layer);
    emit('draw');
  });
}

export function hasDrawnShape() {
  return Boolean(drawItems && drawItems.getLayers().length > 0);
}

export function getDrawnWkt() {
  if (!hasDrawnShape()) {
    return null;
  }
  return layerToWkt(drawItems.getLayers()[0]);
}

// Restores a shape from WKT (a URL, typically). Silently does nothing for
// WKT this page can't draw -- see wktToLayer on why a bad URL should open
// the page rather than break it.
export function setDrawnWkt(wkt) {
  if (!drawItems) {
    return false;
  }
  const layer = wktToLayer(wkt);
  drawItems.clearLayers();
  if (!layer) {
    return false;
  }
  drawItems.addLayer(layer);
  return true;
}

export function clearDrawn() {
  if (!drawItems) {
    return;
  }
  drawItems.clearLayers();
  emit('draw');
}
