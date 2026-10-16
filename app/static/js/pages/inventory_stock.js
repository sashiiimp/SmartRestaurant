SR.createApp({
  data() { return { rows: [], suppliers: [], filter: '', status: '', loading: true, error: null, form: null, check: null, checking: false, ui }; },
  computed: {
    shown() {
      const f = this.filter.toLowerCase();
      return this.rows.filter(r => (!f || r.name.toLowerCase().includes(f)) && (!this.status || r.status === this.status));
    },
  },
  async mounted() { await this.load(); this.suppliers = (await api.get('/suppliers')).data; },
  methods: {
    async runCheck() {
      this.checking = true;
      try { this.check = (await api.get('/stock/consistency')).data; } catch (e) { ui.toast(ui.errorText(e), 'danger'); } finally { this.checking = false; }
    },
    async load() {
      this.loading = true; this.error = null;
      try { this.rows = (await api.get('/stock/levels')).data; } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    // the form itself (sr-ingredient-form) is shared with Admin > Menu & Recipes (BOM) > Ingredients
    add() { this.form = {}; },
    edit(r) { this.form = r; },
    async saved() { this.form = null; await this.load(); },
  },
}).mount('#app');
