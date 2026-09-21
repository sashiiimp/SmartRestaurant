SR.createApp({
  data() { return { s: null, loading: true, error: null, saving: false, errors: {}, ui }; },
  async mounted() {
    try { this.s = (await api.get('/settings')).data; } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
  },
  methods: {
    async save() {
      this.saving = true; this.errors = {};
      const body = { data_source_label: this.s.data_source_label, alerts: {} };
      this.s.values.forEach(v => { body[v.key] = v.value; });
      this.s.alerts.forEach(a => { body.alerts[a.key] = a.enabled; });
      try { this.s = (await api.put('/settings', body)).data; ui.toast('Settings saved. They apply from the next calculation.'); }
      catch (e) { this.errors = e.fields || {}; if (!Object.keys(this.errors).length) ui.toast(ui.errorText(e), 'danger'); } finally { this.saving = false; }
    },
  },
}).mount('#app');
