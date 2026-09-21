SR.createApp({
  data() { return { d: null, loading: true, error: null, ui }; },
  async mounted() { await this.load(); },
  computed: { maxNeed() { return this.d ? Math.max(1, ...this.d.need_vs_stock.map(r => Math.max(r.need, r.usable))) : 1; } },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try { this.d = (await api.get('/dashboards/inventory')).data; } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    async ack(a) { try { await api.post('/alerts/' + a.id + '/acknowledge'); await this.load(); } catch (e) { ui.toast(ui.errorText(e), 'danger'); } },
  },
}).mount('#app');
