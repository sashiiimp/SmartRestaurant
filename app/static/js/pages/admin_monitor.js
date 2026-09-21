SR.createApp({
  data() {
    const end = ui.addDays(ui.todayIso(), -1);
    return { tab: 'sales', from: ui.addDays(end, -27), to: end, groupBy: 'day', sales: null, acc: null, waste: null, loading: false, error: null, ui };
  },
  async mounted() { await this.load(); },
  computed: {
    salesLabels() { return this.sales ? this.sales.rows.map(r => r.period) : []; },
    salesData() { return this.sales ? [{ label: 'Portions sold', data: this.sales.rows.map(r => r.quantity) }] : []; },
    accLabels() { return this.acc && this.acc.series ? this.acc.series.map(r => ui.date(r.date)) : []; },
    accData() { return this.acc && this.acc.series ? [{ label: 'Forecast (all items)', data: this.acc.series.map(r => r.forecast) }, { label: 'Actual (all items)', data: this.acc.series.map(r => r.actual) }] : []; },
    wasteLabels() { return this.waste ? this.waste.food.rows.map(r => r.period) : []; },
    wasteData() { return this.waste ? [{ label: 'Food waste (LKR at selling price)', data: this.waste.food.rows.map(r => r.value) }] : []; },
  },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      const p = { from: this.from, to: this.to };
      try {
        if (this.tab === 'sales') this.sales = (await api.get('/reports/sales', { ...p, group_by: this.groupBy })).data;
        else if (this.tab === 'forecast') this.acc = (await api.get('/forecasts/accuracy', p)).data;
        else this.waste = (await api.get('/reports/waste', { ...p, group_by: this.groupBy })).data;
      } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    setTab(t) { this.tab = t; this.load(); },
  },
}).mount('#app');
