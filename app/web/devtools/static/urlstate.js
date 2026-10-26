// The address bar mirrors both tabs' state, so a view is reloadable and can
// be handed to someone else as a URL:
//
//   /devtools?tab=search&smode=phrase&q=restaurant%20kiel&geom=POLYGON((...))&page=2
//
// Each module contributes its own slice through
// registerCollector rather than this file reaching into the tabs, so the
// tiles tab's vocabulary (theme/mode/format/grid/debug/legend) and the search
// tab's (smode/q/street/hn/pc/city/radius/cat/inview/within/fuzzy/sort/sim/geom/
// page/here) stay out of each other's way.
//
// The key is deliberately *not* part of the state: a URL is something you
// paste into a chat, and a key in it is a key in the chat log.

const collectors = [];

export function registerCollector(collect) {
  collectors.push(collect);
}

export function writeStateToUrl() {
  const params = new URLSearchParams();
  for (const collect of collectors) {
    for (const [key, value] of Object.entries(collect() || {})) {
      if (value !== null && value !== undefined && value !== '') {
        params.set(key, String(value));
      }
    }
  }
  // replaceState, not pushState: a pan must not fill the back button. This
  // is also why callers write on moveend/zoomend rather than per frame --
  // browsers rate-limit history writes.
  history.replaceState(null, '', `${location.pathname}?${params}`);
}

// Raw strings (or null). Every value is validated where it is *applied* --
// a theme against the served theme list, a geom against the WKT parser --
// none of which this file knows about.
export function readStateFromUrl() {
  const params = new URLSearchParams(location.search);
  const get = (key) => params.get(key);
  // Only what the scripts apply themselves. The tab, the radios, the
  // fields and the checkboxes the server renders as the URL sets them
  // (`controls()` in web/devtools/__init__.py), so they are right before
  // any script has run.
  return {
    lang: get('lang'),
    lat: get('lat'),
    lon: get('lon'),
    z: get('z'),
    // tiles tab: checked against the served themes and grids
    theme: get('theme'),
    grid: get('grid'),
    legend: get('legend'),
    // search tab
    cat: get('cat'),
    geom: get('geom'),
    page: get('page'),
    here: get('here'),
  };
}

// A complete numeric view, or null -- half a position is no position.
export function viewFromState(state) {
  const raw = [state.lat, state.lon, state.z];
  if (raw.some((value) => value === null || value === '')) {
    return null;
  }
  const [lat, lon, zoom] = raw.map(Number);
  if (![lat, lon, zoom].every(Number.isFinite)) {
    return null;
  }
  return { center: [lat, lon], zoom };
}
