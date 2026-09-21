const BLANK = { id: null, name: '', unit: 'kg', category: '', shelf_life_days: '', default_supplier_id: '', min_stock: 0, reorder_level: 0, pack_size: 1, reorder_qty: 0 };
SR.createApp({
  data() { return { rows: [], suppliers: [], filter: '', status: '', loading: true, error: null, form: null, errors: {}, saving: false, check: null, checking: false, ui }; },
  computed: {
    // inactive suppliers cannot be newly chosen, but the one already on the ingredient stays visible
    supplierOptions() { return this.suppliers.filter(s => s.is_active || (this.form && s.id === this.form.default_supplier_id)); },
    shown() {
      const f = this.filter.toLowerCase();
      return this.rows.filter(r => (!f || r.name.toLowerCase().includes(f)) && (!this.status || r.status === this.status));
    },
  },
  async mounted() { await this.load(); this.suppliers = (await api.get('/suppliers')).data; },
  methods: {
    async runCheck() {
      this.checking = true;
      try { this.check = (await api.get('/stock/consistency')).data; } catch (e) { ui.toast(ui.errorText(e), 'danger'); } finally { this.checking = false; }
    },
    async load() {
      this.loading = true; this.error = null;
      try { this.rows = (await api.get('/stock/levels')).data; } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    add() { this.form = { ...BLANK }; this.errors = {}; },
    edit(r) { this.form = { ...r, default_supplier_id: r.default_supplier_id || '', shelf_life_days: r.shelf_life_days || '' }; this.errors = {}; },
    async save() {
      this.saving = true; this.errors = {};
      const f = this.form;
      const body = { name: f.name, unit: f.unit, category: f.category, shelf_life_days: f.shelf_life_days, default_supplier_id: f.default_supplier_id,
        min_stock: f.min_stock, reorder_level: f.reorder_level, pack_size: f.pack_size, reorder_qty: f.reorder_qty };
      try {
        if (f.id) await api.patch('/ingredients/' + f.id, body); else await api.post('/ingredients', body);
        ui.toast('Ingredient saved.'); this.form = null; await this.load();
      } catch (e) { this.errors = e.fields || {}; if (!Object.keys(this.errors).length) ui.toast(ui.errorText(e), 'danger'); }
      finally { this.saving = false; }
    },
  },
}).mount('#app');
