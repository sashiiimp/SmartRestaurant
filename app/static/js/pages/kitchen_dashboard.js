SR.createApp({
  data() { return { date: ui.todayIso(), d: null, alerts: [], loading: true, error: null, ui }; },
  async mounted() { await this.load(); },
  computed: {
    isToday() { return this.date === ui.todayIso(); },
    preparedPct() { const t = this.d && this.d.tiles; return t && Number(t.planned_total) ? Math.min(100, Math.round(Number(t.prepared_total) / Number(t.planned_total) * 100)) : 0; },
  },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try { this.d = (await api.get('/dashboards/kitchen', { date: this.date })).data; }
      catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
      // After the dashboard (never in parallel) so the alert check runs once.
      if (this.d) { try { this.alerts = (await api.get('/alerts', { status: 'open' })).data; } catch (e) { this.alerts = this.d.alerts; } }
    },
    toPrepare(r) { return r.final_qty === null || r.final_qty === undefined ? r.recommended_qty : r.final_qty; },
    pct(r) { const t = Number(this.toPrepare(r)); return t ? Math.min(100, Math.round(Number(r.prepared) / t * 100)) : (r.prepared > 0 ? 100 : 0); },
    async ack(a) {
      try { await api.post('/alerts/' + a.id + '/acknowledge'); await this.load(); } catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
  },
}).mount('#app');
