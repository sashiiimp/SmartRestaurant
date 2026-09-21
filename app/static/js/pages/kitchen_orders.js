SR.createApp({
  data() {
    const t = ui.todayIso();
    return { tab: 'pre', orderDate: t, orders: [], oloading: false, oform: { id: null, menu_item_id: '', quantity: '', customer_note: '' }, oerrors: {}, osaving: false, today: t, from: t, to: ui.addDays(t, 13), status: '', items: [], rows: [], loading: true, error: null, notice: null, form: null, errors: {}, saving: false, ui };
  },
  async mounted() {
    try { this.items = (await api.get('/menu-items', { active: true })).data; } catch (e) { this.error = ui.errorText(e); }
    await this.load();
    await this.loadOrders();
  },
  computed: {
    openCount() { return this.orders.filter(o => o.status === 'open').length; },
    openPortions() { return this.orders.filter(o => o.status === 'open').reduce((a, o) => a + o.quantity, 0); },
  },
  methods: {
    async loadOrders() {
      this.oloading = true;
      try { this.orders = (await api.get('/kitchen/orders', { date: this.orderDate })).data; }
      catch (e) { this.error = ui.errorText(e); } finally { this.oloading = false; }
    },
    resetOrderForm() { this.oform = { id: null, menu_item_id: '', quantity: '', customer_note: '' }; this.oerrors = {}; },
    editOrder(r) { this.oform = { id: r.id, menu_item_id: r.menu_item_id, quantity: r.quantity, customer_note: r.customer_note || '' }; this.oerrors = {}; window.scrollTo({ top: 0, behavior: 'smooth' }); },
    async saveOrder() {
      this.osaving = true; this.oerrors = {};
      const f = this.oform;
      try {
        if (f.id) await api.patch('/kitchen/orders/' + f.id, { quantity: f.quantity, customer_note: f.customer_note });
        else await api.post('/kitchen/orders', { menu_item_id: f.menu_item_id, quantity: f.quantity, customer_note: f.customer_note, order_date: this.orderDate });
        ui.toast('Order saved.'); this.resetOrderForm(); await this.loadOrders();
      } catch (e) { this.oerrors = e.fields || {}; if (!Object.keys(this.oerrors).length) ui.toast(ui.errorText(e), 'danger'); }
      finally { this.osaving = false; }
    },
    async setOrderStatus(r, status) {
      if (status === 'cancelled' && !confirm('Cancel the order for ' + r.quantity + ' x ' + r.item + '?')) return;
      try { await api.patch('/kitchen/orders/' + r.id, { status }); ui.toast('Order ' + status + '.'); await this.loadOrders(); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); await this.loadOrders(); }
    },
    editable(r) { return r.status !== 'cancelled' && r.target_date >= this.today; },
    async load() {
      this.loading = true; this.error = null;
      try { this.rows = (await api.get('/kitchen/pre-orders', { from: this.from, to: this.to, status: this.status })).data; }
      catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    startNew() { this.form = { id: null, menu_item_id: '', target_date: ui.addDays(this.today, 1), quantity: '', customer_note: '', status: 'pending' }; this.errors = {}; },
    edit(r) { this.form = { id: r.id, menu_item_id: r.menu_item_id, target_date: r.target_date, quantity: r.quantity, customer_note: r.customer_note || '', status: r.status }; this.errors = {}; },
    warn(meta) { this.notice = meta && meta.warnings && meta.warnings.length ? meta.warnings[0] : null; },
    async save() {
      this.saving = true; this.errors = {}; this.notice = null;
      const f = this.form;
      try {
        const r = f.id
          ? await api.patch('/kitchen/pre-orders/' + f.id, { target_date: f.target_date, quantity: f.quantity, customer_note: f.customer_note })
          : await api.post('/kitchen/pre-orders', { menu_item_id: f.menu_item_id, target_date: f.target_date, quantity: f.quantity, customer_note: f.customer_note, status: f.status });
        ui.toast('Pre-order saved.'); this.warn(r.meta); this.form = null; await this.load();
      } catch (e) { this.errors = e.fields || {}; if (!Object.keys(this.errors).length) ui.toast(ui.errorText(e), 'danger'); }
      finally { this.saving = false; }
    },
    async setStatus(r, status) {
      if (status === 'cancelled' && !confirm('Cancel this pre-order for ' + r.item + '?')) return;
      this.notice = null;
      try { const res = await api.patch('/kitchen/pre-orders/' + r.id, { status }); this.warn(res.meta); ui.toast('Pre-order ' + status + '.'); await this.load(); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
  },
}).mount('#app');
