SR.createApp({
  data() { return { date: ui.todayIso(), d: null, loading: true, error: null, ui }; },
  async mounted() { await this.load(); },
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
