// Compact chart axis labels ("Tue 13" for a week, "13 Oct" for a month); the card subtitle gives the full dates.
const shortDate = (iso, weekday) => new Date(iso + 'T00:00:00Z').toLocaleDateString('en-GB', weekday
  ? { weekday: 'short', day: 'numeric', timeZone: 'UTC' } : { day: 'numeric', month: 'short', timeZone: 'UTC' });

// One plain sentence per stored event (dashboard_service.recent_activity). Unknown actions fall back to their name.
const DAY = (iso) => iso ? ui.date(iso) : '';
const ACTIVITY = {
  'forecast.run': (e, x) => x.status === 'ok' || x.status === 'partial'
    ? 'Forecast generated for ' + x.days + ' days (' + DAY(x.from) + ' to ' + DAY(x.to) + '), ' + x.items + ' menu items' + (x.status === 'partial' ? ', partly' : '')
    : 'Forecast run ' + x.status + ' for ' + DAY(x.from),
  'recommendation.accept': (e, x) => 'Prep plan accepted for ' + e.name + ': ' + x.final + ' portions on ' + DAY(x.date),
  'recommendation.override': (e, x) => 'Prep plan changed for ' + e.name + ': ' + x.final + ' portions on ' + DAY(x.date) + ' (system suggested ' + x.recommended + ')',
  'prep.start': (e, x) => 'Preparation started for ' + e.name + ' (' + DAY(x.date) + ')',
  'prep.done': (e, x) => 'Preparation finished for ' + e.name + ': ' + x.prepared + ' portions',
  'prep.reopen': (e) => 'Preparation reopened for ' + e.name,
  'prepared.record': (e, x) => 'Food preparation recorded for ' + (x.item || e.name) + ': ' + x.quantity + ' portions',
  'waste.record': (e, x) => 'Food waste recorded for ' + (x.item || e.name) + ': ' + x.quantity + ' portions (' + String(x.reason || '').replace(/_/g, ' ') + ')',
  'sales.served': (e, x) => 'Served portions recorded for ' + DAY(x.date) + ' (' + x.lines + ' items)',
  'preorder.create': (e, x) => 'Pre-order #' + e.entity_id + ' created: ' + x.quantity + ' x ' + x.item + ' for ' + DAY(x.date),
  'preorder.confirm': (e, x) => 'Pre-order #' + e.entity_id + ' confirmed: ' + x.quantity + ' x ' + x.item,
  'preorder.complete': (e, x) => 'Pre-order #' + e.entity_id + ' completed (handed over)',
  'preorder.cancel': (e) => 'Pre-order #' + e.entity_id + ' cancelled',
  'preorder.hold': (e) => 'Pre-order #' + e.entity_id + ' put back on hold',
  'preorder.update': (e) => 'Pre-order #' + e.entity_id + ' updated',
  'stock.stock_in': (e, x) => 'Stock received: ' + ui.qty(x.quantity, x.unit) + ' of ' + e.name,
  'stock.stock_out': (e, x) => 'Stock issued: ' + ui.qty(-x.quantity, x.unit) + ' of ' + e.name,
  'stock.wastage': (e, x) => 'Ingredient wastage recorded: ' + ui.qty(-x.quantity, x.unit) + ' of ' + e.name,
  'stock.adjustment': (e, x) => 'Stock corrected for ' + e.name + ' (' + (x.quantity > 0 ? '+' : '') + ui.qty(x.quantity, x.unit) + ')',
  'stock.adjust': (e) => 'Stock corrected for ' + e.name,
  'shortage.report': (e) => 'Kitchen reported a shortage of ' + e.name,
  'model.train': () => 'Forecast model trained', 'model.activate': () => 'Forecast model activated',
  'recipe.update': (e) => 'Recipe (BOM) updated for ' + e.name, 'menu.create': (e) => 'Menu item added: ' + e.name,
  'menu.update': (e) => 'Menu item updated: ' + e.name, 'menu.availability': (e) => 'Availability changed for ' + e.name,
  'ingredient.create': (e) => 'Ingredient added: ' + e.name, 'ingredient.update': (e) => 'Ingredient updated: ' + e.name,
  'sales.import': () => 'Sales history imported', 'history.bulk_load': () => 'Kitchen history loaded',
  'holidays.import': () => 'Holiday calendar imported', 'weather.import': () => 'Weather data imported',
  'promotion.create': () => 'Promotion created', 'settings.update': () => 'Settings changed', 'restaurant.update': () => 'Restaurant details updated',
  'purchase_order.create': () => 'Purchase order created', 'purchase_order.send': () => 'Purchase order sent',
  'purchase_order.receive': () => 'Purchase order received', 'purchase_order.cancel': () => 'Purchase order cancelled',
  'stock_request.create': () => 'Kitchen stock request created', 'stock_request.approve': () => 'Kitchen stock request approved',
  'stock_request.issue': () => 'Kitchen stock request issued', 'stock_request.reject': () => 'Kitchen stock request rejected',
  'stock_request.cancel': () => 'Kitchen stock request cancelled', 'order.create': () => 'Daily order recorded', 'order.update': () => 'Daily order updated',
  'food_usage.record': (e) => 'Staff meal or sample recorded for ' + e.name, 'food_usage.clear': (e) => 'Food use entry removed for ' + e.name,
  'usage.record': (e) => 'Ingredient use recorded for ' + e.name, 'usage.clear': (e) => 'Ingredient use entry removed for ' + e.name,
  'supplier.create': () => 'Supplier added', 'supplier.update': () => 'Supplier updated',
  'user.create': () => 'User account created', 'user.password_reset': () => 'User password reset', 'user.role_change': () => 'User role changed',
  'user.activate': () => 'User account activated', 'user.deactivate': () => 'User account deactivated', 'user.rename': () => 'User renamed',
};
function describe(raw) {
  const e = { ...raw, name: raw.name || 'an item' }, f = ACTIVITY[e.action];
  try { if (f) return f(e, e.detail || {}); } catch (err) { /* missing detail on an older entry: fall back below */ }
  return String(e.action).replace(/[._]/g, ' ').replace(/^./, c => c.toUpperCase());
}

SR.createApp({
  data() { return { range: 7, d: null, alerts: [], history: undefined, alertTab: 'open', trend: undefined, perf: null, prep: null, req: null, reorder: null, allActivity: false, allStock: false, loading: true, error: null, ui }; },
  async mounted() { await this.load(); this.loadPerf(); },
  computed: {
    synthetic() { return this.d && /synthetic|demo|simulated/i.test(this.d.data_source || ''); },
    // Food waste rate tile: amber above the waste-risk limit from Settings (the same limit the waste-risk alert uses).
    wasteTone() { const r = this.d.waste_rate.pct; return r === null ? 'neutral' : (r > this.d.waste_threshold_pct ? 'warning' : 'success'); },
    wasteHint() {
      const w = this.d.waste_rate;
      return w.pct === null ? 'nothing prepared in this period'
        : ui.num(this.d.waste.quantity, 0) + ' portions wasted of ' + ui.num(w.prepared, 0) + ' prepared · ' + ui.money(this.d.waste.value) + ' at selling price · limit ' + ui.num(this.d.waste_threshold_pct, 1) + '%';
    },
    stockHint() { const s = this.d.stock; return s.out + ' out of stock, ' + s.low + ' low, of ' + s.ingredients + ' ingredients'; },
    // Recommended actions: plain rules over figures the dashboard already has; each links to the page that handles it.
    actions() {
      const d = this.d, out = [], names = rows => rows.slice(0, 4).map(r => r.name).join(', ') + (rows.length > 4 ? ' and ' + (rows.length - 4) + ' more' : '');
      if (!d.active_model) out.push({ key: 'model', tone: 'danger', icon: 'layers', title: 'No active forecasting model', detail: 'Train a model and activate it before forecasting.', href: '/admin/models?tab=models', link: 'ML models' });
      if (this.forecastDays < 7) out.push({ key: 'fc', tone: 'warning', icon: 'trending', title: 'Run the forecast', detail: 'No forecast yet for ' + this.missingForecastText + '.', href: '/admin/models?tab=runs', link: 'Forecasting' });
      const low = d.inventory_alerts.filter(r => r.status !== 'ok');
      if (low.length) out.push({ key: 'low', tone: d.stock.out ? 'danger' : 'warning', icon: 'package', title: low.length + ' ingredient' + (low.length === 1 ? ' needs' : 's need') + ' reordering', detail: names(low) + '. Reordering is done by the Inventory & Procurement Manager.', href: '/admin/monitor?tab=stock', link: 'Stock levels' });
      const short = d.inventory_alerts.filter(r => r.forecast);
      if (short.length) out.push({ key: 'short', tone: 'info', icon: 'bars', title: short.length + ' ingredient' + (short.length === 1 ? '' : 's') + ' will run short within 7 days', detail: 'From the forecast and recipes: ' + names(short) + '.', href: '/admin/monitor?tab=ingredients', link: 'Ingredient demand' });
      const expired = d.inventory_alerts.reduce((n, r) => n + r.expiry.filter(e => e.expired).length, 0);
      if (expired) out.push({ key: 'exp', tone: 'danger', icon: 'clock', title: expired + ' expired batch' + (expired === 1 ? '' : 'es') + ' still in stock', detail: 'They should be recorded as inventory wastage.', href: '/admin/monitor?tab=batches', link: 'Batches' });
      const w = d.waste_rate.pct;
      if (w !== null && w > d.waste_threshold_pct) out.push({ key: 'waste', tone: 'warning', icon: 'trash', title: 'Food waste ' + ui.num(w, 1) + '% is above the ' + ui.num(d.waste_threshold_pct, 1) + '% limit', detail: 'Check which items are wasted most.', href: '/admin/monitor?tab=waste', link: 'Waste report' });
      if (d.items_without_recipe.length) out.push({ key: 'bom', tone: 'warning', icon: 'book', title: 'Menu items without a recipe', detail: d.items_without_recipe.join(', ') + ': their ingredient needs count as zero.', href: '/admin/catalog', link: 'Add recipes' });
      if (d.pre_orders.count) out.push({ key: 'po', tone: 'info', icon: 'bag', title: d.pre_orders.count + ' confirmed pre-order' + (d.pre_orders.count === 1 ? '' : 's') + ', ' + d.pre_orders.portions + ' portions', detail: 'In the next 7 days. Already included in the kitchen prep plan.', href: null });
      if (w !== null && w <= d.waste_threshold_pct) out.push({ key: 'wasteok', tone: 'success', icon: 'check', title: 'Food waste ' + ui.num(w, 1) + '% is within the ' + ui.num(d.waste_threshold_pct, 1) + '% limit', detail: 'For the reporting period.', href: '/admin/monitor?tab=waste', link: 'Waste report' });
      if (!out.length) out.push({ key: 'ok', tone: 'success', icon: 'check', title: 'Nothing needs attention', detail: 'Stock, forecast and waste are within their limits.', href: null });
      return out;
    },
    forecastShortCount() { return this.d.inventory_alerts.filter(r => r.forecast).length; },
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
    // Consecutive identical events (same action, record and details) are shown once with a count, never dropped.
    activity() {
      const out = [];
      for (const e of (this.d ? this.d.recent_activity : [])) {
        const key = e.action + '|' + e.entity_id + '|' + JSON.stringify(e.detail) + '|' + e.user;
        const last = out[out.length - 1];
        if (last && last.key === key) { last.times += 1; continue; }
        out.push({ ...e, key, times: 1, text: describe(e) });
      }
      return out;
    },
    // The six steps with today's figures (all values come from the endpoints above; nothing is calculated anew)
    chain() {
      const d = this.d, n = v => ui.num(v, 0), wait = 'loading';
      const items = this.prep ? this.prep.items.filter(i => i.status !== 'no_forecast') : [];
      const decided = items.filter(i => i.status === 'accepted' || i.status === 'overridden').length;
      const toMake = items.reduce((t, i) => t + Number(i.final_qty ?? i.recommended_qty ?? 0), 0);
      const short = this.req ? this.req.ingredients.filter(i => i.status === 'short').length : null;
      const w = d.waste_rate.pct, cov = d.coverage;
      return [
        { title: 'Historical sales', value: n(d.sales.quantity) + ' sold', mine: true, href: '/admin/monitor?tab=sales',
          caption: ui.money(d.sales.revenue) + ' · ' + cov.days_with_sales + ' of ' + cov.days + ' days recorded', owner: 'Admin imports · kitchen records' },
        { title: 'ML demand forecast', value: this.forecastDays ? n(d.forecast_next7_total) + ' portions' : 'No forecast', mine: true, href: '/admin/models?tab=models',
          tone: this.forecastDays < 7 ? 'warning' : 'info',
          caption: 'next 7 days' + (this.perf ? ' · ' + this.algoName(d.active_model.algorithm) + ' MAE ' + ui.num(this.perf.model, 1) + ' vs ' + ui.num(this.perf.baseline, 1) + ' baseline' : ''), owner: 'Admin trains · runs daily' },
        { title: 'Preparation recommendations', value: this.prep ? n(toMake) + ' to prepare' : (this.prep === false ? '-' : wait), mine: false, href: null,
          caption: this.prep ? 'today, forecast + ' + this.prep.buffer_pct + '% buffer in whole batches · ' + decided + ' of ' + items.length + ' decided' : 'today', owner: 'Kitchen accepts or overrides' },
        { title: 'BOM & ingredient requirements', value: short === null ? (this.req === false ? '-' : wait) : (short ? short + ' short' : 'All covered'), mine: true, href: '/admin/catalog',
          tone: short ? 'danger' : (short === 0 ? 'success' : null),
          caption: "today's plan x recipes" + (d.items_without_recipe.length ? ' · ' + d.items_without_recipe.length + ' items lack a recipe' : ''), owner: 'Admin keeps the recipes' },
        { title: 'Inventory decisions', value: this.reorder ? (this.reorder.length ? this.reorder.length + ' to reorder' : 'Nothing to order') : (this.reorder === false ? '-' : wait), mine: true, href: '/admin/monitor?tab=stock',
          tone: d.stock.out ? 'danger' : (d.stock.low ? 'warning' : 'success'),
          caption: d.stock.out + ' out of stock · ' + d.stock.low + ' low · of ' + d.stock.ingredients, owner: 'Inventory manager orders' },
        { title: 'Food waste monitoring', value: w === null ? 'No data' : ui.num(w, 1) + '% wasted', mine: true, href: '/admin/monitor?tab=waste', tone: this.wasteTone,
          caption: n(d.waste.quantity) + ' portions · ' + ui.money(d.waste.value) + ' · limit ' + ui.num(d.waste_threshold_pct, 0) + '%', owner: 'Kitchen records · admin reviews' },
      ];
    },
    // Last 7 recorded days, then the 7 forecast days, on one axis: history as a line, prediction as bars.
    hfDays() { return this.trendDates.slice(-7); },
    hfLabels() { return [...this.hfDays.map(x => shortDate(x, true)), ...this.forecastLabels]; },
    hfData() {
      const c = getComputedStyle(document.body).getPropertyValue('--info').trim() || '#175cd3';
      const sold = this.trendSeries ? this.trendSeries.sold.slice(-7) : this.hfDays.map(() => null);
      return [
        { type: 'line', label: 'Recorded sales (history)', data: [...sold, ...Array(7).fill(null)], borderColor: '#047857', backgroundColor: '#047857', borderWidth: 2.5, tension: 0.3, pointRadius: 3, pointBackgroundColor: '#fff', pointBorderWidth: 2, order: 0 },
        { type: 'bar', label: 'ML forecast (prediction)', data: [...Array(7).fill(null), ...this.d.forecast_next7.map(f => f.qty)], backgroundColor: c + '59', borderColor: c, borderWidth: 1.5, order: 1 },
      ];
    },
    activityShown() { return this.activity.slice(0, this.allActivity ? 10 : 5); },
  },
  methods: {
    shortDate(iso) { return shortDate(iso, false); },
    setRange(n) { if (this.range !== n) { this.range = n; this.load(); } },
    async load() {
      this.loading = true; this.error = null;
      try { this.d = (await api.get('/dashboards/admin', { range: this.range })).data; } catch (e) { this.d = null; this.error = ui.errorText(e); } finally { this.loading = false; }
      this.trend = undefined; this.allStock = false; this.history = undefined; this.alertTab = 'open';
      if (this.d) { await this.loadAlerts(); this.loadTrend(); this.loadChain(); }
    },
    // Loaded after the dashboard (never in parallel) so the alert check runs once.
    async loadAlerts() { try { this.alerts = (await api.get('/alerts', { status: 'open' })).data; } catch (e) { this.alerts = this.d.alerts; } },
    // Today's prep plan, ingredient requirements and reorder suggestions for the workflow strip (read-only; the
    // administrator may read them). Loaded one after another, after the dashboard; a failure only blanks that step.
    async loadChain() {
      const day = ui.todayIso();
      try { this.prep = (await api.get('/recommendations/prep', { date: day })).data; } catch (e) { this.prep = false; }
      try { this.req = (await api.get('/recommendations/requirements', { date: day })).data; } catch (e) { this.req = false; }
      try { this.reorder = (await api.get('/recommendations/reorder')).data; } catch (e) { this.reorder = false; }
    },
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
        if (model && base && base.mae) this.perf = { model: model.mae, baseline: base.mae, wape: model.wape, from: active.holdout.start, to: active.holdout.end };
      } catch (e) { this.perf = null; }
    },
    async showHistory() {
      this.alertTab = 'history';
      if (this.history !== undefined) return;
      try { this.history = (await api.get('/alerts', { status: 'closed' })).data.sort((x, y) => (y.closed_at || '').localeCompare(x.closed_at || '')); }
      catch (e) { this.history = null; }
    },
    closedText(a) {
      const why = { cleared: 'condition no longer true', restocked: 'restocked' }[a.closed_reason] || a.closed_reason || 'closed';
      return 'Opened ' + ui.dateTime(a.created_at) + ' · closed ' + ui.dateTime(a.closed_at) + ' (' + why + ')';
    },
    algoName(a) { return { xgboost: 'XGBoost', random_forest: 'Random forest', naive_lag7: 'Same day last week', seasonal_mean4: '4-week average' }[a] || a; },
    async ack(a) { try { await api.post('/alerts/' + a.id + '/acknowledge'); await this.load(); } catch (e) { ui.toast(ui.errorText(e), 'danger'); } },
  },
}).mount('#app');
