SR.createApp({
  data() {
    const t = ui.todayIso();
    return { today: t, from: t, to: ui.addDays(t, 13), status: '', items: [], rows: [], loading: true, error: null, notice: null, form: null, errors: {}, saving: false, ui };
  },
  async mounted() {
    try { this.items = (await api.get('/menu-items', { active: true })).data; } catch (e) { this.error = ui.errorText(e); }
    await this.load();
  },
  methods: {
    editable(r) { return r.status !== 'cancelled' && r.target_date >= this.today; },
    async load() {
      this.loading = true; this.error = null;
      try { this.rows = (await api.get('/kitchen/pre-orders', { from: this.from, to: this.to, status: this.status })).data; }
      catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    startNew() { this.form = { id: null, menu_item_id: '', target_date: ui.addDays(this.today, 1), quantity: '', customer_note: '', status: 'pending' }; this.errors = {}; },
    edit(r) { this.form = { id: r.id, menu_item_id: r.menu_item_id, target_date: r.target_date, quantity: r.quantity, customer_note: r.customer_note || '', status: r.status }; this.errors = {}; },
    warn(meta) { this.notice = meta && meta.warnings && meta.warnings.length ? meta.warnings[0] : null; },
    async save() {
      this.saving = true; this.errors = {}; this.notice = null;
      const f = this.form;
      try {
        const r = f.id
          ? await api.patch('/kitchen/pre-orders/' + f.id, { target_date: f.target_date, quantity: f.quantity, customer_note: f.customer_note })
          : await api.post('/kitchen/pre-orders', { menu_item_id: f.menu_item_id, target_date: f.target_date, quantity: f.quantity, customer_note: f.customer_note, status: f.status });
        ui.toast('Pre-order saved.'); this.warn(r.meta); this.form = null; await this.load();
      } catch (e) { this.errors = e.fields || {}; if (!Object.keys(this.errors).length) ui.toast(ui.errorText(e), 'danger'); }
      finally { this.saving = false; }
    },
    async setStatus(r, status) {
      if (status === 'cancelled' && !confirm('Cancel this pre-order for ' + r.item + '?')) return;
      this.notice = null;
      try { const res = await api.patch('/kitchen/pre-orders/' + r.id, { status }); this.warn(res.meta); ui.toast('Pre-order ' + status + '.'); await this.load(); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
  },
}).mount('#app');
