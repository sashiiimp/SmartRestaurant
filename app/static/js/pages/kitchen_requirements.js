SR.createApp({
  data() { return { date: ui.todayIso(), r: null, ask: null, note: '', busy: false, loading: true, error: null, ui }; },
  computed: {
    shortCount() { return this.r ? this.r.ingredients.filter(i => i.status === 'short').length : 0; },
    // short ingredients first, otherwise the order the service returns
    sortedIngredients() { return this.r ? [...this.r.ingredients].sort((a, b) => (b.status === 'short') - (a.status === 'short')) : []; },
  },
  async mounted() { await this.load(); },
  methods: {
    toggle(i) { this.ask = this.ask === i.ingredient_id ? null : i.ingredient_id; this.note = ''; },
    async report(i) {
      this.busy = true;
      try {
        const { data } = await api.post('/kitchen/shortage-reports', { ingredient_id: i.ingredient_id, note: this.note });
        ui.toast(data.created ? 'Shortage reported to Inventory.' : 'The open shortage report was updated.');
        this.ask = null; this.note = '';
      } catch (e) { ui.toast(ui.errorText(e), 'danger'); } finally { this.busy = false; }
    },
    async load() {
      this.loading = true; this.error = null; this.ask = null;
      try { this.r = (await api.get('/recommendations/requirements', { date: this.date })).data; }
      catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
  },
}).mount('#app');
