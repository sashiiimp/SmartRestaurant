SR.createApp({
  data() { return { date: ui.todayIso(), d: null, loading: true, error: null, ui }; },
  async mounted() { await this.load(); },
  computed: {
    planLabels() { return this.d ? this.d.plan.map(r => r.name) : []; },
    planChart() {
      if (!this.d) return [];
      return [{ label: 'Forecast', data: this.d.plan.map(r => Number(r.forecast_qty) || 0), backgroundColor: '#cbd5e1' },
              { label: 'Recommended', data: this.d.plan.map(r => Number(r.recommended_qty) || 0) },
              { label: 'Prepared', data: this.d.plan.map(r => Number(r.prepared) || 0), backgroundColor: '#2f9e6b' }];
    },
    preparedPct() { const t = this.d && this.d.tiles; return t && Number(t.planned_total) ? Math.round(Number(t.prepared_total) / Number(t.planned_total) * 100) : 0; },
  },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try { this.d = (await api.get('/dashboards/kitchen', { date: this.date })).data; }
      catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    async ack(a) {
      try { await api.post('/alerts/' + a.id + '/acknowledge'); await this.load(); } catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
  },
}).mount('#app');
