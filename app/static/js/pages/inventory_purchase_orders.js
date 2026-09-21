SR.createApp({
  data() {
    return { rows: [], suppliers: [], ingredients: [], status: '', loading: true, error: null, form: null, errors: {}, saving: false,
             po: null, recv: null, recvErrors: {}, busy: false, ui };
  },
  computed: {
    canReceive() { return this.po && ['draft', 'sent', 'partially_received'].includes(this.po.status) && this.po.lines.some(l => l.qty_outstanding > 0); },
    canCancel() { return this.po && ['draft', 'sent'].includes(this.po.status) && this.po.lines.every(l => l.qty_received === 0); },
  },
  async mounted() {
    try {
      this.suppliers = (await api.get('/suppliers', { active: true })).data;
      this.ingredients = (await api.get('/ingredients', { active: true })).data;
    } catch (e) { this.error = ui.errorText(e); }
    await this.load();
    const id = new URLSearchParams(location.search).get('open');
    if (id) await this.open(Number(id));
  },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try { this.rows = (await api.get('/purchase-orders', { status: this.status })).data; }
      catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    async open(id) {
      this.recv = null; this.recvErrors = {};
      try { this.po = (await api.get('/purchase-orders/' + id)).data; window.scrollTo({ top: 0, behavior: 'smooth' }); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
    startNew() { this.form = { supplier_id: '', expected_date: '', notes: '', lines: [{ ingredient_id: '', qty_ordered: '', unit_cost: '' }] }; this.errors = {}; },
    async create() {
      this.saving = true; this.errors = {};
      const f = this.form;
      const body = { supplier_id: f.supplier_id, expected_date: f.expected_date || undefined, notes: f.notes || undefined,
        lines: f.lines.map(l => ({ ingredient_id: l.ingredient_id, qty_ordered: l.qty_ordered, unit_cost: l.unit_cost === '' ? undefined : l.unit_cost })) };
      try {
        const { data } = await api.post('/purchase-orders', body);
        ui.toast('Saved ' + data.po_number + ' as a draft.'); this.form = null; await this.load(); this.po = data;
      } catch (e) { this.errors = e.fields || {}; if (!Object.keys(this.errors).length) ui.toast(ui.errorText(e), 'danger'); }
      finally { this.saving = false; }
    },
    async act(path, message) {
      this.busy = true;
      try { this.po = (await api.post('/purchase-orders/' + this.po.id + path)).data; ui.toast(message); await this.load(); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); } finally { this.busy = false; }
    },
    send() { return this.act('/send', this.po.po_number + ' marked as sent.'); },
    cancel() {
      if (!confirm('Cancel ' + this.po.po_number + '?')) return;
      return this.act('/cancel', this.po.po_number + ' cancelled.');
    },
    startReceive() {
      this.recvErrors = {};
      this.recv = { received_date: ui.todayIso(),
        lines: this.po.lines.filter(l => l.qty_outstanding > 0).map(l => ({ line_id: l.id, ingredient: l.ingredient, unit: l.unit, outstanding: l.qty_outstanding,
          quantity: String(l.qty_outstanding), expiry_date: '', batch_no: '', unit_cost: l.unit_cost === null ? '' : String(l.unit_cost) })) };
    },
    async receive() {
      this.busy = true; this.recvErrors = {};
      const lines = this.recv.lines.filter(l => l.quantity !== '' && Number(l.quantity) !== 0).map(l => ({
        line_id: l.line_id, quantity: l.quantity, expiry_date: l.expiry_date || undefined, batch_no: l.batch_no || undefined, unit_cost: l.unit_cost === '' ? undefined : l.unit_cost }));
      // errors are reported against the position in the list that was sent, so map them back to the form rows
      const shown = this.recv.lines.filter(l => l.quantity !== '' && Number(l.quantity) !== 0);
      try {
        const { data } = await api.post('/purchase-orders/' + this.po.id + '/receive', { received_date: this.recv.received_date, lines });
        this.po = data.purchase_order; this.recv = null; ui.toast('Stock received: ' + data.received.length + ' line(s).');
        await this.load();
        api.get('/alerts', { status: 'open', refresh: true }).catch(() => {});
      } catch (e) {
        const out = {};
        Object.entries(e.fields || {}).forEach(([k, v]) => {
          const m = /^lines\[(\d+)\]$/.exec(k);
          if (m) { const row = this.recv.lines.indexOf(shown[Number(m[1])]); out['lines[' + row + ']'] = v; } else out[k] = v;
        });
        this.recvErrors = out; if (!Object.keys(out).length) ui.toast(ui.errorText(e), 'danger');
      } finally { this.busy = false; }
    },
  },
}).mount('#app');
