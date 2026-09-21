SR.createApp({
  data() {
    return { date: ui.todayIso(), plan: null, loading: true, error: null, state: {}, ui };
  },
  computed: {
    items() { return this.plan ? this.plan.items : []; },
    isPast() { return this.date < ui.todayIso(); },
  },
  async mounted() { await this.load(); },
  methods: {
    st(id) {
      if (!this.state[id]) this.state[id] = { overriding: false, qty: '', reason: '', add: '', busy: false, errors: {}, message: null };
      return this.state[id];
    },
    async load() {
      this.loading = true; this.error = null;
      try {
        const { data } = await api.get('/recommendations/prep', { date: this.date });
        this.plan = data; this.state = {};
      } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    async refresh() {
      const { data } = await api.get('/recommendations/prep', { date: this.date });
      this.plan = data;
    },
    async decide(item, action) {
      const s = this.st(item.menu_item_id); s.busy = true; s.errors = {}; s.message = null;
      const body = { menu_item_id: item.menu_item_id, date: this.date, action };
      if (action === 'override') { body.final_qty = s.qty; body.reason = s.reason; }
      try {
        const { data } = await api.post('/recommendations/prep/decisions', body);
        s.overriding = false;
        await this.refresh();
        ui.toast(action === 'accept' ? item.name + ': accepted ' + data.final_qty : item.name + ': overridden to ' + data.final_qty);
      } catch (e) { s.errors = e.fields || {}; s.message = ui.errorText(e); } finally { s.busy = false; }
    },
    async addPrepared(item) {
      const s = this.st(item.menu_item_id); s.busy = true; s.errors = {}; s.message = null;
      try {
        const { data } = await api.post('/kitchen/prepared', { menu_item_id: item.menu_item_id, date: this.date, quantity: s.add });
        s.add = '';
        await this.refresh();
        ui.toast(item.name + ': ' + data.total_prepared + ' prepared so far');
      } catch (e) { s.errors = e.fields || {}; s.message = ui.errorText(e); } finally { s.busy = false; }
    },
    async toggleAvailable(item) {
      const flag = !item.is_available;
      try {
        await api.patch('/menu-items/' + item.menu_item_id + '/availability', { is_available: flag });
        await this.refresh();
        ui.toast(item.name + (flag ? ' is available again.' : ' is marked unavailable.'));
      } catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
  },
}).mount('#app');
