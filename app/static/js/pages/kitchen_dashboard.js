SR.createApp({
  data() { return { date: ui.todayIso(), d: null, alerts: [], day: null, requests: null, loading: true, error: null, ui }; },
  async mounted() { await this.load(); },
  computed: {
    isToday() { return this.date === ui.todayIso(); },
    forecastCount() { return this.d ? this.d.plan.filter(r => r.status !== 'no_forecast').length : 0; },
    decidedCount() { return this.d ? this.d.plan.filter(r => r.status === 'accepted' || r.status === 'overridden').length : 0; },
    // a step is done when everything in it is done; the first step that is not done is the current one
    stepsDone() {
      if (!this.d) return [false, false, false, false];
      const f = this.d.plan.length > 0 && this.forecastCount === this.d.plan.length;
      const p = this.forecastCount > 0 && this.decidedCount === this.forecastCount;
      return [f, p, p && this.preparedPct >= 100, false];
    },
    chain() {
      const d = this.d, t = d.tiles, n = v => ui.num(v, 0), sum = (k) => this.day ? this.day.items.reduce((a, i) => a + Number(i[k] || 0), 0) : null;
      const fc = d.plan.filter(r => r.status !== 'no_forecast').reduce((a, r) => a + Number(r.forecast_qty || 0), 0);
      const open = this.requests ? this.requests.filter(r => r.status === 'pending' || r.status === 'approved').length : null;
      const served = sum('served'), wasted = sum('wasted');
      return [
        { title: 'Historical sales', value: served === null ? '-' : n(served) + ' served', mine: true, href: '/kitchen/record',
          caption: 'recorded today', owner: 'Kitchen records · admin imports' },
        { title: 'ML demand forecast', value: this.forecastCount ? n(fc) + ' portions' : 'No forecast', mine: true, href: '/kitchen/prep?tab=forecast',
          tone: this.forecastCount ? 'info' : 'warning', caption: this.forecastCount + '/' + d.plan.length + ' items', owner: 'ML model, runs daily' },
        { title: 'Preparation recommendations', value: this.decidedCount + '/' + this.forecastCount + ' decided', mine: true, href: '/kitchen/prep',
          progress: this.preparedPct, caption: this.preparedPct + '% prepared', owner: 'Kitchen accepts or overrides' },
        { title: 'BOM & ingredient requirements', value: t.shortage_count ? t.shortage_count + ' short' : 'All covered', mine: true, href: '/kitchen/requirements',
          tone: t.shortage_count ? 'danger' : 'success', caption: 'plan x recipes', owner: 'Kitchen checks' },
        { title: 'Inventory decisions', value: open === null ? '-' : (open ? open + ' open' : 'None open'), mine: true, href: '/kitchen/requirements?tab=requests',
          caption: 'stock requests', owner: 'Inventory manager issues' },
        { title: 'Food waste monitoring', value: wasted === null ? '-' : n(wasted) + ' wasted', mine: true, href: '/kitchen/record#waste',
          tone: wasted ? 'warning' : null, caption: 'recorded today', owner: 'Kitchen records' },
      ];
    },
    preparedPct() { const t = this.d && this.d.tiles; return t && Number(t.planned_total) ? Math.min(100, Math.round(Number(t.prepared_total) / Number(t.planned_total) * 100)) : 0; },
  },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try { this.d = (await api.get('/dashboards/kitchen', { date: this.date })).data; }
      catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
      // After the dashboard (never in parallel) so the alert check runs once.
      if (this.d) { try { this.alerts = (await api.get('/alerts', { status: 'open' })).data; } catch (e) { this.alerts = this.d.alerts; } }
      // served / waste so far and open stock requests, for the workflow strip (read-only)
      try { this.day = (await api.get('/kitchen/daily-summary', { date: this.date })).data; } catch (e) { this.day = false; }
      try { this.requests = (await api.get('/kitchen/stock-requests', { status: '' })).data; } catch (e) { this.requests = false; }
    },
    stepClass(i) { const done = this.stepsDone; return { 'is-done': done[i], 'is-current': !done[i] && done.slice(0, i).every(Boolean) }; },
    toPrepare(r) { return r.final_qty === null || r.final_qty === undefined ? r.recommended_qty : r.final_qty; },
    pct(r) { const t = Number(this.toPrepare(r)); return t ? Math.min(100, Math.round(Number(r.prepared) / t * 100)) : (r.prepared > 0 ? 100 : 0); },
    async ack(a) {
      try { await api.post('/alerts/' + a.id + '/acknowledge'); await this.load(); } catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
  },
}).mount('#app');
