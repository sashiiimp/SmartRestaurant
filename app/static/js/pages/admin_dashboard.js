// Plain-English names for audit log actions ("promotion.create" -> "Promotion created").
const ACT_NOUN = { history: 'Sales history', sales: 'Sales', model: 'Forecast model', stock_request: 'Stock request', purchase_order: 'Purchase order',
  menu: 'Menu item', user: 'User', settings: 'Settings', restaurant: 'Restaurant details', holidays: 'Holidays', weather: 'Weather data', stock: 'Stock',
  recipe: 'Recipe', preorder: 'Pre-order', order: 'Order', promotion: 'Promotion', ingredient: 'Ingredient', supplier: 'Supplier' };
const ACT_VERB = { create: 'created', update: 'updated', activate: 'activated', train: 'trained', import: 'imported', bulk_load: 'loaded', cancel: 'cancelled',
  receive: 'received', send: 'sent', adjust: 'adjusted', approve: 'approved', reject: 'rejected', issue: 'issued', deactivate: 'deactivated',
  password_reset: 'password reset', role_change: 'role changed' };

SR.createApp({
  data() { return { range: 7, d: null, alerts: [], trend: undefined, perf: null, allActivity: false, loading: true, error: null, ui }; },
  async mounted() { await this.load(); this.loadPerf(); },
  computed: {
    trendLabels() { return this.trend ? this.trend.sales.rows.map(r => ui.date(r.period)) : []; },
    trendData() {
      if (!this.trend) return [];
      const waste = new Map(this.trend.waste.food.rows.map(r => [r.period, r.quantity]));
      return [{ label: 'Portions sold', data: this.trend.sales.rows.map(r => r.quantity) },
              { label: 'Portions wasted', data: this.trend.sales.rows.map(r => waste.get(r.period) || 0) }];
    },
    activityShown() { return this.d ? this.d.recent_activity.slice(0, this.allActivity ? 10 : 5) : []; },
  },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try { this.d = (await api.get('/dashboards/admin', { range: this.range })).data; } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
      this.trend = undefined;
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
        if (model && base && base.mae) this.perf = { model: model.mae, baseline: base.mae, better: Math.round((1 - model.mae / base.mae) * 100), from: active.holdout.start, to: active.holdout.end };
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
