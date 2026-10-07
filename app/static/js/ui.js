/* Display formatting and small helpers. All formatting lives here, never in services. */
// The server's business date can be fixed for a demo (SMARTREST_TODAY). Pages follow it by keeping the offset between
// the server's date at page load and the browser's Colombo date, so a real-time server still rolls over at midnight.
const SR_DAY_OFFSET = (() => {
  const m = document.querySelector('meta[name="business-today"]');
  const local = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Colombo' });
  return m && m.content ? Math.round((Date.parse(m.content) - Date.parse(local)) / 86400000) : 0;
})();

window.ui = {
  todayIso() {
    const d = new Date(new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Colombo' }) + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() + SR_DAY_OFFSET);
    return d.toISOString().slice(0, 10);
  },
  addDays(iso, n) { const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); },
  date(iso) {
    if (!iso) return '';
    return new Date(iso + 'T00:00:00Z').toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' });
  },
  dateTime(iso) { return iso ? new Date(iso).toLocaleString('en-GB', { timeZone: 'Asia/Colombo', dateStyle: 'medium', timeStyle: 'short' }) : ''; },
  money(n) { return n === null || n === undefined ? '' : 'LKR ' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); },
  num(n, digits = 1) { return n === null || n === undefined ? '' : Number(n).toLocaleString('en-US', { maximumFractionDigits: digits }); },
  qty(n, unit) { return n === null || n === undefined ? '' : Number(n).toLocaleString('en-US', { maximumFractionDigits: 3 }) + (unit ? ' ' + unit : ''); },
  toast(message, type = 'success') {
    let box = document.getElementById('toast-box');
    if (!box) {
      box = document.createElement('div');
      box.id = 'toast-box'; box.className = 'toast-container position-fixed bottom-0 end-0 p-3'; box.style.zIndex = 2000;
      document.body.appendChild(box);
    }
    const el = document.createElement('div');
    el.className = 'toast align-items-center text-bg-' + type + ' border-0'; el.setAttribute('role', 'status');
    const inner = document.createElement('div'); inner.className = 'd-flex';
    const body = document.createElement('div'); body.className = 'toast-body'; body.textContent = message;
    inner.appendChild(body); el.appendChild(inner); box.appendChild(el);
    const t = new bootstrap.Toast(el, { delay: type === 'success' ? 2500 : 6000 }); t.show();
    el.addEventListener('hidden.bs.toast', () => el.remove());
  },
  errorText(e) { return (e && e.message) || 'Something went wrong. Please try again.'; },
};
