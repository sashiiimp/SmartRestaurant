SR.createApp({
  data() { return { rows: [], loading: true, error: null, ui }; },
  async mounted() {
    try { this.rows = (await api.get('/recommendations/reorder')).data; }
    catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
  },
}).mount('#app');
