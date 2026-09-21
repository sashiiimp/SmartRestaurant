SR.createApp({
  data() { return { tab: 'sales', promos: [], items: [], loading: true, error: null, form: null, errors: {}, saving: false, ui }; },
  async mounted() {
    try { this.items = (await api.get('/menu-items', { active: true })).data; await this.load(); } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
  },
  methods: {
    async load() { this.promos = (await api.get('/promotions')).data; },
    add() { this.form = { name: '', start_date: ui.todayIso(), end_date: ui.addDays(ui.todayIso(), 6), discount_pct: 10, applies_to_all: false, item_ids: [] }; this.errors = {}; },
    async save() {
      this.saving = true; this.errors = {};
      try { await api.post('/promotions', this.form); ui.toast('Promotion saved. Run a new forecast to include it.'); this.form = null; await this.load(); }
      catch (e) { this.errors = e.fields || {}; if (!Object.keys(this.errors).length) ui.toast(ui.errorText(e), 'danger'); } finally { this.saving = false; }
    },
    async toggle(p) { try { await api.patch('/promotions/' + p.id, { is_active: !p.is_active }); await this.load(); } catch (e) { ui.toast(ui.errorText(e), 'danger'); } },
    names(p) { return p.applies_to_all ? 'All items' : p.item_ids.map(i => (this.items.find(x => x.id === i) || {}).name || i).join(', '); },
  },
}).mount('#app');
