SR.createApp({
  data() { return { date: ui.todayIso(), plan: null, loading: true, error: null, state: {}, ui }; },
  computed: {
    items() { return this.plan ? this.plan.items : []; },
    isPast() { return this.date < ui.todayIso(); },
    isToday() { return this.date === ui.todayIso(); },
    isFuture() { return this.date > ui.todayIso(); },
    anyWeatherEstimated() { return this.items.some(it => it.weather_estimated); },
    withForecast() { return this.items.filter(it => it.status !== 'no_forecast').length; },
    decided() { return this.items.filter(it => it.status === 'accepted' || it.status === 'overridden').length; },
    finished() { return this.items.filter(it => it.prep_status === 'done').length; },
    allDone() { return this.withForecast > 0 && this.finished === this.withForecast; },
    // display only, added up from the rows (planned = the decision, else the suggestion). Remaining and extra use the
    // same per-row figures as the list, so the summary always equals the sum of what each row shows.
    totals() {
      const t = { recommended: 0, planned: 0, prepared: 0, remaining: 0, extra: 0, pct: 0 };
      for (const it of this.items) {
        t.prepared += Number(it.prepared_so_far) || 0;
        if (it.status === 'no_forecast') continue;
        t.recommended += Number(it.recommended_qty) || 0;
        t.planned += Number(this.planned(it)) || 0;
        t.remaining += this.remaining(it);
        t.extra += this.extra(it);
      }
      t.pct = t.planned ? Math.min(100, Math.round(100 * t.prepared / t.planned)) : 0;
      return t;
    },
  },
  async mounted() { await this.load(); },
  methods: {
    // There is no general Accept button: the first Add prepared accepts the recommendation (recorded as automatic).
    // One case keeps a button: an accepted plan whose recommendation has since moved (for example after a new confirmed
    // pre-order) can take the new figure without counting as a change of plan.
    acceptLabel(it) { return this.moved(it) ? 'Use new ' + it.recommended_qty : null; },
    canDecide(it) { return it.status !== 'no_forecast' && !this.isPast && it.prep_status !== 'done'; },
    // planned = the decided quantity, or the suggestion while nothing is decided (null without a forecast)
    planned(it) { return it.final_qty !== null && it.final_qty !== undefined ? it.final_qty : (it.status === 'no_forecast' ? null : it.recommended_qty); },
    moved(it) { return it.status === 'accepted' && it.final_qty !== it.recommended_qty; },
    // Approved covers both ways of approving (by hand, or by the first prepared entry); the tooltip says which
    decisionKey(it) { return it.status === 'overridden' ? 'changed' : (it.status === 'accepted' ? 'approved' : it.status); },
    decisionLabel(it) { return { suggested: 'Suggested', approved: 'Approved', changed: 'Changed' }[this.decisionKey(it)] || ''; },
    decisionTitle(it) {
      if (it.status === 'suggested') return 'Not approved yet: your first prepared entry approves it';
      if (it.status === 'accepted') return it.decision_source === 'auto' ? 'Approved automatically by the first prepared entry' : 'Approved';
      return it.override_reason ? 'Changed by the kitchen: ' + it.override_reason : 'Changed by the kitchen';
    },
    calcText(it) {
      return 'forecast ' + ui.num(it.forecast_qty, 1) + ' + ' + it.buffer_pct + '% safety buffer' + (it.preorder_qty ? ' (at least the ' + it.preorder_qty + ' pre-ordered)' : '')
        + ', rounded up to batches of ' + it.batch_size;
    },
    // per row: remaining never goes below 0 (a finished item has nothing left); portions above the plan are "extra"
    remaining(it) {
      const p = this.planned(it);
      if (p === null || it.prep_status === 'done') return 0;
      return Math.max(0, p - (Number(it.prepared_so_far) || 0));
    },
    extra(it) { const p = this.planned(it); return p === null ? 0 : Math.max(0, (Number(it.prepared_so_far) || 0) - p); },
    short(it) { const p = this.planned(it); return p === null ? 0 : Math.max(0, p - (Number(it.prepared_so_far) || 0)); },
    readyToFinish(it) { const p = this.planned(it); return it.prep_status !== 'done' && it.prepared_so_far > 0 && p !== null && it.prepared_so_far >= p; },
    rowState(it) {
      if (it.status === 'no_forecast' && !it.prepared_so_far) return 'none';
      if (it.prep_status === 'done') return 'done';
      return it.prepared_so_far > 0 ? 'cooking' : (it.status === 'suggested' ? 'suggested' : 'planned');
    },
    barClass(it) { return it.prep_status === 'done' ? 'bg-success' : (this.extra(it) ? 'bg-warning' : (it.status === 'suggested' ? 'is-suggested' : '')); },
    openChange(it) {
      const s = this.st(it.menu_item_id);
      s.changing = !s.changing; s.confirm = null;
      if (s.changing && s.qty === '') s.qty = String(this.planned(it));
    },
    // Finish: straight away when the plan is reached; below the plan it asks once, in the row
    finish(it) {
      const s = this.st(it.menu_item_id), gap = this.short(it);
      s.changing = false; s.errors = {}; s.message = null;
      if (!gap) return this.prepStatus(it, 'done');
      s.confirm = { title: 'Finish preparation of ' + it.name, yes: 'Finish preparation', go: () => this.prepStatus(it, 'done'),
        text: 'Finish ' + it.name + ' with ' + it.prepared_so_far + ' of ' + this.planned(it) + ' planned? ' + gap + ' fewer than planned.' };
    },
    st(id) {
      if (!this.state[id]) this.state[id] = { changing: false, confirm: null, adding: false, qty: '', reason: '', add: '', busy: false, errors: {}, message: null };
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
        s.changing = false; s.qty = ''; s.reason = '';
        await this.refresh();
        ui.toast(action === 'accept' ? item.name + ': plan updated to ' + data.final_qty : item.name + ': plan changed to ' + data.final_qty);
        if (data.warnings && data.warnings.length) ui.toast(data.warnings[0], 'warning');
      } catch (e) { s.errors = e.fields || {}; s.message = Object.keys(s.errors).length ? null : ui.errorText(e); } finally { s.busy = false; }
    },
    // An entry that takes the item above its plan is confirmed first (a typo such as 300 for 30 cannot be taken back);
    // cooking more than planned is allowed and shows as extra.
    addPrepared(item) {
      const s = this.st(item.menu_item_id), n = Number(String(s.add).trim()), p = this.planned(item);
      s.errors = {}; s.message = null; s.confirm = null;
      if (Number.isInteger(n) && n > 0 && p) {
        const total = (Number(item.prepared_so_far) || 0) + n;
        if (total > p) {
          s.confirm = { title: 'Add more than planned for ' + item.name, yes: 'Add ' + n, go: () => this.sendPrepared(item),
            text: 'Adding ' + n + ' makes ' + total + ' prepared, ' + (total - p) + ' more than the plan of ' + p + '.' };
          return;
        }
      }
      return this.sendPrepared(item);
    },
    async sendPrepared(item) {
      const s = this.st(item.menu_item_id); s.busy = true; s.errors = {}; s.message = null; s.confirm = null;
      try {
        const { data } = await api.post('/kitchen/prepared', { menu_item_id: item.menu_item_id, date: this.date, quantity: s.add });
        s.add = ''; s.adding = false;
        await this.refresh();
        ui.toast(item.name + ': ' + data.added + ' added, ' + data.total_prepared + ' prepared');
        if (data.auto_accepted) ui.toast(item.name + ': plan of ' + data.auto_accepted.final_qty + ' approved', 'info');
      } catch (e) { s.errors = e.fields || {}; s.message = e.fields && e.fields.quantity ? 'Enter a whole number of portions (1 or more).' : (e.fields && e.fields.date ? 'Date ' + e.fields.date + '.' : ui.errorText(e)); } finally { s.busy = false; }
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
        s.confirm = null;
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
