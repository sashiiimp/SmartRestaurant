/* Alert count in the navbar. Silent if the alerts API is unavailable. */
(function () {
  const badge = document.getElementById('alert-count');
  if (!badge || !window.api) return;
  window.api.get('/alerts', { status: 'open' }).then(({ meta }) => {
    const c = (meta && meta.counts) || {};
    const n = (c.critical || 0) + (c.warning || 0) + (c.info || 0);
    badge.textContent = n;
    badge.className = 'badge ' + (c.critical ? 'bg-danger' : n ? 'bg-warning text-dark' : 'bg-secondary');
  }).catch(() => {});
})();
