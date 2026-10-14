const WIDE = '(min-width: 1200px)';
SR.createApp({
  data() {
    // wide screens get the comparison table, narrower ones the cards (only one is rendered, so ids stay unique)
    return { date: ui.todayIso(), plan: null, loading: true, error: null, state: {}, wide: window.matchMedia(WIDE).matches, ui };
  },
  computed: {
    items() { return this.plan ? this.plan.items : []; },
    isPast() { return this.date < ui.todayIso(); },
    isFuture() { return this.date > ui.todayIso(); },
    anyWeatherEstimated() { return this.items.some(it => it.weather_estimated); },
    withForecast() { return this.items.filter(it => it.status !== 'no_forecast').length; },
    decided() { return this.items.filter(it => it.status === 'accepted' || it.status === 'overridden').length; },
    totalRecommended() { return this.items.reduce((n, it) => n + (it.status === 'no_forecast' ? 0 : Number(it.recommended_qty) || 0), 0); },
    totalPrepared() { return this.items.reduce((n, it) => n + (Number(it.prepared_so_far) || 0), 0); },
  },
  async mounted() { window.matchMedia(WIDE).addEventListener('change', e => { this.wide = e.matches; }); await this.load(); },
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
    progress(item) {
      if (!item.final_qty) return item.prepared_so_far > 0 ? 100 : 0;
      return Math.min(100, Math.round(100 * item.prepared_so_far / item.final_qty));
    },
    async prepStatus(item, action) {
      const s = this.st(item.menu_item_id); s.busy = true; s.errors = {}; s.message = null;
      try {
        const res = await api.post('/recommendations/prep/status', { menu_item_id: item.menu_item_id, date: this.date, action });
        await this.refresh();
        const label = { start: 'started', done: 'marked done', reopen: 'reopened' }[action];
        ui.toast(item.name + ': ' + label + '.');
        if (res.meta && res.meta.warnings && res.meta.warnings.length) ui.toast(res.meta.warnings[0], 'warning');
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
