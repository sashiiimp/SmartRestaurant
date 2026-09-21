SR.createApp({
  data() { return { range: 7, d: null, loading: true, error: null, running: false, ui }; },
  async mounted() { await this.load(); },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try { this.d = (await api.get('/dashboards/admin', { range: this.range })).data; } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    async runAlerts() {
      this.running = true;
      try { const { data } = await api.post('/alerts/run'); ui.toast('Alerts checked: ' + data.opened + ' opened, ' + data.closed + ' cleared.'); await this.load(); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); } finally { this.running = false; }
    },
    async ack(a) { try { await api.post('/alerts/' + a.id + '/acknowledge'); await this.load(); } catch (e) { ui.toast(ui.errorText(e), 'danger'); } },
  },
}).mount('#app');
