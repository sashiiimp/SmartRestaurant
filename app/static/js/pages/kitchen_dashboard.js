SR.createApp({
  data() { return { date: ui.todayIso(), d: null, alerts: [], requests: null, loading: true, error: null, ui, allAlerts: location.hash === '#alerts' }; },
  async mounted() {
    await this.load();
    // the navbar bell opens /kitchen#alerts: show every open alert and scroll to them once they are drawn
    if (location.hash === '#alerts') this.$nextTick(() => { const el = document.getElementById('alerts'); if (el) el.scrollIntoView({ block: 'start' }); });
  },
  computed: {
    isToday() { return this.date === ui.todayIso(); },
    day() { return this.d.day; },
    // display only: the same figures as the plan table (planned = accepted or changed quantity, else the suggestion)
    approvedPortions() { return this.d.plan.filter(r => ['accepted', 'overridden'].includes(r.status)).reduce((t, r) => t + Number(this.toPrepare(r) || 0), 0); },
    suggestedPortions() { return this.d.plan.filter(r => r.status === 'suggested').reduce((t, r) => t + Number(r.recommended_qty || 0), 0); },
    preparedPct() { const t = this.d && this.d.tiles; return t && Number(t.planned_total) ? Math.min(100, Math.round(Number(t.prepared_total) / Number(t.planned_total) * 100)) : 0; },
    toGo() { return Math.max(0, Number(this.d.tiles.planned_total) - Number(this.day.prepared_total)); },
    preparedHint() {
      const plan = this.day.items_forecast && !this.day.undecided ? 'approved' : 'recommended';
      return this.preparedPct + '% of the ' + plan + ' plan · ' + this.d.tiles.items_done + ' of ' + this.d.plan.length + ' items done';
    },
    isFuture() { return this.date > ui.todayIso(); },
    // shortages: out-of-stock ingredients first (critical), then the rest, each group in the server's order
    shortRows() { return [...this.d.shortages.filter(s => this.isOut(s)), ...this.d.shortages.filter(s => !this.isOut(s))]; },
    shortSummary() {
      const n = this.d.shortages.length, out = this.d.shortages.filter(s => this.isOut(s)).length;
      return n + (n === 1 ? ' ingredient' : ' ingredients') + ' short' + (out ? ' · ' + out + ' out of stock' : '');
    },
    openRequests() { return this.requests ? this.requests.filter(r => r.status === 'pending' || r.status === 'approved').length : 0; },
    // alerts: stock-out alerts about ingredients already in the shortage table repeat it, so the preview shows the others;
    // "Show all" lists every open alert (nothing is changed or hidden for good)
    covered() {
      const short = new Set(this.d.shortages.map(s => s.ingredient_id));
      return this.alerts.filter(a => a.alert_type === 'projected_stockout' && a.entity_type === 'ingredient' && short.has(a.entity_id));
    },
    preview() { const c = new Set(this.covered.map(a => a.id)); return this.alerts.filter(a => !c.has(a.id)).slice(0, 3); },
    // What needs attention for this day, what the system recommends, and the page that handles it. Plain rules over
    // the figures above; nothing is calculated anew. Shortages have their own table with the Request stock action, and
    // items awaiting approval and portions still to prepare are on the two cards (empty list = the section is hidden).
    actions() {
      const d = this.d, x = this.day, out = [], s = (n, one, many) => n + ' ' + (n === 1 ? one : many);
      if (d.plan.length && !x.items_forecast) out.push({ key: 'nofc', tone: 'danger', title: 'No forecast for ' + ui.date(this.date),
        detail: 'The administrator runs the forecast. You can still set quantities by hand.', action: 'Plan & prepare', href: '/kitchen/prep' });
      if (x.pre_orders.pending) out.push({ key: 'po', tone: 'warning', title: s(x.pre_orders.pending, 'pre-order waits', 'pre-orders wait') + ' for confirmation',
        detail: 'Only confirmed pre-orders count in the plan.', action: 'Pre-orders', href: '/kitchen/orders' });
      if (x.served_total === null && x.prepared_total > 0 && this.date <= ui.todayIso()) out.push({ key: 'served', tone: 'info',
        title: 'Served portions not recorded yet', detail: 'After service, record served portions and waste.', action: 'Record served & waste', href: '/kitchen/record' });
      return out;
    },
  },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try { this.d = (await api.get('/dashboards/kitchen', { date: this.date })).data; }
      catch (e) { this.d = null; this.error = ui.errorText(e); } finally { this.loading = false; }
      // After the dashboard (never in parallel) so the alert check runs once.
      if (this.d) { try { this.alerts = (await api.get('/alerts', { status: 'open' })).data; } catch (e) { this.alerts = this.d.alerts; } }
      // open stock requests, so a shortage says whether stock was already asked for (read-only)
      try { this.requests = (await api.get('/kitchen/stock-requests', { status: '' })).data; } catch (e) { this.requests = false; }
    },
    isOut(s) { return Number(s.usable_stock) <= 0; },
    barClass(r) { return r.prep_status === 'done' ? 'bg-success' : (this.decision(r) === 'suggested' ? 'is-suggested' : ''); },
    toPrepare(r) { return r.final_qty === null || r.final_qty === undefined ? r.recommended_qty : r.final_qty; },
    pct(r) { const t = Number(this.toPrepare(r)); return t ? Math.min(100, Math.round(Number(r.prepared) / t * 100)) : (r.prepared > 0 ? 100 : 0); },
    // the decision on an item (recommendations.status) and, once preparation has started, its progress (prep_status)
    decision(r) { return ['accepted', 'overridden'].includes(r.status) ? r.status : (r.status === 'no_forecast' ? 'none' : 'suggested'); },
    state(r) { return r.prep_status === 'done' ? 'done' : (r.prep_status === 'in_progress' ? 'progress' : this.decision(r)); },
    stateLabel(r) { return { done: 'Completed', progress: 'In progress', accepted: 'Accepted', overridden: 'Changed', suggested: 'Suggested', none: 'No forecast' }[this.state(r)]; },
    qtyTitle(r) {
      return { accepted: 'Accepted recommendation', overridden: 'Plan changed from the recommended ' + r.recommended_qty, suggested: 'Suggested, not approved yet', none: '' }[this.decision(r)];
    },
    async ack(a) {
      try { await api.post('/alerts/' + a.id + '/acknowledge'); await this.load(); } catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
  },
}).mount('#app');
