SR.createApp({
  data() {
    return {
      date: ui.todayIso(), items: [], loading: true, error: null, ui,
      served: {}, savingServed: false, servedErrors: {}, conflicts: null, servedMessages: [],
      waste: { menu_item_id: '', quantity: '', reason: 'overproduction', note: '' }, wasteErrors: {}, savingWaste: false,
      usage: null, use: {}, usageErrors: {}, allIngredients: [], otherIng: '',
    };
  },
  async mounted() {
    try { this.allIngredients = (await api.get('/ingredients', { active: true })).data; } catch (e) { /* the rest of the page still works */ }
    await this.load();
  },
  computed: {
    otherIngredients() { const shown = new Set(this.usage ? this.usage.rows.map(r => r.ingredient_id) : []); return this.allIngredients.filter(g => !shown.has(g.id)); },
  },
  methods: {
    async load() {
      this.loading = true; this.error = null; this.conflicts = null; this.servedMessages = [];
      try {
        const { data } = await api.get('/kitchen/daily-summary', { date: this.date });
        this.items = data.items;
        this.served = {};
        data.items.forEach(i => { this.served[i.menu_item_id] = i.served === null || i.served === undefined ? '' : String(i.served); });
        if (!this.waste.menu_item_id && data.items.length) this.waste.menu_item_id = data.items[0].menu_item_id;
      } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
      await this.loadUsage();
    },
    async loadUsage() {
      try {
        const u = (await api.get('/kitchen/ingredient-usage', { date: this.date })).data;
        this.use = {}; this.usageErrors = {};
        u.rows.forEach(r => { this.use[r.ingredient_id] = { quantity: r.recorded === null ? '' : String(r.recorded), note: r.note || '' }; });
        this.usage = u;
      } catch (e) { this.usage = null; ui.toast(ui.errorText(e), 'danger'); }
    },
    addOther() {
      const g = this.allIngredients.find(x => x.id === this.otherIng); if (!g) return;
      this.use[g.id] = { quantity: '', note: '' };
      this.usage.rows.push({ ingredient_id: g.id, ingredient: g.name, unit: g.unit, expected: 0, recorded: null, variance: null, note: null, usage_id: null });
      this.otherIng = '';
    },
    async saveUsage(r) {
      const f = this.use[r.ingredient_id]; this.usageErrors[r.ingredient_id] = '';
      if (f.quantity === '') { this.usageErrors[r.ingredient_id] = 'Enter the amount used.'; return; }
      try { await api.post('/kitchen/ingredient-usage', { date: this.date, ingredient_id: r.ingredient_id, quantity: f.quantity, note: f.note || undefined }); ui.toast(r.ingredient + ': usage recorded.'); await this.loadUsage(); }
      catch (e) { this.usageErrors[r.ingredient_id] = Object.values(e.fields || {}).join('; ') || ui.errorText(e); }
    },
    async clearUsage(r) {
      try { await api.delete('/kitchen/ingredient-usage/' + r.usage_id); ui.toast(r.ingredient + ': back to the expected usage.'); await this.loadUsage(); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
    async saveServed(confirm) {
      this.savingServed = true; this.servedErrors = {}; this.servedMessages = [];
      const lines = this.items.filter(i => this.served[i.menu_item_id] !== '').map(i => ({ menu_item_id: i.menu_item_id, quantity: this.served[i.menu_item_id] }));
      try {
        const { data } = await api.post('/sales/served', { date: this.date, lines, confirm_overwrite: !!confirm });
        this.conflicts = null; this.servedMessages = data.warnings;
        ui.toast('Served quantities saved (' + data.saved + ' changed).');
        await this.load(); this.servedMessages = data.warnings;
      } catch (e) {
        if (e.code === 'duplicate_record') this.conflicts = e.conflicts || [];
        else { this.servedErrors = e.fields || {}; this.servedMessages = [ui.errorText(e)]; }
      } finally { this.savingServed = false; }
    },
    async saveWaste() {
      this.savingWaste = true; this.wasteErrors = {};
      try {
        const { data } = await api.post('/kitchen/waste', { date: this.date, ...this.waste });
        ui.toast('Waste recorded (' + data.total_waste + ' today).');
        if (data.warnings.length) ui.toast(data.warnings[0], 'warning');
        this.waste.quantity = ''; this.waste.note = '';
        await this.load();
      } catch (e) { this.wasteErrors = e.fields || {}; if (!Object.keys(this.wasteErrors).length) ui.toast(ui.errorText(e), 'danger'); }
      finally { this.savingWaste = false; }
    },
  },
}).mount('#app');
