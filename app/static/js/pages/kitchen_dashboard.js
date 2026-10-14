SR.createApp({
  data() { return { date: ui.todayIso(), d: null, alerts: [], requests: null, loading: true, error: null, ui }; },
  async mounted() { await this.load(); },
  computed: {
    isToday() { return this.date === ui.todayIso(); },
    day() { return this.d.day; },
    preparedPct() { const t = this.d && this.d.tiles; return t && Number(t.planned_total) ? Math.min(100, Math.round(Number(t.prepared_total) / Number(t.planned_total) * 100)) : 0; },
    servedHint() {
      const x = this.day;
      if (x.served_total !== null) return 'portions served / wasted';
      return x.wasted_total ? x.wasted_total + ' portions wasted so far' : 'record after service';
    },
    openRequests() { return this.requests ? this.requests.filter(r => r.status === 'pending' || r.status === 'approved').length : 0; },
    // What needs attention for this day, what the system recommends, and the page that handles it. Plain rules over
    // the figures above; nothing is calculated anew.
    actions() {
      const d = this.d, x = this.day, out = [], s = (n, one, many) => n + ' ' + (n === 1 ? one : many);
      if (d.plan.length && !x.items_forecast) out.push({ key: 'nofc', tone: 'danger', title: 'No forecast for ' + ui.date(this.date),
        detail: 'The administrator runs the forecast. You can still set quantities by hand.', action: 'Plan & prepare', href: '/kitchen/prep' });
      if (x.undecided) out.push({ key: 'decide', tone: 'warning', title: s(x.undecided, 'item needs', 'items need') + ' a preparation decision',
        detail: 'Accept the recommended quantity or change it.', action: 'Decide quantities', href: '/kitchen/prep' });
      if (d.shortages.length) out.push({ key: 'short', tone: 'danger', title: s(d.shortages.length, 'ingredient is', 'ingredients are') + ' short for this plan',
        detail: this.openRequests ? 'Request the missing quantity. ' + s(this.openRequests, 'request is', 'requests are') + ' already open.' : 'Request the missing quantity from inventory.',
        action: 'Request stock', href: '/kitchen/requirements?tab=requests' });
      if (x.pre_orders.pending) out.push({ key: 'po', tone: 'warning', title: s(x.pre_orders.pending, 'pre-order waits', 'pre-orders wait') + ' for confirmation',
        detail: 'Only confirmed pre-orders count in the plan.', action: 'Pre-orders', href: '/kitchen/orders' });
      const left = Number(d.tiles.planned_total) - Number(x.prepared_total);
      if (!x.undecided && x.items_forecast && left > 0 && this.date <= ui.todayIso()) out.push({ key: 'prep', tone: 'info',
        title: ui.num(left, 0) + ' portions still to prepare', detail: 'Record prepared portions as you go.', action: 'Plan & prepare', href: '/kitchen/prep' });
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
    toPrepare(r) { return r.final_qty === null || r.final_qty === undefined ? r.recommended_qty : r.final_qty; },
    pct(r) { const t = Number(this.toPrepare(r)); return t ? Math.min(100, Math.round(Number(r.prepared) / t * 100)) : (r.prepared > 0 ? 100 : 0); },
    async ack(a) {
      try { await api.post('/alerts/' + a.id + '/acknowledge'); await this.load(); } catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
  },
}).mount('#app');
