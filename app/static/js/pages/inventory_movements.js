SR.createApp({
  data() {
    const t = ui.todayIso();
    return {
      tab: 'in', ingredients: [], levels: [], moves: [], total: 0, batches: [], filterIng: '', loading: true, error: null, saving: false, errors: {}, ui,
      forms: {
        in: { ingredient_id: '', quantity: '', received_date: t, expiry_date: '', batch_no: '', unit_cost: '' },
        out: { ingredient_id: '', quantity: '', movement_date: t, reason: 'issued_to_kitchen' },
        wastage: { ingredient_id: '', quantity: '', movement_date: t, reason: 'expired', batch_id: '' },
        adjust: { ingredient_id: '', counted_quantity: '', movement_date: t, note: '' },
      },
    };
  },
  computed: {
    form() { return this.forms[this.tab]; },
    onHand() { const r = this.levels.find(x => x.id === this.form.ingredient_id); return r ? Number(r.on_hand) : null; },
    adjustDiff() {
      const c = this.form.counted_quantity;
      return this.tab === 'adjust' && this.onHand !== null && c !== '' && !isNaN(Number(c)) ? Number(c) - this.onHand : null;
    },
    unit() { const i = this.ingredients.find(x => x.id === this.form.ingredient_id); return i ? i.unit : ''; },
  },
  async mounted() {
    try {
      this.ingredients = (await api.get('/ingredients', { active: true })).data;
      if (this.ingredients.length) Object.values(this.forms).forEach(f => { f.ingredient_id = this.ingredients[0].id; });
      await this.refresh();
    } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
  },
  methods: {
    async refresh() {
      const r = await api.get('/stock/movements', { ingredient_id: this.filterIng, limit: 30 });
      this.moves = r.data; this.total = r.meta.total;
      this.batches = (await api.get('/stock/batches', { ingredient_id: this.filterIng })).data;
      this.levels = (await api.get('/stock/levels')).data;
    },
    async save() {
      this.saving = true; this.errors = {};
      const path = { in: '/stock/in', out: '/stock/out', wastage: '/stock/wastage', adjust: '/stock/adjustments' }[this.tab];
      const body = { ...this.form };
      Object.keys(body).forEach(k => { if (body[k] === '') delete body[k]; });
      try {
        const { data } = await api.post(path, body);
        ui.toast('Saved. Usable stock is now ' + ui.qty(data.usable === undefined ? null : data.usable, data.unit || this.unit).trim());
        this.form.quantity = ''; this.form.counted_quantity = ''; this.form.note = '';
        await this.refresh();
        api.get('/alerts', { status: 'open', refresh: true }).catch(() => {});
      } catch (e) { this.errors = e.fields || {}; if (!Object.keys(this.errors).length) ui.toast(ui.errorText(e), 'danger'); }
      finally { this.saving = false; }
    },
  },
}).mount('#app');
