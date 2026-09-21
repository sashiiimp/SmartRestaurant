SR.createApp({
  data() { return { date: ui.todayIso(), r: null, loading: true, error: null, ui }; },
  async mounted() { await this.load(); },
  methods: {
    async report(i) {
      const note = window.prompt('Report a shortage of ' + i.name + '. What did you find? (optional)', '');
      if (note === null) return;
      try { const { data } = await api.post('/kitchen/shortage-reports', { ingredient_id: i.ingredient_id, note }); ui.toast(data.created ? 'Shortage reported to Inventory.' : 'The open shortage report was updated.'); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
    async load() {
      this.loading = true; this.error = null;
      try { this.r = (await api.get('/recommendations/requirements', { date: this.date })).data; }
      catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
  },
}).mount('#app');
