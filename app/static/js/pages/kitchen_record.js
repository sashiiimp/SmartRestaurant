SR.createApp({
  data() {
    return {
      date: ui.todayIso(), items: [], loading: true, error: null, ui,
      tab: 'day', tabs: [{ id: 'day', label: 'Daily record' }, { id: 'ingredients', label: 'Ingredient usage' }],
      served: {}, savingServed: false, servedErrors: {}, conflicts: null, servedMessages: [],
      open: null,
      waste: { menu_item_id: '', quantity: '', reason: 'overproduction', note: '' }, wasteErrors: {}, savingWaste: false,
      usage: null, use: {}, usageErrors: {}, allIngredients: [], otherIng: '',
      foodUsage: null, usageTypes: ['staff_meal', 'complimentary', 'sample', 'other'],
      food: { menu_item_id: '', usage_type: 'staff_meal', quantity: '', note: '' }, foodErrors: {}, savingFood: false,
    };
  },
  async mounted() {
    // A link such as /kitchen/record#ingredients opens that tab, also when only the address hash changes. The earlier
    // addresses #balance, #served, #waste and #other open the daily record, where the balance now is.
    const fromHash = () => {
      const h = location.hash.slice(1);
      if (this.tabs.some(t => t.id === h)) this.tab = h;
      else if (['balance', 'served', 'waste', 'other'].includes(h)) {
        this.tab = 'day';
        this.$nextTick(() => setTimeout(() => { const el = document.getElementById('sec-served'); if (el) el.scrollIntoView({ block: 'start' }); }, 300));
      }
    };
    fromHash();
    window.addEventListener('hashchange', fromHash);
    try { this.allIngredients = (await api.get('/ingredients', { active: true })).data; } catch (e) { /* the rest of the page still works */ }
    await this.load();
  },
  computed: {
    // column totals (display only; the saved figures come from the daily summary)
    totals() {
      const bal = this.items.map(i => this.balance(i)).filter(b => b !== null);
      return { prepared: this.items.reduce((t, i) => t + num(i.prepared), 0), wasted: this.items.reduce((t, i) => t + num(i.wasted), 0),
               other: this.items.reduce((t, i) => t + num(i.other_use), 0),
               served: this.items.reduce((t, i) => t + num(this.servedValue(i)), 0),
               balance: bal.length ? bal.reduce((t, b) => t + b, 0) : null };
    },
    status() {
      return { served: this.items.filter(i => saved(i.served)).length, servedDone: this.items.length > 0 && this.items.every(i => saved(i.served)),
               warnings: this.items.filter(i => this.rowWarn(i)).length };
    },
    dirtyCount() { return this.items.filter(i => this.isDirty(i)).length; },
    // the other-use figure the form would replace (one per item, day and type)
    replacing() { return this.foodEntry(this.open, this.food.usage_type); },
    otherIngredients() { const shown = new Set(this.usage ? this.usage.rows.map(r => r.ingredient_id) : []); return this.allIngredients.filter(g => !shown.has(g.id)); },
  },
  methods: {
    setTab(id) { this.tab = id; history.replaceState(null, '', '#' + id); },
    moveTab(step) {
      const i = this.tabs.findIndex(t => t.id === this.tab);
      const next = this.tabs[(i + step + this.tabs.length) % this.tabs.length].id;
      this.setTab(next);
      this.$nextTick(() => document.getElementById('tab-' + next).focus());
    },
    // keep=true reloads the figures after a waste or other-use entry without dropping served quantities typed but not saved
    async load(keep) {
      const drafts = keep === true ? Object.fromEntries(this.items.filter(i => this.isDirty(i)).map(i => [i.menu_item_id, this.served[i.menu_item_id]])) : {};
      if (keep !== true) { this.loading = true; this.open = null; }
      this.error = null; this.conflicts = null; this.servedMessages = [];
      try {
        const { data } = await api.get('/kitchen/daily-summary', { date: this.date });
        this.items = data.items;
        this.served = {};
        data.items.forEach(i => { this.served[i.menu_item_id] = i.menu_item_id in drafts ? drafts[i.menu_item_id] : (saved(i.served) ? String(i.served) : ''); });
      } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
      await this.loadUsage();
      await this.loadFood();
    },
    // ---- one row per item ----
    servedValue(i) {
      const v = this.served[i.menu_item_id];
      if (v !== '' && v !== undefined && !isNaN(Number(v))) return Number(v);
      return saved(i.served) ? i.served : null;     // blank skips the item, so the saved figure stays
    },
    isDirty(i) { const v = this.served[i.menu_item_id]; return v !== '' && v !== undefined && v !== (saved(i.served) ? String(i.served) : ''); },
    // prepared = served + waste + other use + balance, as in the daily balance (kitchen_service._balance_row);
    // unknown until served is entered
    balance(i) { const s = this.servedValue(i); return s === null ? null : num(i.prepared) - s - num(i.wasted) - num(i.other_use); },
    balanceText(i) { const b = this.balance(i); return b === null ? '-' : (b > 0 ? String(b) : b < 0 ? '−' + Math.abs(b) : '0'); },
    balanceClass(i) {
      const b = this.balance(i);
      return ['rec-b', b === null ? 'is-none' : b < 0 ? 'is-neg' : b === 0 ? 'is-ok' : 'is-left', this.isDirty(i) ? 'is-draft' : ''];
    },
    balanceTitle(i) {
      const b = this.balance(i);
      if (b === null) return 'Enter served to see the balance';
      if (b < 0) return Math.abs(b) + ' more used than prepared';
      return b ? b + ' prepared but not accounted for' : 'Everything prepared is accounted for';
    },
    rowWarn(i) { const b = this.balance(i); return (b !== null && b < 0) || i.flags.length > 0; },
    rowState(i) {
      if (this.isDirty(i)) return 'dirty';
      if (i.flags.length || (this.balance(i) !== null && this.balance(i) < 0)) return 'warn';
      return saved(i.served) ? 'saved' : 'none';
    },
    stateText(i) {
      const s = this.rowState(i);
      if (s === 'dirty') return 'Not saved yet';
      if (s === 'warn') {
        if (i.flags.includes('served_exceeds_prepared')) return 'Served above prepared';
        if (i.flags.includes('waste_exceeds_prepared')) return 'Waste above prepared';
        return 'More used than prepared';
      }
      if (s === 'saved') return 'Recorded';
      return num(i.prepared) ? 'Not recorded' : 'Nothing prepared';
    },
    // ---- waste and other use for one item, in the panel under its row ----
    toggle(i) {
      if (this.open === i.menu_item_id) { this.open = null; return; }
      this.open = i.menu_item_id; this.wasteErrors = {}; this.foodErrors = {};
      this.waste = { menu_item_id: i.menu_item_id, quantity: '', reason: 'overproduction', note: '' };
      this.food = { menu_item_id: i.menu_item_id, usage_type: 'staff_meal', quantity: '', note: '' };
      this.prefillFood();
      this.$nextTick(() => {
        // where items are cards (below 1200 px) the item moves to the top so its panel is not hidden under the save bar
        const row = document.getElementById('rec-' + i.menu_item_id);
        if (row && window.matchMedia('(max-width: 1199.98px)').matches) row.previousElementSibling.scrollIntoView({ block: 'start', behavior: 'smooth' });
        const el = document.getElementById('w-qty'); if (el) el.focus({ preventScroll: true });
      });
    },
    itemEntries(i) { return this.foodUsage ? this.foodUsage.entries.filter(e => e.menu_item_id === i.menu_item_id) : []; },
    foodEntry(itemId, type) { return this.foodUsage && itemId ? this.foodUsage.entries.find(e => e.menu_item_id === itemId && e.usage_type === type) || null : null; },
    prefillFood() { const e = this.foodEntry(this.food.menu_item_id, this.food.usage_type); this.food.quantity = e ? String(e.quantity) : ''; this.food.note = e && e.note ? e.note : ''; },
    editFood(e) {
      this.food.usage_type = e.usage_type; this.prefillFood();
      this.$nextTick(() => { const el = document.getElementById('u-qty'); if (el) { el.focus(); el.select(); } });
    },
    usageLabel(t) { return { staff_meal: 'Staff meal', complimentary: 'Complimentary', sample: 'Tasting sample', other: 'Other' }[t] || t; },
    async loadFood() {
      try { this.foodUsage = (await api.get('/kitchen/food-usage', { date: this.date })).data; }
      catch (e) { this.foodUsage = null; ui.toast(ui.errorText(e), 'danger'); }
    },
    async saveFood() {
      this.savingFood = true; this.foodErrors = {};
      try {
        const res = await api.post('/kitchen/food-usage', { date: this.date, ...this.food, note: this.food.note || undefined });
        ui.toast(res.data.item + ': ' + this.usageLabel(res.data.usage_type).toLowerCase() + ' ' + res.data.quantity + ' recorded.');
        if (res.meta && res.meta.warnings && res.meta.warnings.length) ui.toast(res.meta.warnings[0], 'warning');
        await this.load(true);
        this.prefillFood();
      } catch (e) { this.foodErrors = e.fields || {}; if (!Object.keys(this.foodErrors).length) ui.toast(ui.errorText(e), 'danger'); }
      finally { this.savingFood = false; }
    },
    async clearFood(e) {
      try {
        await api.delete('/kitchen/food-usage/' + e.usage_id); ui.toast(e.item + ': ' + this.usageLabel(e.usage_type).toLowerCase() + ' cleared.');
        await this.load(true);
        this.prefillFood();
      } catch (err) { ui.toast(ui.errorText(err), 'danger'); }
    },
    async saveWaste() {
      this.savingWaste = true; this.wasteErrors = {};
      try {
        const { data } = await api.post('/kitchen/waste', { date: this.date, ...this.waste });
        ui.toast('Waste recorded (' + data.total_waste + ' today).');
        if (data.warnings.length) ui.toast(data.warnings[0], 'warning');
        this.waste.quantity = ''; this.waste.note = '';
        await this.load(true);
      } catch (e) { this.wasteErrors = e.fields || {}; if (!Object.keys(this.wasteErrors).length) ui.toast(ui.errorText(e), 'danger'); }
      finally { this.savingWaste = false; }
    },
    // ---- served, saved for all items at once ----
    async saveServed(confirm) {
      this.savingServed = true; this.servedErrors = {}; this.servedMessages = [];
      const lines = this.items.filter(i => this.served[i.menu_item_id] !== '').map(i => ({ menu_item_id: i.menu_item_id, quantity: this.served[i.menu_item_id] }));
      try {
        const { data } = await api.post('/sales/served', { date: this.date, lines, confirm_overwrite: !!confirm });
        this.conflicts = null; this.servedMessages = data.warnings;
        ui.toast('Served quantities saved (' + data.saved + ' changed).');
        await this.load(true); this.servedMessages = data.warnings;
      } catch (e) {
        if (e.code === 'duplicate_record') this.conflicts = e.conflicts || [];
        else { this.servedErrors = e.fields || {}; this.servedMessages = [ui.errorText(e)]; }
      } finally { this.savingServed = false; }
    },
    // ---- ingredient usage ----
    async loadUsage() {
      try {
        const u = (await api.get('/kitchen/ingredient-usage', { date: this.date })).data;
        this.use = {}; this.usageErrors = {};
        u.rows.forEach(r => { this.use[r.ingredient_id] = { quantity: r.recorded === null ? '' : String(r.recorded), note: r.note || '' }; });
        this.usage = u;
      } catch (e) { this.usage = null; ui.toast(ui.errorText(e), 'danger'); }
    },
    addOther() {
      const g = this.allIngredients.find(x => x.id === this.otherIng); if (!g) return;
      this.use[g.id] = { quantity: '', note: '' };
      this.usage.rows.push({ ingredient_id: g.id, ingredient: g.name, unit: g.unit, expected: 0, recorded: null, variance: null, note: null, usage_id: null });
      this.otherIng = '';
    },
    async saveUsage(r) {
      const f = this.use[r.ingredient_id]; this.usageErrors[r.ingredient_id] = '';
      if (f.quantity === '') { this.usageErrors[r.ingredient_id] = 'Enter the amount used.'; return; }
      try { await api.post('/kitchen/ingredient-usage', { date: this.date, ingredient_id: r.ingredient_id, quantity: f.quantity, note: f.note || undefined }); ui.toast(r.ingredient + ': usage recorded.'); await this.loadUsage(); }
      catch (e) { this.usageErrors[r.ingredient_id] = Object.values(e.fields || {}).join('; ') || ui.errorText(e); }
    },
    async clearUsage(r) {
      try { await api.delete('/kitchen/ingredient-usage/' + r.usage_id); ui.toast(r.ingredient + ': back to the expected usage.'); await this.loadUsage(); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
  },
}).mount('#app');

function num(v) { return v === '' || v === null || v === undefined || isNaN(Number(v)) ? 0 : Number(v); }
function saved(v) { return v !== null && v !== undefined; }
