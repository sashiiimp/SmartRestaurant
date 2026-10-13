// Plain-English names for audit log actions ("promotion.create" -> "Promotion created").
const ACT_NOUN = { history: 'Sales history', sales: 'Sales', model: 'Forecast model', stock_request: 'Stock request', purchase_order: 'Purchase order',
  menu: 'Menu item', user: 'User', settings: 'Settings', restaurant: 'Restaurant details', holidays: 'Holidays', weather: 'Weather data', stock: 'Stock',
  recipe: 'Recipe', preorder: 'Pre-order', order: 'Order', promotion: 'Promotion', ingredient: 'Ingredient', supplier: 'Supplier' };
const ACT_VERB = { create: 'created', update: 'updated', activate: 'activated', train: 'trained', import: 'imported', bulk_load: 'loaded', cancel: 'cancelled',
  receive: 'received', send: 'sent', adjust: 'adjusted', approve: 'approved', reject: 'rejected', issue: 'issued', deactivate: 'deactivated',
  password_reset: 'password reset', role_change: 'role changed' };

// Compact chart axis labels ("Tue 13" for a week, "13 Oct" for a month); the card subtitle gives the full dates.
const shortDate = (iso, weekday) => new Date(iso + 'T00:00:00Z').toLocaleDateString('en-GB', weekday
  ? { weekday: 'short', day: 'numeric', timeZone: 'UTC' } : { day: 'numeric', month: 'short', timeZone: 'UTC' });

SR.createApp({
  data() { return { range: 7, d: null, alerts: [], trend: undefined, perf: null, allActivity: false, allStock: false, loading: true, error: null, ui }; },
  async mounted() { await this.load(); this.loadPerf(); },
  computed: {
    synthetic() { return this.d && /synthetic|demo|simulated/i.test(this.d.data_source || ''); },
    // Food waste rate tile: amber above the waste-risk limit from Settings (the same limit the waste-risk alert uses).
    wasteTone() { const r = this.d.waste_rate.pct; return r === null ? 'neutral' : (r > this.d.waste_threshold_pct ? 'warning' : 'success'); },
    wasteHint() {
      const w = this.d.waste_rate;
      return w.pct === null ? 'nothing prepared in this period' : ui.num(w.wasted, 0) + ' of ' + ui.num(w.prepared, 0) + ' prepared (limit ' + ui.num(this.d.waste_threshold_pct, 1) + '%)';
    },
    stockHint() { const s = this.d.stock; return s.out + ' out of stock, ' + s.low + ' low, of ' + s.ingredients; },
    stockShown() { return this.allStock ? this.d.stock.rows : this.d.stock.rows.slice(0, 6); },
    forecastDays() { return this.d.forecast_next7.filter(f => f.qty !== null).length; },
    forecastLabels() { return this.d.forecast_next7.map(f => shortDate(f.date, true)); },
    // Predictions are drawn in the info blue, recorded history in the green accent, so the two are never confused.
    forecastData() {
      const c = getComputedStyle(document.body).getPropertyValue('--info').trim() || '#175cd3';
      return [{ label: 'Predicted portions', data: this.d.forecast_next7.map(f => f.qty), backgroundColor: c + '59', borderColor: c, borderWidth: 1.5, hoverBackgroundColor: c + '8c' }];
    },
    missingForecastText() { return this.d.forecast_next7.filter(f => f.qty === null).map(f => ui.date(f.date)).join(', '); },
    partialItems() { return this.d.forecast_next7.some(f => f.qty !== null && f.items < this.d.menu_items_active); },
    // Every date of the period on the x axis; a day without records is null (a gap), never a made-up zero.
    trendDates() { const out = []; for (let x = this.d.from; x <= this.d.to; x = ui.addDays(x, 1)) out.push(x); return out; },
    trendLabels() { return this.trendDates.map(x => shortDate(x, this.d.range_days === 7)); },
    trendSeries() {
      if (!this.trend) return null;
      const sold = new Map(this.trend.sales.rows.map(r => [r.period, r.quantity]));
      const waste = new Map(this.trend.waste.food.rows.map(r => [r.period, r.quantity]));
      return { sold: this.trendDates.map(x => sold.has(x) ? sold.get(x) : null),
               wasted: this.trendDates.map(x => waste.has(x) ? waste.get(x) : (sold.has(x) ? 0 : null)) };
    },
    trendHasData() { const s = this.trendSeries; return !!s && (s.sold.some(v => v !== null) || s.wasted.some(v => v !== null)); },
    trendGaps() { return !!this.trendSeries && this.trendSeries.sold.some(v => v === null); },
    trendData() {
      if (!this.trendSeries) return [];
      return [{ label: 'Portions sold (recorded)', data: this.trendSeries.sold },
              { label: 'Portions wasted (recorded)', data: this.trendSeries.wasted, borderColor: '#d97706', backgroundColor: '#d97706' }];
    },
    activityShown() { return this.d ? this.d.recent_activity.slice(0, this.allActivity ? 10 : 5) : []; },
  },
  methods: {
    setRange(n) { if (this.range !== n) { this.range = n; this.load(); } },
    async load() {
      this.loading = true; this.error = null;
      try { this.d = (await api.get('/dashboards/admin', { range: this.range })).data; } catch (e) { this.d = null; this.error = ui.errorText(e); } finally { this.loading = false; }
      this.trend = undefined; this.allStock = false;
      if (this.d) { await this.loadAlerts(); this.loadTrend(); }
    },
    // Loaded after the dashboard (never in parallel) so the alert check runs once.
    async loadAlerts() { try { this.alerts = (await api.get('/alerts', { status: 'open' })).data; } catch (e) { this.alerts = this.d.alerts; } },
    // The trend chart reuses the existing report endpoints; if they fail the cards above still show.
    async loadTrend() {
      const p = { from: this.d.from, to: this.d.to, group_by: 'day' };
      try {
        const [sales, waste] = await Promise.all([api.get('/reports/sales', p), api.get('/reports/waste', p)]);
        this.trend = { sales: sales.data, waste: waste.data };
      } catch (e) { this.trend = null; }
    },
    // Hold-out error of the active model and of the naive baseline, from the stored training metrics.
    async loadPerf() {
      try {
        const rows = (await api.get('/model-versions')).data;
        const active = rows.find(m => m.status === 'active');
        const cmp = active && active.metrics ? active.metrics.comparison : [];
        const model = cmp.find(c => c.model === active.algorithm), base = cmp.find(c => c.model === 'naive_lag7');
        if (model && base && base.mae) this.perf = { model: model.mae, baseline: base.mae, from: active.holdout.start, to: active.holdout.end };
      } catch (e) { this.perf = null; }
    },
    algoName(a) { return { xgboost: 'XGBoost', random_forest: 'Random forest', naive_lag7: 'Same day last week', seasonal_mean4: '4-week average' }[a] || a; },
    activityText(action) {
      const [noun, verb] = String(action).split('.');
      return (ACT_NOUN[noun] || noun.replace(/_/g, ' ')) + ' ' + (ACT_VERB[verb] || (verb || '').replace(/_/g, ' '));
    },
    async ack(a) { try { await api.post('/alerts/' + a.id + '/acknowledge'); await this.load(); } catch (e) { ui.toast(ui.errorText(e), 'danger'); } },
  },
}).mount('#app');
