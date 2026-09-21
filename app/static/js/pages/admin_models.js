SR.createApp({
  data() { return { versions: [], runs: [], loading: true, error: null, busy: '', trainResult: null, ui }; },
  computed: { active() { return this.versions.find(v => v.status === 'active') || null; } },
  async mounted() { await this.load(); },
  methods: {
    async load() {
      try { this.versions = (await api.get('/model-versions')).data; this.runs = (await api.get('/forecast-runs', { limit: 12 })).data; }
      catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    async train() {
      this.busy = 'train'; this.trainResult = null;
      try { const { data } = await api.post('/model-versions'); this.trainResult = data; ui.toast('Trained ' + data.version_label + '. Activate it to use it.'); await this.load(); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); } finally { this.busy = ''; }
    },
    async activate(v) {
      if (!confirm('Activate ' + v.version_label + '? The current model stays available for rollback.')) return;
      try { await api.post('/model-versions/' + v.id + '/activate'); ui.toast(v.version_label + ' is now active. Run a forecast to use it.'); await this.load(); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
    async runForecast() {
      this.busy = 'run';
      try { const { data } = await api.post('/forecast-runs', {}); ui.toast('Forecast run ' + data.status + ' (' + data.items_forecast + ' items, ' + data.duration_ms + ' ms)', data.status === 'ok' ? 'success' : 'warning'); await this.load(); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); } finally { this.busy = ''; }
    },
    m(v, name) { return (v.metrics.comparison.find(c => c.model === name) || {}); },
  },
}).mount('#app');
