SR.createApp({
  data() { return { s: null, r: { name: '', address: '', contact: '', opening_days: '', opening_hours: '' }, rErrors: {}, savingR: false, loading: true, error: null, saving: false, errors: {}, ui }; },
  async mounted() {
    try { this.s = (await api.get('/settings')).data; this.r = this.blankToText((await api.get('/restaurant')).data); } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
  },
  methods: {
    blankToText(r) { return { name: r.name || '', address: r.address || '', contact: r.contact || '', opening_days: r.opening_days || '', opening_hours: r.opening_hours || '' }; },
    async saveRestaurant() {
      this.savingR = true; this.rErrors = {};
      try { this.r = this.blankToText((await api.put('/restaurant', this.r)).data); ui.toast('Restaurant information saved. The name shows in the sidebar from the next page.'); }
      catch (e) { this.rErrors = e.fields || {}; if (!Object.keys(this.rErrors).length) ui.toast(ui.errorText(e), 'danger'); }
      finally { this.savingR = false; }
    },
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
