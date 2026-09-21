SR.createApp({
  data() {
    return { start: ui.todayIso(), rows: [], meta: {}, loading: true, error: null, itemId: '', ui };
  },
  computed: {
    dates() { return Array.from({ length: 7 }, (_, i) => ui.addDays(this.start, i)); },
    items() {
      const seen = new Map();
      this.rows.forEach(r => seen.set(r.menu_item_id, r.item));
      return [...seen].map(([id, name]) => ({ id, name }));
    },
    table() {
      return this.items.map(it => {
        const cells = this.dates.map(d => this.rows.find(r => r.menu_item_id === it.id && r.date === d) || null);
        return { ...it, cells };
      });
    },
    chartItem() { return this.itemId || (this.items[0] && this.items[0].id); },
    chartData() {
      const cells = (this.table.find(t => t.id === this.chartItem) || { cells: [] }).cells;
      return [{ label: 'Forecast (portions)', data: cells.map(c => c ? c.predicted_qty : null) }];
    },
  },
  async mounted() { await this.load(); },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try {
        const { data, meta } = await api.get('/forecasts', { from: this.start, to: ui.addDays(this.start, 6) });
        this.rows = data; this.meta = meta;
        if (!this.itemId && data.length) this.itemId = data[0].menu_item_id;  // show the first item in the chart selector
      } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
  },
}).mount('#app');
