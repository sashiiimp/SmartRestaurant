SR.createApp({
  data() { return { today: ui.todayIso(), rows: [], ingredients: [], status: '', loading: true, error: null, form: null, errors: {}, saving: false, ui }; },
  async mounted() {
    try { this.ingredients = (await api.get('/ingredients', { active: true })).data; } catch (e) { this.error = ui.errorText(e); }
    await this.load();
    // "Request" on the Ingredients page links here with the ingredient and the missing quantity filled in
    const q = new URLSearchParams(location.search);
    if (q.get('ingredient')) {
      this.startNew();
      this.form.lines = [{ ingredient_id: Number(q.get('ingredient')), quantity: q.get('qty') || '' }];
    }
  },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try { this.rows = (await api.get('/kitchen/stock-requests', { status: this.status })).data; }
      catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    startNew() { this.form = { needed_date: '', note: '', lines: [{ ingredient_id: '', quantity: '' }] }; this.errors = {}; },
    async save() {
      this.saving = true; this.errors = {};
      const f = this.form;
      const body = { needed_date: f.needed_date || undefined, note: f.note || undefined, lines: f.lines.map(l => ({ ingredient_id: l.ingredient_id, quantity: l.quantity })) };
      try { await api.post('/kitchen/stock-requests', body); ui.toast('Request sent to the inventory section.'); this.form = null; await this.load(); }
      catch (e) { this.errors = e.fields || {}; if (!Object.keys(this.errors).length) ui.toast(ui.errorText(e), 'danger'); }
      finally { this.saving = false; }
    },
    async cancel(r) {
      if (!confirm('Cancel request #' + r.id + '?')) return;
      try { await api.post('/kitchen/stock-requests/' + r.id + '/cancel'); ui.toast('Request cancelled.'); await this.load(); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); await this.load(); }
    },
  },
}).mount('#app');
