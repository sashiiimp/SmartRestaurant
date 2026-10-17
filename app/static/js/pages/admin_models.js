SR.createApp({
  data() { return { versions: [], runs: [], loading: true, error: null, busy: '', trainResult: null, ui }; },
  computed: {
    active() { return this.versions.find(v => v.status === 'active') || null; },
    // a version that is not active but scored a lower hold-out error. Each version is tested on the 56 days before it
    // was trained, so the periods differ and the errors are not a like-for-like comparison: the page says so.
    lowerOther() {
      const a = this.active, mae = v => this.m(v, v.algorithm).mae;
      if (!a || mae(a) == null) return null;
      const best = this.versions.filter(v => v.status === 'trained' && mae(v) != null && mae(v) < mae(a)).sort((x, y) => mae(x) - mae(y))[0];
      return best ? { v: best, mae: mae(best), activeMae: mae(a), samePeriod: best.holdout.start === a.holdout.start && best.holdout.end === a.holdout.end } : null;
    },
  },
  async mounted() { await this.load(); },
  methods: {
    async load() {
      try { this.versions = (await api.get('/model-versions')).data || []; this.runs = (await api.get('/forecast-runs', { limit: 12 })).data || []; }
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
    // the models compared in one training run, lowest hold-out error first
    byMae(list) { return [...(list || [])].sort((x, y) => (x.mae ?? Infinity) - (y.mae ?? Infinity)); },
    algoName(a) { return { xgboost: 'XGBoost', random_forest: 'Random Forest', naive_lag7: 'Same day last week', seasonal_mean4: '4-week average' }[a] || a; },
  },
}).mount('#app');
