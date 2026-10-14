SR.createApp({
  data() {
    const end = ui.addDays(ui.todayIso(), -1);
    return {
      tab: 'sales', from: ui.addDays(end, -27), to: end, groupBy: 'day', itemId: '', ingId: '', mtype: '', demandStart: ui.todayIso(),
      tabs: [['sales', 'Sales and revenue'], ['demand', 'Demand forecast'], ['forecast', 'Forecast accuracy'], ['analytics', 'Analytics'], ['waste', 'Waste reports'],
             ['stock', 'Stock levels'], ['ingredients', 'Ingredient demand'], ['batches', 'Batches and expiry'], ['inventory', 'Stock trends'], ['movements', 'Stock movements']],
      // the 10 reports under 4 headings: the heading bar picks a group, the underlined tabs pick a report inside it
      groups: [['sales', 'Sales', ['sales'], 'Step 1, historical sales: portions sold and revenue, the data the forecast learns from.'],
               ['forecasting', 'Forecasting', ['demand', 'forecast'], 'Step 2, ML demand forecast: what the model predicts, and how close earlier forecasts came to what was sold.'],
               ['inventory', 'Inventory', ['stock', 'ingredients', 'batches', 'inventory', 'movements'], 'Steps 4 and 5, ingredients and inventory: needs from the recipes, stock now, expiry and every movement.'],
               ['waste', 'Waste & Analytics', ['waste', 'analytics'], 'Step 6, food waste monitoring: prepared food and ingredients wasted, plus patterns by weekday, holiday and promotion.']],
      shortGroup: { 'Public holiday': 'Public', 'Poya day': 'Poya', 'School holiday': 'School', 'Ordinary day': 'Ordinary', 'Promotion running': 'Promotion', 'No promotion': 'No promo' },
      items: [], ingredients: [], levels: [], counts: { ok: 0, low: 0, out: 0 }, ingDemand: null, batches: [], sales: null, acc: null, waste: null, usage: null, trend: null, moves: null, an: null, demand: { rows: [], meta: {} },
      loading: false, error: null, ui,
    };
  },
  async mounted() {
    try {
      this.items = (await api.get('/menu-items', { active: true })).data;
      this.ingredients = (await api.get('/ingredients', { active: true })).data;
      if (this.ingredients.length) this.ingId = this.ingredients[0].id;
    } catch (e) { this.error = ui.errorText(e); }
    // ?tab= opens a tab directly (the old Inventory overview address sends admins to ?tab=stock)
    const start = new URLSearchParams(location.search).get('tab');
    if (start && this.tabs.some(t => t[0] === start)) this.setTab(start); else await this.load();
  },
  computed: {
    // tabs that show stock as it is now, so the date filters do not apply
    snapshot() { return ['stock', 'ingredients', 'batches'].includes(this.tab); },
    group() { return this.groups.find(g => g[2].includes(this.tab)) || this.groups[0]; },
    subTabs() { return this.group[2].map(k => this.tabs.find(t => t[0] === k)); },
    ingDays() { return this.ingDemand ? Array.from({ length: this.ingDemand.days }, (_, i) => ui.addDays(this.ingDemand.from, i)) : []; },
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
        return { id, name, cells, total: cells.reduce((a, c) => a + (c ? c.predicted_qty : 0), 0), partial: cells.some(c => !c) };
      });
    },
    // null for a day without any forecast, so the table shows "-" and the chart a gap instead of a false 0
    demandDayTotals() { return this.demandDates.map((d, i) => this.demandTable.some(t => t.cells[i]) ? this.demandTable.reduce((a, t) => a + (t.cells[i] ? t.cells[i].predicted_qty : 0), 0) : null); },
    demandGrand() { return this.demandDayTotals.reduce((a, v) => a + (v || 0), 0); },
    // days of the window that have a forecast for at least one item; a total over fewer than 7 days is labelled partial
    demandDaysCovered() { return this.demandDayTotals.filter(v => v !== null).length; },
    demandTotalLabel() { const n = this.demandDaysCovered; return n === 7 ? '7-day total' : n + '-day total (partial)'; },
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
        else if (this.tab === 'stock') { const r = await api.get('/stock/levels'); this.levels = r.data; this.counts = r.meta.counts; }
        else if (this.tab === 'ingredients') this.ingDemand = (await api.get('/recommendations/ingredient-forecast', { from: ui.todayIso(), days: 7 })).data;
        else if (this.tab === 'batches') this.batches = (await api.get('/stock/batches')).data;
        else if (this.tab === 'analytics') this.an = (await api.get('/reports/analytics', p)).data;
        else if (this.tab === 'inventory') this.trend = this.ingId ? (await api.get('/reports/inventory-trend', { ...p, ingredient_id: this.ingId })).data : null;
        else if (this.tab === 'movements') { const r = await api.get('/reports/movements', { ...p, ingredient_id: this.ingId, type: this.mtype }); this.moves = { data: r.data, meta: r.meta }; }
        else {
          this.waste = (await api.get('/reports/waste', { ...p, group_by: this.groupBy })).data;
          this.usage = (await api.get('/reports/food-usage', p)).data;
        }
      } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    setTab(t) {
      this.tab = t;
      try { history.replaceState(null, '', '?tab=' + t); } catch (e) { /* the tab still works without the address */ }
      // stock movements are recorded up to today, so these two tabs include today by default
      if ((t === 'inventory' || t === 'movements') && this.to < ui.todayIso()) this.to = ui.todayIso();
      if (t === 'movements') this.ingId = '';
      // analytics needs a longer window than the other tabs to say anything about weekdays and holidays
      if (t === 'analytics' && (new Date(this.to) - new Date(this.from)) / 86400000 < 60) this.from = ui.addDays(this.to, -89);
      if (t === 'inventory' && !this.ingId && this.ingredients.length) this.ingId = this.ingredients[0].id;
      this.load();
    },
  },
}).mount('#app');
