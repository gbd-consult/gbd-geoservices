// The Search tab: the three text modes, and "what's here" -- the point
// mode, whose request is a click on the map.
//
// `/search` takes `mode` + `text`, has a free-form phrase mode that reports
// how it read the query, filters by category, and answers a point with the
// point mode. The result list has one property table per hit, clickable
// both ways between list and map, and the draw tools mean "search inside
// this shape".

import * as api from './api.js';
import * as catpicker from './catpicker.js';
import { lang, t } from './i18n.js';
import * as mapview from './mapview.js';
import { registerCollector, writeStateToUrl } from './urlstate.js';

const PAGE_SIZE = 20;

const modeRadios = document.querySelectorAll('input[name="smode"]');
const queryInput = document.getElementById('searchQuery');
const queryHint = document.getElementById('searchQueryHint');
const categoryPicker = catpicker.create({
  button: document.getElementById('searchCategory'),
  label: document.getElementById('searchCategoryLabel'),
  popup: document.getElementById('searchCategoryTree'),
});
const inViewCheckbox = document.getElementById('searchInView');
const withinCheckbox = document.getElementById('searchWithin');
const fuzzyCheckbox = document.getElementById('searchFuzzy');
const sortSelect = document.getElementById('searchSort');
const similarityInput = document.getElementById('searchSimilarity');
const similarityValue = document.getElementById('searchSimilarityValue');
const submitButton = document.getElementById('searchSubmit');
const clearButton = document.getElementById('searchClear');
const radiusInput = document.getElementById('hereRadius');
const addressInputs = {
  street: document.getElementById('addrStreet'),
  housenumber: document.getElementById('addrNumber'),
  postcode: document.getElementById('addrPostcode'),
  city: document.getElementById('addrCity'),
};
const panel = document.getElementById('panel-search');
const geomNote = document.getElementById('searchGeomNote');
const errorBox = document.getElementById('searchError');
const busyBox = document.getElementById('searchBusy');
const summaryBox = document.getElementById('searchSummary');
const interpretationBox = document.getElementById('searchInterpretation');
const pager = document.getElementById('searchPager');
const prevButton = document.getElementById('searchPrev');
const nextButton = document.getElementById('searchNext');
const pageLabel = document.getElementById('searchPageLabel');
const resultsBox = document.getElementById('searchResults');

const HINTS = {
  name: t('hint_name'),
  phrase: t('hint_phrase'),
};

const LAYER_STYLE = {
  // Half transparent, so the street name under a highlighted street reads.
  normal: { color: '#2563eb', weight: 3, opacity: 0.5, fillOpacity: 0.15 },
  selected: { color: '#dc2626', weight: 5, opacity: 0.5, fillOpacity: 0.3 },
  // Outline only: "what's here" returns every area containing the point --
  // municipality, district, country -- and a fill each stacks into a tint
  // over the whole map.
  here: { color: '#7c3aed', weight: 3, opacity: 0.9, fillOpacity: 0 },
};

const state = {
  page: 0,
  total: 0,
  hasMore: false,
  features: [],
  layers: [],
  selectedIndex: -1,
  searched: false,
  // 'search' | 'here' -- what the current list is, which decides whether
  // the pager and the summary mean anything.
  kind: 'search',
  hereMarker: null,
  // The last clicked point, so a new radius asks about the same place.
  herePoint: null,
  // Incremented per request; a response for anything but the latest is
  // dropped. Switching mode re-runs the current query, so a mode switch
  // followed at once by a submit puts two requests in flight, and without
  // this whichever answered *last* would win.
  seq: 0,
};

function currentMode() {
  return document.querySelector('input[name="smode"]:checked').value;
}

function addressValue(name) {
  return addressInputs[name].value.trim();
}

// The body `/search` takes. bbox and area are alternatives the server
// refuses together, so a drawn shape wins and the view box is left out.
// The address mode takes its parts as fields and refuses text and
// categories.
function buildBody() {
  const body = {
    mode: currentMode(),
    page: state.page,
    limit: PAGE_SIZE,
    sort: sortSelect.value,
    similarity: Number(similarityInput.value),
    lang,
  };
  if (currentMode() === 'address') {
    for (const name of Object.keys(addressInputs)) {
      if (addressValue(name)) {
        body[name] = addressValue(name);
      }
    }
  } else {
    body.text = queryInput.value.trim();
    if (categoryPicker.value) {
      body.categories = [categoryPicker.value];
    }
  }
  const map = mapview.getMap();
  const drawn = mapview.getDrawnWkt();
  if (drawn) {
    body.area = drawn;
    body.within = withinCheckbox.checked;
  } else if (inViewCheckbox.checked && map) {
    const b = map.getBounds();
    body.bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
  }
  // Distance is measured from the centre of what is on screen, which is
  // what "near here" means to the person looking at it.
  if (map) {
    const centre = map.getCenter();
    body.near = [centre.lng, centre.lat];
  }
  return body;
}

export function hasQuery() {
  if (currentMode() === 'address') {
    return Boolean(addressValue('street') && addressValue('housenumber'));
  }
  return Boolean(queryInput.value.trim() || categoryPicker.value);
}

export async function search({ zoom = false } = {}) {
  if (!hasQuery()) {
    showError(t(currentMode() === 'address' ? 'enter_address' : 'enter_query'));
    return;
  }
  const body = buildBody();
  startRequest();
  const started = performance.now();
  // The button is never disabled while a request is in flight: a click
  // then fell on a disabled button and vanished (switch mode, which re-runs
  // the query, then press Search at once). The sequence number is what
  // makes overlapping requests safe instead.
  const seq = ++state.seq;
  try {
    // Ticked, the name mode asks the fuzzy name search alone; every other
    // search, and the name mode unticked, goes to `/search`.
    const path = fuzzyCheckbox.checked && currentMode() === 'name' ? '/search/fuzzy' : '/search';
    const page = await api.request(path, { method: 'POST', body });
    if (seq !== state.seq) {
      return;
    }
    const elapsed = performance.now() - started;
    state.kind = 'search';
    state.searched = true;
    state.total = page.total;
    state.hasMore = page.has_more;
    state.features = page.results.features;
    summaryBox.textContent = t('summary', {
      total: page.total, page: page.page + 1, ms: Math.round(elapsed),
    });
    renderInterpretation(page.interpretation);
    renderResults();
    if (zoom) {
      zoomToAll();
    }
  } catch (error) {
    if (seq === state.seq) {
      showError(`${error.status ?? ''} ${error.message}`.trim());
    }
  } finally {
    if (seq === state.seq) {
      busyBox.classList.add('hidden');
      syncClearButton();
      writeStateToUrl();
    }
  }
}

// What the phrase parser made of the query. Without it a list of results
// is unexplainable: nothing on the page says whether "Kiel" was read as a
// place, as a name, or as neither.
function renderInterpretation(interpretation) {
  interpretationBox.innerHTML = '';
  interpretationBox.classList.toggle('hidden', !interpretation);
  if (!interpretation) {
    return;
  }
  const title = document.createElement('label');
  title.className = 'field-label';
  title.textContent = 'Interpretation';
  interpretationBox.appendChild(title);
  for (const reading of interpretation) {
    const row = document.createElement('div');
    row.className = 'interp-row';
    const parts = [`${reading.rule} (${reading.rows})`];
    if (reading.text) parts.push(t('read_text', { value: reading.text }));
    if (reading.name) parts.push(t('read_name', { value: reading.name }));
    if (reading.category) parts.push(t('read_category', { value: reading.category }));
    if (reading.place) parts.push(t('read_place', { value: reading.place }));
    if (reading.street) parts.push(t('read_street', { value: reading.street }));
    for (const address of reading.addresses || []) {
      parts.push(t('read_address', { value: Object.values(address).join(' ') }));
    }
    row.textContent = parts.join(' · ');
    interpretationBox.appendChild(row);
  }
}

// The radius field as the `radius` parameter, or null: empty or out of
// range leaves the server's own radii.
function hereRadius() {
  const radius = Number(radiusInput.value);
  return radiusInput.value.trim() && Number.isFinite(radius) && radius > 0 && radius <= 10000
    ? radius : null;
}

async function whatsHere(latlng) {
  startRequest();
  state.herePoint = latlng;
  placeHereMarker(latlng);
  const seq = ++state.seq;
  const request = {
    mode: 'point',
    near: [Number(latlng.lng.toFixed(6)), Number(latlng.lat.toFixed(6))],
    lang,
  };
  const radius = hereRadius();
  if (radius !== null) {
    request.radius = radius;
  }
  try {
    const body = await api.request('/search', { method: 'POST', body: request });
    if (seq !== state.seq) {
      return;
    }
    state.kind = 'here';
    state.searched = false;
    state.page = 0;
    state.total = body.count;
    state.hasMore = false;
    // The server puts the nearest address first: it names the click, and
    // the list under it is what lies there.
    state.features = body.results.features;
    summaryBox.textContent = t('here_summary', { count: body.count });
    renderInterpretation(null);
    renderResults();
  } catch (error) {
    showError(`${error.status ?? ''} ${error.message}`.trim());
  }
  if (seq === state.seq) {
    busyBox.classList.add('hidden');
  }
  syncClearButton();
  writeStateToUrl();
}

function placeHereMarker(latlng) {
  const map = mapview.getMap();
  if (state.hereMarker) {
    state.hereMarker.remove();
  }
  state.hereMarker = L.circleMarker(latlng, {
    radius: 7, color: '#7c3aed', weight: 3, fillOpacity: 0.4,
  }).addTo(map);
}

function renderResults() {
  const map = mapview.getMap();
  for (const layer of state.layers) {
    layer.remove();
  }
  state.layers = [];
  state.selectedIndex = -1;
  resultsBox.innerHTML = '';

  state.features.forEach((feature, index) => {
    resultsBox.appendChild(buildResultCard(index, feature));
    if (map && feature.geometry) {
      const layer = buildResultLayer(index, feature);
      layer.addTo(map);
      state.layers.push(layer);
    } else {
      state.layers.push(null);
    }
  });
  renderPager();
}

// Every property, alphabetically, as the API sends it -- nulls included,
// since the viewer is for checking the response shape as much as the hit.
function allProperties(properties) {
  return Object.keys(properties).sort().map((key) => {
    const value = properties[key];
    const text = value !== null && typeof value === 'object' ? JSON.stringify(value) : String(value);
    return [key, text];
  });
}

const ZOOM_ICON = '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">'
  + '<circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" stroke-width="1.6"/>'
  + '<path d="M10.5 10.5 14 14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';
const REVEAL_ICON = '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">'
  + '<path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" stroke-width="1.6"'
  + ' stroke-linecap="round" stroke-linejoin="round"/></svg>';

function iconButton(className, title, svg, onClick) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `result-icon ${className}`;
  button.title = title;
  button.innerHTML = svg;
  button.addEventListener('click', (event) => {
    event.stopPropagation();
    onClick(button);
  });
  return button;
}

function resultTitle(properties) {
  if (properties.name) {
    return properties.name;
  }
  const join = (parts) => parts.filter(Boolean).join(' ');
  const address = [
    join([properties.address_street, properties.address_housenumber]),
    join([properties.address_postcode, properties.address_city]),
  ].filter(Boolean).join(', ');
  return address || properties.category_name || '';
}

function buildResultCard(index, feature) {
  const properties = feature.properties;
  const card = document.createElement('div');
  card.className = 'result-card';
  card.dataset.resultIndex = String(index);
  // A guess -- anything short of an exact match -- reads differently at a
  // glance from an answer.
  const relevance = properties.match_relevance;
  if (relevance !== undefined && relevance !== null && relevance < 100) {
    card.classList.add('guessed');
  }

  const table = document.createElement('table');
  table.className = 'result-table hidden';
  for (const [label, value] of allProperties(properties)) {
    const row = table.insertRow();
    const keyCell = row.insertCell();
    keyCell.className = 'result-key';
    keyCell.textContent = label;
    const valueCell = row.insertCell();
    valueCell.className = 'result-value';
    valueCell.textContent = value;
  }

  const head = document.createElement('div');
  head.className = 'result-head';
  const zoom = iconButton('result-zoom', t('zoom_to'), ZOOM_ICON, () => selectResult(index, true));
  zoom.disabled = !feature.geometry;
  head.appendChild(zoom);
  head.appendChild(iconButton('result-reveal', t('all_properties'), REVEAL_ICON, (button) => {
    const open = table.classList.toggle('hidden') === false;
    button.classList.toggle('open', open);
  }));

  const text = document.createElement('div');
  text.className = 'result-text';
  const title = document.createElement('div');
  title.className = 'result-title';
  const name = document.createElement('span');
  name.className = 'result-name';
  name.textContent = resultTitle(properties) || t('unnamed');
  title.appendChild(name);
  if (properties.category_name) {
    title.appendChild(document.createTextNode(` • ${properties.category_name}`));
  }
  text.appendChild(title);
  const places = properties.places || [];
  if (places.length) {
    const path = document.createElement('div');
    path.className = 'result-places';
    path.textContent = places.map((place) => place.name).join(' • ');
    text.appendChild(path);
  }
  head.appendChild(text);

  card.appendChild(head);
  card.appendChild(table);
  card.addEventListener('click', () => selectResult(index));
  return card;
}

function buildResultLayer(index, feature) {
  const style = state.kind === 'here' ? LAYER_STYLE.here : LAYER_STYLE.normal;
  const layer = L.geoJSON(feature, {
    // A bare radius-1 point is invisible and points are most hits.
    pointToLayer: (point, latlng) => L.circleMarker(latlng, { radius: 6 }),
  });
  layer.setStyle(style);
  layer.on('click', (event) => {
    // In "what's here" a click is a request wherever it lands: the areas
    // of the last answer cover the whole view, and selecting one of them
    // instead left the mode with nothing to click on.
    if (hereMode()) {
      return;
    }
    L.DomEvent.stopPropagation(event);
    selectResult(index);
  });
  return layer;
}

// Selects a hit, or unselects it when it is selected already; `zoom`
// always selects and flies there.
function selectResult(index, zoom = false) {
  const next = zoom || index !== state.selectedIndex ? index : -1;
  const normal = state.kind === 'here' ? LAYER_STYLE.here : LAYER_STYLE.normal;
  for (const card of resultsBox.querySelectorAll('.result-card')) {
    card.classList.remove('selected');
  }
  for (const layer of state.layers) {
    if (layer) layer.setStyle(normal);
  }
  state.selectedIndex = next;
  if (next < 0) {
    return;
  }
  const card = resultsBox.querySelector(`[data-result-index="${next}"]`);
  if (card) {
    card.classList.add('selected');
    card.scrollIntoView({ block: 'nearest' });
  }
  const layer = state.layers[next];
  if (layer) {
    layer.setStyle(LAYER_STYLE.selected);
    layer.bringToFront();
    if (zoom) {
      zoomTo([layer]);
    }
  }
}

function zoomTo(layers) {
  const bounds = new L.LatLngBounds();
  for (const layer of layers) {
    if (layer) bounds.extend(layer.getBounds());
  }
  if (bounds.isValid()) {
    mapview.getMap().flyToBounds(bounds, { duration: 0.5, maxZoom: 17 });
  }
}

function zoomToAll() {
  zoomTo(state.layers);
}

function renderPager() {
  const show = state.kind === 'search' && state.searched && state.total > PAGE_SIZE;
  pager.classList.toggle('hidden', !show);
  const pages = Math.max(1, Math.ceil(state.total / PAGE_SIZE));
  pageLabel.textContent = t('page_of', { page: state.page + 1, pages });
  prevButton.disabled = state.page <= 0;
  nextButton.disabled = !state.hasMore;
}

async function goToPage(page) {
  if (page < 0 || page === state.page) {
    return;
  }
  state.page = page;
  await search();
}

function clearResults() {
  for (const layer of state.layers) {
    if (layer) layer.remove();
  }
  if (state.hereMarker) {
    state.hereMarker.remove();
    state.hereMarker = null;
  }
  // Bumping seq also discards a request still in flight, so a clear is
  // not undone by an answer arriving afterwards.
  Object.assign(state, {
    page: 0, total: 0, hasMore: false, features: [], layers: [],
    selectedIndex: -1, searched: false, kind: 'search', herePoint: null,
    seq: state.seq + 1,
  });
  resultsBox.innerHTML = '';
  summaryBox.textContent = '';
  busyBox.classList.add('hidden');
  renderInterpretation(null);
  showError('');
  renderPager();
  syncClearButton();
  writeStateToUrl();
}

// A new request empties the list and the map at once, so an answer that
// fails or is slow never sits under the previous request's results.
function startRequest() {
  showError('');
  state.features = [];
  renderResults();
  summaryBox.textContent = '';
  renderInterpretation(null);
  pager.classList.add('hidden');
  busyBox.classList.remove('hidden');
}

function showError(text) {
  errorBox.textContent = text;
  errorBox.classList.toggle('hidden', !text);
}

function syncClearButton() {
  clearButton.disabled = state.features.length === 0 && !queryInput.value
    && Object.values(addressInputs).every((input) => !input.value);
}

// A drawn shape and "only in view" are alternatives, like bbox and area in
// the body; the shape wins, and the checkbox says so by going grey.
function syncGeomNote() {
  const drawn = mapview.hasDrawnShape();
  geomNote.classList.toggle('hidden', !drawn);
  inViewCheckbox.disabled = drawn;
  withinCheckbox.disabled = !drawn;
}

function hereMode() {
  return currentMode() === 'here' && isActive();
}

// A crosshair while a click on the map is a request -- over the result
// layers too, which Leaflet otherwise gives a pointer (devtools.css).
function syncHereCursor() {
  const container = mapview.getMap()?.getContainer();
  if (container) {
    container.style.cursor = hereMode() ? 'crosshair' : '';
    container.classList.toggle('here-mode', hereMode());
  }
}

function onMapClick(event) {
  if (hereMode()) {
    whatsHere(event.latlng);
  }
}

function isActive() {
  return document.querySelector('input[name="tab"]:checked').value === 'search';
}

// /metadata's tree in the picker's shape: one language's name, `subs`.
function pickerTree(nodes, lang) {
  return (nodes || []).map((node) => ({
    id: node.id,
    name: node.names[lang] ?? node.id,
    subs: pickerTree(node.subcategories, lang),
  }));
}

// The categories as a tree, from the same one the importer classified
// with -- so what can be picked here is what rows carry.
async function loadCategories(selected) {
  try {
    const metadata = await api.request('/metadata');
    categoryPicker.load(pickerTree(metadata.categories, lang), selected);
  } catch (error) {
    showError(t('categories_error', { message: error.message }));
  }
}

function syncModeHint() {
  panel.classList.toggle('mode-here', currentMode() === 'here');
  panel.classList.toggle('mode-address', currentMode() === 'address');
  queryHint.textContent = HINTS[currentMode()] ?? '';
  fuzzyCheckbox.disabled = currentMode() !== 'name';
  syncHereCursor();
}

export function init(urlState) {
  registerCollector(() => ({
    smode: currentMode() === 'name' ? '' : currentMode(),
    q: queryInput.value,
    cat: categoryPicker.value,
    geom: mapview.getDrawnWkt(),
    page: state.page > 0 ? state.page : '',
    radius: radiusInput.value.trim(),
    street: addressInputs.street.value,
    hn: addressInputs.housenumber.value,
    pc: addressInputs.postcode.value,
    city: addressInputs.city.value,
    inview: inViewCheckbox.checked ? '1' : '',
    within: withinCheckbox.checked ? '' : '0',
    fuzzy: fuzzyCheckbox.checked ? '1' : '',
    sort: sortSelect.value === 'score' ? '' : sortSelect.value,
    sim: similarityInput.value === similarityInput.dataset.default ? '' : similarityInput.value,
    here: currentMode() === 'here' && state.herePoint
      ? `${state.herePoint.lat.toFixed(6)},${state.herePoint.lng.toFixed(6)}` : '',
  }));

  // Every control is rendered as the URL sets it; what is typed or ticked
  // goes back into the URL, so a reload or a language switch keeps it.
  for (const control of [queryInput, ...Object.values(addressInputs), inViewCheckbox,
    withinCheckbox, fuzzyCheckbox, sortSelect, similarityInput]) {
    control.addEventListener('change', writeStateToUrl);
  }
  for (const radio of modeRadios) {
    radio.addEventListener('change', () => {
      syncModeHint();
      writeStateToUrl();
      if (currentMode() !== 'here' && state.searched && hasQuery()) {
        state.page = 0;
        search();
      }
    });
  }
  radiusInput.addEventListener('change', () => {
    writeStateToUrl();
    if (state.kind === 'here' && state.herePoint) {
      whatsHere(state.herePoint);
    }
  });
  const page = Number(urlState.page);
  state.page = Number.isFinite(page) && page > 0 ? page : 0;

  similarityInput.addEventListener('input', () => {
    similarityValue.textContent = similarityInput.value;
  });
  submitButton.addEventListener('click', () => {
    state.page = 0;
    search({ zoom: true });
  });
  for (const input of [queryInput, ...Object.values(addressInputs)]) {
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        state.page = 0;
        search({ zoom: true });
      }
    });
    input.addEventListener('input', syncClearButton);
  }
  clearButton.addEventListener('click', () => {
    queryInput.value = '';
    for (const input of Object.values(addressInputs)) {
      input.value = '';
    }
    clearResults();
  });
  prevButton.addEventListener('click', () => goToPage(state.page - 1));
  nextButton.addEventListener('click', () => goToPage(state.page + 1));

  // A new or cleared shape changes what the search means -- re-run it, but
  // only once something has been searched for.
  mapview.on('draw', () => {
    syncGeomNote();
    writeStateToUrl();
    if (state.searched) {
      state.page = 0;
      search();
    }
  });
  // A grid change rebuilds the map and drops every layer with it.
  mapview.on('rebuild', () => {
    state.hereMarker = null;
    const map = mapview.getMap();
    map.on('click', onMapClick);
    renderResults();
    syncHereCursor();
  });

  syncModeHint();
  syncClearButton();
  return loadCategories(urlState.cat);
}

// After the map exists: the URL's shape needs a draw layer to live on.
export function applyUrlGeometry(urlState) {
  if (urlState.geom) {
    mapview.setDrawnWkt(urlState.geom);
  }
  syncGeomNote();
}

// The point "what's here" was last asked about, asked again.
export function applyUrlHere(urlState) {
  const [lat, lng] = (urlState.here ?? '').split(',').map(Number);
  if (currentMode() === 'here' && Number.isFinite(lat) && Number.isFinite(lng)) {
    whatsHere(L.latLng(lat, lng));
  }
}

export function onTabShown() {
  syncHereCursor();
}
