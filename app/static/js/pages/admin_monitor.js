SR.createApp({
  data() {
    const end = ui.addDays(ui.todayIso(), -1);
    return {
      tab: 'sales', from: ui.addDays(end, -27), to: end, groupBy: 'day', itemId: '', ingId: '', mtype: '', demandStart: ui.todayIso(),
      tabs: [['sales', 'Sales and revenue'], ['demand', 'Demand forecast'], ['forecast', 'Forecast accuracy'], ['inventory', 'Inventory'], ['movements', 'Stock movements'], ['waste', 'Waste']],
      items: [], ingredients: [], sales: null, acc: null, waste: null, trend: null, moves: null, demand: { rows: [], meta: {} },
      loading: false, error: null, ui,
    };
  },
  async mounted() {
    try {
      this.items = (await api.get('/menu-items', { active: true })).data;
      this.ingredients = (await api.get('/ingredients', { active: true })).data;
      if (this.ingredients.length) this.ingId = this.ingredients[0].id;
    } catch (e) { this.error = ui.errorText(e); }
    await this.load();
  },
  computed: {
    csvUrl() {
      const range = '&from=' + this.from + '&to=' + this.to;
      if (this.tab === 'forecast') return '/api/v1/forecasts/accuracy?format=csv' + range + (this.itemId ? '&item_id=' + this.itemId : '');
      if (this.tab === 'inventory') return '/api/v1/reports/inventory-trend?format=csv' + range + '&ingredient_id=' + this.ingId;
      if (this.tab === 'movements') return '/api/v1/reports/movements?format=csv' + range + (this.ingId ? '&ingredient_id=' + this.ingId : '') + (this.mtype ? '&type=' + this.mtype : '');
      const base = { sales: '/api/v1/reports/sales', waste: '/api/v1/reports/waste' }[this.tab];
      return base + '?format=csv' + range + '&group_by=' + this.groupBy;
    },
    salesLabels() { return this.sales ? this.sales.rows.map(r => r.period) : []; },
    salesData() { return this.sales ? [{ label: 'Portions sold', data: this.sales.rows.map(r => r.quantity) }] : []; },
    accLabels() { return this.acc && this.acc.series ? this.acc.series.map(r => ui.date(r.date)) : []; },
    accData() { return this.acc && this.acc.series ? [{ label: 'Forecast' + (this.itemId ? '' : ' (all items)'), data: this.acc.series.map(r => r.forecast) }, { label: 'Actual' + (this.itemId ? '' : ' (all items)'), data: this.acc.series.map(r => r.actual) }] : []; },
    wasteLabels() { return this.waste ? this.waste.food.rows.map(r => r.period) : []; },
    wasteData() { return this.waste ? [{ label: 'Food waste (LKR at selling price)', data: this.waste.food.rows.map(r => r.value) }] : []; },
    trendData() { return this.trend ? [{ label: 'Closing stock', data: this.trend.rows.map(r => r.closing) }] : []; },
    demandDates() { return Array.from({ length: 7 }, (_, i) => ui.addDays(this.demandStart, i)); },
    demandTable() {
      const seen = new Map();
      this.demand.rows.forEach(r => seen.set(r.menu_item_id, r.item));
      return [...seen].map(([id, name]) => {
        const cells = this.demandDates.map(d => this.demand.rows.find(r => r.menu_item_id === id && r.date === d) || null);
        return { id, name, cells, total: cells.reduce((a, c) => a + (c ? c.predicted_qty : 0), 0) };
      });
    },
    demandDayTotals() { return this.demandDates.map((d, i) => this.demandTable.reduce((a, t) => a + (t.cells[i] ? t.cells[i].predicted_qty : 0), 0)); },
    demandGrand() { return this.demandDayTotals.reduce((a, v) => a + v, 0); },
    demandChart() { return [{ label: 'Forecast (portions, all items)', data: this.demandDayTotals }]; },
  },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      const p = { from: this.from, to: this.to };
      try {
        if (this.tab === 'sales') this.sales = (await api.get('/reports/sales', { ...p, group_by: this.groupBy })).data;
        else if (this.tab === 'demand') { const r = await api.get('/forecasts', { from: this.demandStart, to: ui.addDays(this.demandStart, 6) }); this.demand = { rows: r.data, meta: r.meta }; }
        else if (this.tab === 'forecast') this.acc = (await api.get('/forecasts/accuracy', { ...p, item_id: this.itemId })).data;
        else if (this.tab === 'inventory') this.trend = this.ingId ? (await api.get('/reports/inventory-trend', { ...p, ingredient_id: this.ingId })).data : null;
        else if (this.tab === 'movements') { const r = await api.get('/reports/movements', { ...p, ingredient_id: this.ingId, type: this.mtype }); this.moves = { data: r.data, meta: r.meta }; }
        else this.waste = (await api.get('/reports/waste', { ...p, group_by: this.groupBy })).data;
      } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    setTab(t) {
      this.tab = t;
      // stock movements are recorded up to today, so these two tabs include today by default
      if ((t === 'inventory' || t === 'movements') && this.to < ui.todayIso()) this.to = ui.todayIso();
      if (t === 'movements') this.ingId = '';
      if (t === 'inventory' && !this.ingId && this.ingredients.length) this.ingId = this.ingredients[0].id;
      this.load();
    },
  },
}).mount('#app');
