// WKT <-> Leaflet, for the one thing the search tab needs it for: putting a
// drawn shape in the URL and getting it back.
//
// Hand-rolled rather than pulled from a CDN because the surface actually in
// use is three geometry types and one direction each. The server speaks
// WKT (it goes straight into ST_GeomFromText, see search.py), so WKT is
// also what the URL carries -- one spelling end to end, no conversion step
// that could disagree with itself.

// Coordinates are written lon/lat, which is WKT/PostGIS axis order and the
// opposite of Leaflet's LatLng. Every conversion below flips deliberately;
// getting this backwards puts Duesseldorf in Somalia.

// ~0.1 m at this latitude. Enough that a redrawn shape is visually
// identical, short enough that a 64-point circle still makes a sane URL.
const PRECISION = 6;

function num(value) {
  // toFixed then Number: trims 51.230000 to 51.23 without leaving the
  // 17-digit float spellings that make a URL unreadable.
  return String(Number(value.toFixed(PRECISION)));
}

function ring(latlngs) {
  const points = latlngs.map((p) => `${num(p.lng)} ${num(p.lat)}`);
  // A WKT ring must close; Leaflet's polygon rings do not repeat the first
  // point, so it is appended here.
  if (points.length > 0 && points[0] !== points[points.length - 1]) {
    points.push(points[0]);
  }
  return points.join(', ');
}

// How many points approximate a drawn circle. WKT has no circle, so one is
// emitted as a polygon -- 64 segments keeps the visible error under a pixel
// at the zoom levels a circle gets drawn at, without bloating the URL.
const CIRCLE_SEGMENTS = 64;

// Mean Earth radius (IUGG), matching what Leaflet's own distance math uses.
const EARTH_RADIUS_M = 6371008.8;

// Destination point given a start, a bearing and a distance along a great
// circle. Used only to trace a circle's outline -- at the radii a hand-drawn
// circle has, a cheaper flat-earth approximation would also do, but this one
// does not degrade near the poles and is no harder to read.
function destination(center, bearingRad, distanceM) {
  const angular = distanceM / EARTH_RADIUS_M;
  const lat1 = (center.lat * Math.PI) / 180;
  const lon1 = (center.lng * Math.PI) / 180;
  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(angular)
    + Math.cos(lat1) * Math.sin(angular) * Math.cos(bearingRad)
  );
  const lon2 = lon1 + Math.atan2(
    Math.sin(bearingRad) * Math.sin(angular) * Math.cos(lat1),
    Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2)
  );
  return { lat: (lat2 * 180) / Math.PI, lng: (lon2 * 180) / Math.PI };
}

// A Leaflet layer -> WKT, or null for a layer shape we don't emit.
//
// Circle is checked before the generic cases because L.Circle has getLatLng
// like a marker does, and would otherwise serialize as a POINT -- losing the
// radius, i.e. the entire shape the user drew.
export function layerToWkt(layer) {
  if (layer instanceof L.Circle) {
    const center = layer.getLatLng();
    const radius = layer.getRadius();
    const points = [];
    for (let i = 0; i < CIRCLE_SEGMENTS; i++) {
      const bearing = (2 * Math.PI * i) / CIRCLE_SEGMENTS;
      points.push(destination(center, bearing, radius));
    }
    return `POLYGON((${ring(points)}))`;
  }
  if (layer instanceof L.Polygon) {
    // Outer ring only. leaflet-draw cannot produce a hole, so a second ring
    // here would be unreachable code guarding against nothing.
    const latlngs = layer.getLatLngs()[0];
    return `POLYGON((${ring(latlngs)}))`;
  }
  if (layer instanceof L.Polyline) {
    // After L.Polygon, which extends L.Polyline -- the order matters.
    const points = layer.getLatLngs().map((p) => `${num(p.lng)} ${num(p.lat)}`);
    return `LINESTRING(${points.join(', ')})`;
  }
  if (layer.getLatLng) {
    const p = layer.getLatLng();
    return `POINT(${num(p.lng)} ${num(p.lat)})`;
  }
  return null;
}

function parseCoords(body) {
  return body
    .split(',')
    .map((pair) => pair.trim().split(/\s+/).map(Number))
    .filter(([lon, lat]) => Number.isFinite(lon) && Number.isFinite(lat))
    // Back to Leaflet order.
    .map(([lon, lat]) => [lat, lon]);
}

// WKT -> a Leaflet layer, or null if it isn't one of the three types this
// page can draw. Callers treat null as "no shape", never as an error: a URL
// is user-editable, and a malformed one should open the page rather than
// break it.
export function wktToLayer(wkt) {
  if (!wkt) {
    return null;
  }
  const text = wkt.trim();
  const match = /^(POINT|LINESTRING|POLYGON)\s*\((.*)\)$/is.exec(text);
  if (!match) {
    return null;
  }
  const [, type, rawBody] = match;
  const kind = type.toUpperCase();
  try {
    if (kind === 'POLYGON') {
      // Strip the inner parens around the ring list, then keep the outer ring.
      const inner = rawBody.trim().replace(/^\(/, '').replace(/\)$/, '');
      const points = parseCoords(inner.split(/\)\s*,\s*\(/)[0]);
      return points.length >= 3 ? L.polygon(points) : null;
    }
    if (kind === 'LINESTRING') {
      const points = parseCoords(rawBody);
      return points.length >= 2 ? L.polyline(points) : null;
    }
    const points = parseCoords(rawBody);
    return points.length >= 1 ? L.marker(points[0]) : null;
  } catch (err) {
    return null;
  }
}
