// The one place the page talks to the server's public API.
//
// The key the viewer types is kept in *their* browser's localStorage and
// nowhere else -- not in the page source, and not in the shareable URL. Requests carry it as
// Authorization: Bearer; tile URLs, which an <img> fetches and so cannot carry a
// header, get it as ?key=, which is exactly the case that carrier exists
// for. On a server with no keys configured the field stays empty and
// nothing is sent.

const STORAGE_KEY = 'gbd-devtools-key';

export function getKey() {
  try {
    return localStorage.getItem(STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

export function setKey(value) {
  try {
    if (value) {
      localStorage.setItem(STORAGE_KEY, value);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // Private windows can refuse storage; the key then lasts the session.
  }
}

// `?key=` for a tile template, or '' when there is none.
export function keyParam(separator) {
  const key = getKey();
  return key ? `${separator}key=${encodeURIComponent(key)}` : '';
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail);
    this.status = status;
  }
}

// JSON in, JSON out. A non-2xx answer becomes an ApiError carrying the
// server's own `detail`, which is written to say what was wrong.
export async function request(path, { method = 'GET', body = null } = {}) {
  const headers = {};
  const key = getKey();
  if (key) {
    headers['Authorization'] = `Bearer ${key}`;
  }
  if (body !== null) {
    headers['Content-Type'] = 'application/json';
  }
  const response = await fetch(path, {
    method,
    headers,
    body: body === null ? null : JSON.stringify(body),
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    let detail = payload && payload.detail ? payload.detail : response.statusText;
    if (typeof detail !== 'string') {
      detail = JSON.stringify(detail);
    }
    throw new ApiError(response.status, detail);
  }
  return payload;
}
