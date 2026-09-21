SR.createApp({
  data() { return { rows: [], status: '', loading: true, error: null, req: null, issue: null, rejecting: false, reason: '', errors: {}, busy: false, ui }; },
  computed: { open() { return this.req && ['pending', 'approved'].includes(this.req.status); } },
  async mounted() {
    await this.load();
    const id = new URLSearchParams(location.search).get('open');
    if (id) await this.openReq(Number(id));
  },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try { this.rows = (await api.get('/stock-requests', { status: this.status })).data; }
      catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    async openReq(id) {
      this.issue = null; this.rejecting = false; this.errors = {};
      try { this.req = (await api.get('/stock-requests/' + id)).data; window.scrollTo({ top: 0, behavior: 'smooth' }); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
    async act(path, body, message) {
      this.busy = true; this.errors = {};
      try { const r = await api.post('/stock-requests/' + this.req.id + path, body); this.req = r.data.stock_request || r.data; ui.toast(message); await this.load(); return true; }
      catch (e) { this.errors = e.fields || {}; if (!Object.keys(this.errors).length) ui.toast(ui.errorText(e), 'danger'); await this.load(); return false; }
      finally { this.busy = false; }
    },
    approve() { return this.act('/approve', undefined, 'Request approved.'); },
    async reject() { if (await this.act('/reject', { reason: this.reason }, 'Request rejected.')) { this.rejecting = false; this.reason = ''; } },
    startIssue() {
      this.errors = {};
      this.issue = { close: false, lines: this.req.lines.filter(l => l.qty_outstanding > 0).map(l => ({
        line_id: l.id, ingredient: l.ingredient, unit: l.unit, outstanding: l.qty_outstanding, usable: l.usable_stock,
        quantity: String(Math.min(l.qty_outstanding, l.usable_stock || 0) || '') })) };
    },
    async doIssue() {
      const shown = this.issue.lines.filter(l => l.quantity !== '' && Number(l.quantity) !== 0);
      const lines = shown.map(l => ({ line_id: l.line_id, quantity: l.quantity }));
      this.busy = true; this.errors = {};
      try {
        const r = await api.post('/stock-requests/' + this.req.id + '/issue', { lines, close: this.issue.close });
        this.req = r.data.stock_request; this.issue = null; ui.toast('Stock issued.'); await this.load();
        api.get('/alerts', { status: 'open', refresh: true }).catch(() => {});
      } catch (e) {
        const out = {};
        Object.entries(e.fields || {}).forEach(([k, v]) => {
          const m = /^lines\[(\d+)\]$/.exec(k);
          if (m) out['lines[' + this.issue.lines.indexOf(shown[Number(m[1])]) + ']'] = v; else out[k] = v;
        });
        this.errors = out; if (!Object.keys(out).length) ui.toast(ui.errorText(e), 'danger');
      } finally { this.busy = false; }
    },
  },
}).mount('#app');
