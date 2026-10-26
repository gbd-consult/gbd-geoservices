// Bootstraps the page and owns what no single tab does: which tab is in
// front, and the Status tab: the API key field and the two status lines.
//
// Server: which area is served and when it was imported.
//
// Styles: the server's style watcher, polled when `devtools_watch` is on.
// When it has recompiled, the themes are re-read, which moves every tile
// URL's generation and redraws the map; when a recompile failed, its error
// is shown here.

import * as api from './api.js';
import { lang, t } from './i18n.js';
import * as mapview from './mapview.js';
import * as search from './search.js';
import * as tiles from './tiles.js';
import { readStateFromUrl, registerCollector, viewFromState, writeStateToUrl } from './urlstate.js';

const TABS = ['tiles', 'search', 'status'];
const tabRadios = document.querySelectorAll('input[name="tab"]');
const keyInput = document.getElementById('apiKey');
const keyApply = document.getElementById('apiKeyApply');
const statusDot = document.getElementById('serverDot');
const statusText = document.getElementById('serverStatus');
const styleDot = document.getElementById('styleDot');
const styleText = document.getElementById('styleStatus');
const keyNotice = document.getElementById('keyNotice');

const WATCH_POLL_MS = 1500;
const WATCH_ON = document.querySelector('meta[name="watch"]').content === 'on';
let seenCompiles = null;

function currentTab() {
  return document.querySelector('input[name="tab"]:checked').value;
}

function applyTab() {
  const tab = currentTab();
  for (const name of TABS) {
    document.getElementById(`panel-${name}`).classList.toggle('hidden', name !== tab);
  }
  // Status has no use for the grid, so it keeps whichever the tab before
  // it had rather than switching the map.
  if (tab !== 'status') {
    tiles.setWebMercatorLock(tab === 'search');
  }
  search.onTabShown();
  const map = mapview.getMap();
  if (map) {
    map.invalidateSize();
  }
  writeStateToUrl();
}

// Over the map while the server refuses the key. /status takes any valid
// key, whatever its scopes, so its 401 means exactly "no key, or a wrong
// one" -- and a blank map says neither.
function showKeyNotice(reason) {
  keyNotice.classList.toggle('hidden', !reason);
  for (const heading of keyNotice.querySelectorAll('[data-key]')) {
    heading.classList.toggle('hidden', heading.dataset.key !== reason);
  }
}

function goToKeyField() {
  document.querySelector('input[name="tab"][value="status"]').checked = true;
  applyTab();
  keyInput.focus();
}

async function loadStatus() {
  try {
    const version = await api.request('/status');
    showKeyNotice(null);
    const parts = [`${version.area}`, `v${version.version}`];
    const imported = version.imported;
    if (imported) {
      const when = imported.at ? new Date(imported.at).toLocaleString(lang) : '?';
      parts.push(t('imported', { when }));
    } else {
      parts.push(t('no_import'));
    }
    if (version.auth === 'open') {
      parts.push(t('auth_open'));
    }
    statusDot.className = `watch-dot ${imported ? 'ok' : 'warn'}`;
    statusText.textContent = parts.join(' · ');
  } catch (error) {
    statusDot.className = 'watch-dot err';
    statusText.textContent = `/status: ${error.message}`;
    showKeyNotice(error.status === 401 ? (api.getKey() ? 'invalid' : 'missing') : null);
  }
}

async function pollWatcher() {
  try {
    const watch = await api.request('/devtools/api/watch');
    if (seenCompiles !== null && watch.compiles !== seenCompiles) {
      tiles.reloadThemes();
      loadStatus();
    }
    seenCompiles = watch.compiles;
    const changed = watch.changed.join(', ');
    if (!watch.watching) {
      styleDot.className = 'watch-dot';
      styleText.textContent = t('not_watching');
    } else if (watch.running) {
      styleDot.className = 'watch-dot warn';
      styleText.textContent = t('compiling', { changed });
    } else if (watch.error) {
      styleDot.className = 'watch-dot err';
      styleText.textContent = t('compile_failed', { changed, error: watch.error });
    } else if (watch.finished_at) {
      const when = new Date(watch.finished_at).toLocaleTimeString(lang);
      styleDot.className = 'watch-dot ok';
      const seconds = watch.seconds.toLocaleString(lang, {
        minimumFractionDigits: 1, maximumFractionDigits: 1,
      });
      styleText.textContent = t('watching_compiled', { when, seconds, changed });
    } else {
      styleDot.className = 'watch-dot ok';
      styleText.textContent = t('watching');
    }
  } catch (error) {
    styleDot.className = 'watch-dot err';
    styleText.textContent = `/devtools/api/watch: ${error.message}`;
  }
  setTimeout(pollWatcher, WATCH_POLL_MS);
}

// Where the map opens when the URL does not say, and where the home button
// goes: fitted to the imported area, rather than a fixed view that is empty
// tiles for every other one.
// Fitted, not centred at a fixed zoom -- Liechtenstein at the zoom that
// suits Schleswig-Holstein is a speck.
async function importedBounds() {
  try {
    const extent = await api.request('/devtools/api/extent');
    if (extent.bbox) {
      const [west, south, east, north] = extent.bbox;
      return [[south, west], [north, east]];
    }
  } catch {
    // Falls through to mapview's default view.
  }
  return null;
}

// The language links keep the rest of the URL -- the view, the tab, every
// field and checkbox -- so switching language does not lose what is on
// screen. The state is written first: a typed query is in the URL only
// once its field has lost focus. Until every tab has registered its
// collector, the URL as it is already holds the state. Without this script
// the plain `?lang=` link still switches, from a fresh page.
let collectorsReady = false;

function initLanguageLinks() {
  for (const link of document.querySelectorAll('.lang-switch a[data-lang]')) {
    link.addEventListener('click', (event) => {
      event.preventDefault();
      if (collectorsReady) {
        writeStateToUrl();
      }
      const params = new URLSearchParams(location.search);
      params.set('lang', link.dataset.lang);
      location.search = params.toString();
    });
  }
}

function initKeyField() {
  keyInput.value = api.getKey();
  const apply = () => {
    api.setKey(keyInput.value.trim());
    // Every tile URL and every request changes, so rebuild both.
    tiles.reloadThemes();
    loadStatus();
  };
  keyApply.addEventListener('click', apply);
  document.getElementById('keyNoticeGo').addEventListener('click', goToKeyField);
  keyInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      apply();
    }
  });
}

async function main() {
  const state = readStateFromUrl();
  initLanguageLinks();

  // The server has rendered `?tab=` in front already.
  for (const radio of tabRadios) {
    radio.addEventListener('change', applyTab);
  }
  // `lang` is carried as the URL had it: every state write rebuilds the
  // query string, and a reload must not fall back to the default language.
  registerCollector(() => ({ tab: currentTab() === 'tiles' ? '' : currentTab(), lang: state.lang }));

  const fromUrl = viewFromState(state);
  mapview.setPendingView(fromUrl);
  mapview.setHomeBounds(await importedBounds());

  // The map position is shared, so it is collected here rather than by
  // either tab.
  registerCollector(() => {
    const map = mapview.getMap();
    if (!map || mapview.isAtHome()) {
      return {};
    }
    const center = map.getCenter();
    return {
      z: String(Number(map.getZoom().toFixed(2))),
      lat: center.lat.toFixed(5),
      lon: center.lng.toFixed(5),
    };
  });
  mapview.on('move', writeStateToUrl);

  initKeyField();
  const categories = search.init(state);
  // Creates the map, so everything that needs one comes after it.
  await tiles.init(state);
  if (!fromUrl) {
    mapview.goHome();
  }
  await categories;

  search.applyUrlGeometry(state);
  collectorsReady = true;
  applyTab();
  search.applyUrlHere(state);
  loadStatus();
  if (WATCH_ON) {
    pollWatcher();
  } else {
    styleDot.className = 'watch-dot';
    styleText.textContent = t('not_watching_off');
  }

  // A URL carrying a query is a shared search -- run it, so the link shows
  // what its sender saw rather than an empty list.
  if (currentTab() === 'search' && search.hasQuery()) {
    // Zoomed to the results, unless the link also carried a view -- then
    // the sender's view is what they meant to share.
    search.search({ zoom: !viewFromState(state) });
  }
}

main();
