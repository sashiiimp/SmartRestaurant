SR.createApp({
  data() { return { date: ui.todayIso(), r: null, loading: true, error: null, ui }; },
  async mounted() { await this.load(); },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try { this.r = (await api.get('/recommendations/requirements', { date: this.date })).data; }
      catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
  },
}).mount('#app');
