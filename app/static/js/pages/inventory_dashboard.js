SR.createApp({
  data() { return { d: null, alerts: [], today: ui.todayIso(), loading: true, error: null, ui }; },
  async mounted() { await this.load(); },
  computed: {
    stockTotal() { return this.d ? this.d.counts.ok + this.d.counts.low + this.d.counts.out : 0; },
    expiredCount() { return this.d ? this.d.expiring.filter(b => b.expired).length : 0; },
    // Only ingredients whose 7-day need is above usable stock; the full list is on Ingredient demand.
    risks() { return this.d ? this.d.need_vs_stock.filter(r => Number(r.need) > Number(r.usable)) : []; },
  },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try { this.d = (await api.get('/dashboards/inventory')).data; } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
      // After the dashboard (never in parallel) so the alert check runs once.
      if (this.d) { try { this.alerts = (await api.get('/alerts', { status: 'open' })).data; } catch (e) { this.alerts = this.d.alerts; } }
    },
    cover(r) { return Number(r.need) ? Math.max(0, Math.min(100, Math.round(Number(r.usable) / Number(r.need) * 100))) : 100; },
    async ack(a) { try { await api.post('/alerts/' + a.id + '/acknowledge'); await this.load(); } catch (e) { ui.toast(ui.errorText(e), 'danger'); } },
  },
}).mount('#app');
