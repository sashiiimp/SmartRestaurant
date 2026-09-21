SR.createApp({
  data() {
    return { tab: 'stock', tabs: [['stock', 'Stock levels'], ['demand', 'Ingredient demand'], ['batches', 'Batches and expiry'], ['movements', 'Recent movements']],
             levels: [], counts: { ok: 0, low: 0, out: 0 }, demand: null, batches: [], moves: [], movementTotal: 0, ing: '', type: '', loading: true, error: null, ui };
  },
  computed: { days() { return this.demand ? Array.from({ length: this.demand.days }, (_, i) => ui.addDays(this.demand.from, i)) : []; } },
  async mounted() { await this.load(); },
  methods: {
    setTab(t) { this.tab = t; this.load(); },
    async load() {
      this.loading = true; this.error = null;
      try {
        if (this.tab === 'stock' || this.tab === 'movements') {
          const r = await api.get('/stock/levels'); this.levels = r.data; this.counts = r.meta.counts;
        }
        if (this.tab === 'demand') this.demand = (await api.get('/recommendations/ingredient-forecast', { from: ui.todayIso(), days: 7 })).data;
        if (this.tab === 'batches') this.batches = (await api.get('/stock/batches')).data;
        if (this.tab === 'movements') {
          const r = await api.get('/stock/movements', { ingredient_id: this.ing, type: this.type, limit: 50 });
          this.moves = r.data; this.movementTotal = r.meta.total;
        }
      } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
  },
}).mount('#app');
