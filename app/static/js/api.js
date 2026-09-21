/* Thin fetch wrapper for /api/v1: CSRF header, envelope unwrapping, field errors (UI_PLAN section 2). */
window.api = (function () {
  function csrf() {
    const m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.content : '';
  }
  function qs(params) {
    if (!params) return '';
    const p = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') p.append(k, v); });
    const s = p.toString();
    return s ? '?' + s : '';
  }
  async function call(method, path, body, params) {
    const headers = { Accept: 'application/json' };
    let payload;
    if (body instanceof FormData) payload = body;
    else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
    if (method !== 'GET') headers['X-CSRFToken'] = csrf();
    let resp;
    try {
      resp = await fetch('/api/v1' + path + qs(params), { method, headers, body: payload, credentials: 'same-origin' });
    } catch (e) {
      throw { code: 'network_error', message: 'Cannot reach the server. Check your connection and try again.', fields: {} };
    }
    if (resp.status === 401) { window.location = '/login'; throw { code: 'unauthenticated', message: 'Please log in.', fields: {} }; }
    let json = null;
    try { json = await resp.json(); } catch (e) { /* not JSON */ }
    if (!resp.ok) {
      const err = (json && json.error) || { code: 'server_error', message: 'Something went wrong. Please try again.' };
      err.status = resp.status; err.fields = err.fields || {};
      throw err;
    }
    return json || { data: null, meta: {} };
  }
  return {
    get: (path, params) => call('GET', path, undefined, params),
    post: (path, body) => call('POST', path, body === undefined ? {} : body),
    put: (path, body) => call('PUT', path, body),
    patch: (path, body) => call('PATCH', path, body),
    delete: (path) => call('DELETE', path),
  };
})();
