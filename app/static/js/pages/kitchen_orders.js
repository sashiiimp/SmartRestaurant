SR.createApp({
  data() {
    const t = ui.todayIso();
    return { tab: 'pre', orderDate: t, orders: [], oloading: false, oform: { id: null, menu_item_id: '', quantity: '', customer_note: '' }, oerrors: {}, osaving: false, today: t, from: t, to: ui.addDays(t, 13), status: '', items: [], rows: [], loading: true, error: null, notice: null, form: null, detail: null, errors: {}, saving: false, ui };
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
    editable(r) { return (r.status === 'pending' || r.status === 'confirmed') && r.target_date >= this.today; },
    actionLabel(s) { return { confirmed: 'Confirm', pending: 'Put back on hold', completed: 'Mark completed', cancelled: 'Cancel pre-order' }[s] || s; },
    async load() {
      this.loading = true; this.error = null;
      try { this.rows = (await api.get('/kitchen/pre-orders', { from: this.from, to: this.to, status: this.status })).data; }
      catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    blank() { return { id: null, menu_item_id: '', target_date: ui.addDays(this.today, 1), pickup_time: '', quantity: '', customer_name: '', customer_contact: '', customer_note: '', status: 'pending' }; },
    startNew() { this.detail = null; this.form = this.blank(); this.errors = {}; },
    edit(r) {
      this.detail = null;
      this.form = { id: r.id, menu_item_id: r.menu_item_id, target_date: r.target_date, pickup_time: r.pickup_time || '', quantity: r.quantity,
        customer_name: r.customer_name || '', customer_contact: r.customer_contact || '', customer_note: r.customer_note || '', status: r.status };
      this.errors = {};
    },
    async view(r) {
      this.form = null;
      try { this.detail = (await api.get('/kitchen/pre-orders/' + r.id)).data; this.$nextTick(() => { const el = document.getElementById('pre-order-detail'); if (el) el.scrollIntoView({ block: 'nearest' }); }); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
    warn(meta) { this.notice = meta && meta.warnings && meta.warnings.length ? meta.warnings[0] : null; },
    async save() {
      this.saving = true; this.errors = {}; this.notice = null;
      const f = this.form;
      const body = { target_date: f.target_date, pickup_time: f.pickup_time, quantity: f.quantity, customer_name: f.customer_name,
        customer_contact: f.customer_contact, customer_note: f.customer_note };
      try {
        const r = f.id ? await api.patch('/kitchen/pre-orders/' + f.id, body)
          : await api.post('/kitchen/pre-orders', { ...body, menu_item_id: f.menu_item_id, status: f.status });
        ui.toast('Pre-order saved.'); this.warn(r.meta); this.form = null; await this.load();
      } catch (e) { this.errors = e.fields || {}; if (!Object.keys(this.errors).length) ui.toast(ui.errorText(e), 'danger'); }
      finally { this.saving = false; }
    },
    async setStatus(r, status) {
      if (status === 'cancelled' && !confirm('Cancel pre-order #' + r.id + ' (' + r.quantity + ' x ' + r.item + ')?')) return;
      this.notice = null;
      try {
        const res = await api.patch('/kitchen/pre-orders/' + r.id, { status }); this.warn(res.meta);
        ui.toast('Pre-order #' + r.id + ' ' + status + '.');
        if (this.detail && this.detail.id === r.id) this.detail = (await api.get('/kitchen/pre-orders/' + r.id)).data;
        await this.load();
      } catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
  },
}).mount('#app');
