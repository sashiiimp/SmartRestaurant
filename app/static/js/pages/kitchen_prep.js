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
    finished() { return this.items.filter(it => it.prep_status === 'done').length; },
    // display only: the same figures as the rows (planned = the decision, else the suggestion)
    totals() {
      const t = { recommended: 0, planned: 0, prepared: 0, remaining: 0, pct: 0 };
      for (const it of this.items) {
        t.prepared += Number(it.prepared_so_far) || 0;
        if (it.status === 'no_forecast') continue;
        t.recommended += Number(it.recommended_qty) || 0;
        t.planned += Number(this.planned(it)) || 0;
        if (it.prep_status !== 'done') t.remaining += Math.max(0, (Number(this.planned(it)) || 0) - (Number(it.prepared_so_far) || 0));
      }
      t.pct = t.planned ? Math.min(100, Math.round(100 * t.prepared / t.planned)) : 0;
      return t;
    },
  },
  async mounted() { window.matchMedia(WIDE).addEventListener('change', e => { this.wide = e.matches; }); await this.load(); },
  methods: {
    // There is no general Accept button: the first Add prepared accepts the recommendation (recorded as automatic).
    // One case keeps a button: an accepted plan whose recommendation has since moved (for example after a new confirmed
    // pre-order) can take the new figure without counting as a change of plan.
    acceptLabel(it) { return this.moved(it) ? 'Use new ' + it.recommended_qty : null; },
    canDecide(it) { return it.status !== 'no_forecast' && !this.isPast && it.prep_status !== 'done'; },
    // planned = the decided quantity, or the suggestion while nothing is decided (null without a forecast)
    planned(it) { return it.final_qty !== null && it.final_qty !== undefined ? it.final_qty : (it.status === 'no_forecast' ? null : it.recommended_qty); },
    moved(it) { return it.status === 'accepted' && it.final_qty !== it.recommended_qty; },
    decisionKey(it) { return it.status === 'overridden' ? 'changed' : (it.status === 'accepted' && it.decision_source === 'auto' ? 'auto' : it.status); },
    decisionLabel(it) { return { suggested: 'Suggested', accepted: 'Accepted', auto: 'Auto-accepted', changed: 'Changed' }[this.decisionKey(it)] || ''; },
    remaining(it) {
      const p = this.planned(it);
      if (p === null) return { text: '-', tone: 'none' };
      if (it.prep_status === 'done') return { text: 'Finished', tone: 'done' };
      const r = p - (Number(it.prepared_so_far) || 0);
      return r > 0 ? { text: String(r), tone: 'left' } : (r === 0 ? { text: '0', tone: 'ok' } : { text: '+' + (-r) + ' over', tone: 'over' });
    },
    // the entered quantity is ADDED to the total; say what it adds to (and that the first entry accepts the plan)
    addHint(it) {
      if (it.prep_status === 'done') return 'A correction adds to the ' + it.prepared_so_far + ' prepared; the item stays finished';
      if (it.prepared_so_far > 0) return 'Adds to the ' + it.prepared_so_far + ' already prepared';
      if (it.status === 'suggested' && !this.isPast) return 'Adds to the total · the first entry accepts ' + it.recommended_qty;
      return 'Adds to the total (none prepared yet)';
    },
    finishGap(it) {
      const d = (Number(it.prepared_so_far) || 0) - (Number(this.planned(it)) || 0);
      return d < 0 ? (-d) + ' fewer than planned' : (d > 0 ? d + ' more than planned' : 'matches the plan');
    },
    barClass(it) { return it.prep_status === 'done' ? 'bg-success' : (it.status === 'suggested' ? 'is-suggested' : ''); },
    openChange(it) {
      const s = this.st(it.menu_item_id);
      s.changing = !s.changing; s.finishing = false;
      if (s.changing && s.qty === '') s.qty = String(this.planned(it));
    },
    askFinish(it) { const s = this.st(it.menu_item_id); s.finishing = true; s.changing = false; s.errors = {}; s.message = null; },
    st(id) {
      if (!this.state[id]) this.state[id] = { changing: false, finishing: false, qty: '', reason: '', add: '', busy: false, errors: {}, message: null };
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
        s.changing = false;
        await this.refresh();
        ui.toast(action === 'accept' ? item.name + ': plan updated to ' + data.final_qty : item.name + ': plan changed to ' + data.final_qty);
        if (data.warnings && data.warnings.length) ui.toast(data.warnings[0], 'warning');
      } catch (e) { s.errors = e.fields || {}; s.message = ui.errorText(e); } finally { s.busy = false; }
    },
    async addPrepared(item) {
      const s = this.st(item.menu_item_id); s.busy = true; s.errors = {}; s.message = null;
      try {
        const { data } = await api.post('/kitchen/prepared', { menu_item_id: item.menu_item_id, date: this.date, quantity: s.add });
        s.add = '';
        await this.refresh();
        ui.toast(item.name + ': added ' + data.added + ', ' + data.total_prepared + ' prepared in total');
        if (data.auto_accepted) ui.toast(item.name + ': plan of ' + data.auto_accepted.final_qty + ' accepted automatically', 'info');
      } catch (e) { s.errors = e.fields || {}; s.message = ui.errorText(e); } finally { s.busy = false; }
    },
    progress(item) {
      const p = this.planned(item);
      if (!p) return item.prepared_so_far > 0 ? 100 : 0;
      return Math.min(100, Math.round(100 * item.prepared_so_far / p));
    },
    async prepStatus(item, action) {
      const s = this.st(item.menu_item_id); s.busy = true; s.errors = {}; s.message = null;
      try {
        const res = await api.post('/recommendations/prep/status', { menu_item_id: item.menu_item_id, date: this.date, action });
        s.finishing = false;
        await this.refresh();
        const label = { start: 'started', done: 'preparation finished', reopen: 'reopened' }[action];
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
