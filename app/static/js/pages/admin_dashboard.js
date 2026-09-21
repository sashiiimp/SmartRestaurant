SR.createApp({
  data() { return { range: 7, d: null, trend: undefined, loading: true, error: null, running: false, ui }; },
  async mounted() { await this.load(); },
  computed: {
    trendLabels() { return this.trend ? this.trend.sales.rows.map(r => r.period.slice(5)) : []; },
    trendData() {
      if (!this.trend) return [];
      const waste = new Map(this.trend.waste.food.rows.map(r => [r.period, r.quantity]));
      return [{ label: 'Portions sold', data: this.trend.sales.rows.map(r => r.quantity) },
              { label: 'Portions wasted', data: this.trend.sales.rows.map(r => waste.get(r.period) || 0) }];
    },
    alertTotal() { return this.d ? this.d.alert_counts.critical + this.d.alert_counts.warning + (this.d.alert_counts.info || 0) : 0; },
  },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try { this.d = (await api.get('/dashboards/admin', { range: this.range })).data; } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
      this.trend = undefined;
      if (this.d) this.loadTrend();
    },
    // The trend chart reuses the existing report endpoints; if they fail the cards above still show.
    async loadTrend() {
      const p = { from: this.d.from, to: this.d.to, group_by: 'day' };
      try {
        const [sales, waste] = await Promise.all([api.get('/reports/sales', p), api.get('/reports/waste', p)]);
        this.trend = { sales: sales.data, waste: waste.data };
      } catch (e) { this.trend = null; }
    },
    async runAlerts() {
      this.running = true;
      try { const { data } = await api.post('/alerts/run'); ui.toast('Alerts checked: ' + data.opened + ' opened, ' + data.closed + ' cleared.'); await this.load(); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); } finally { this.running = false; }
    },
    async ack(a) { try { await api.post('/alerts/' + a.id + '/acknowledge'); await this.load(); } catch (e) { ui.toast(ui.errorText(e), 'danger'); } },
  },
}).mount('#app');
