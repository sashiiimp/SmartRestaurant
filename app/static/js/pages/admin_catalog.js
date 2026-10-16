const BLANK = { id: null, name: '', category: '', price: '', batch_size: 1, shelf_life_hours: '', portion_unit: 'portion' };
SR.createApp({
  data() { return { items: [], ingredients: [], loading: true, error: null, form: null, errors: {}, saving: false, recipe: null, view: null, ui }; },
  computed: {
    activeCount() { return this.items.filter(i => i.is_active).length; },
    missingRecipes() { return this.items.filter(i => i.is_active && !i.has_recipe).length; },
    unavailableCount() { return this.items.filter(i => i.is_active && !i.is_available).length; },
  },
  async mounted() {
    try { this.items = (await api.get('/menu-items')).data; this.ingredients = (await api.get('/ingredients')).data; }
    catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    // ?item=<id> (from the BOM overview) opens that item's recipe in the editor; otherwise the first recipe is shown
    const wanted = this.items.find(i => String(i.id) === new URLSearchParams(location.search).get('item'));
    if (wanted) { await this.select(wanted); await this.openRecipe(wanted); this.$nextTick(() => { const el = document.querySelector('.recipe-panel'); if (el) el.scrollIntoView({ block: 'center' }); }); }
    else if (this.items.length) await this.select(this.items[0]);
  },
  methods: {
    async reload() {
      this.items = (await api.get('/menu-items')).data;
      if (this.view) { const again = this.items.find(i => i.id === this.view.item.id); if (again) await this.select(again); }
    },
    // read-only recipe panel; Edit recipe opens the editor below with the same lines
    toggle(i) { if (this.view && this.view.item.id === i.id) { this.view = null; this.recipe = null; } else this.select(i); },
    async select(i) {
      try { this.view = { item: i, lines: (await api.get('/menu-items/' + i.id + '/recipe')).data }; this.recipe = null; }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
    add() { this.form = { ...BLANK }; this.errors = {}; },
    edit(i) { this.form = { ...i, shelf_life_hours: i.shelf_life_hours || '' }; this.errors = {}; },
    async save() {
      this.saving = true; this.errors = {};
      const f = this.form, body = { name: f.name, category: f.category, price: f.price, batch_size: f.batch_size, shelf_life_hours: f.shelf_life_hours, portion_unit: f.portion_unit };
      try { if (f.id) await api.patch('/menu-items/' + f.id, body); else await api.post('/menu-items', body); ui.toast('Menu item saved.'); this.form = null; await this.reload(); }
      catch (e) { this.errors = e.fields || {}; if (!Object.keys(this.errors).length) ui.toast(ui.errorText(e), 'danger'); } finally { this.saving = false; }
    },
    async setActive(i, flag) {
      if (!flag && !confirm('Deactivate ' + i.name + '? It disappears from data entry and forecasts; its history is kept.')) return;
      try { await api.patch('/menu-items/' + i.id, { is_active: flag }); await this.reload(); } catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
    async openRecipe(i) {
      const { data } = await api.get('/menu-items/' + i.id + '/recipe');
      this.recipe = { item: i, lines: data.map(l => ({ ingredient_id: l.ingredient_id, quantity_per_portion: l.quantity_per_portion })), error: null };
    },
    unit(id) { const g = this.ingredients.find(x => x.id === id); return g ? g.unit : ''; },
    addLine() { this.recipe.lines.push({ ingredient_id: this.ingredients[0].id, quantity_per_portion: '' }); },
    async saveRecipe() {
      this.recipe.error = null;
      try { await api.put('/menu-items/' + this.recipe.item.id + '/recipe', { lines: this.recipe.lines }); ui.toast('Recipe saved.'); this.recipe = null; await this.reload(); }
      catch (e) { this.recipe.error = Object.values(e.fields || {}).join('; ') || ui.errorText(e); }
    },
  },
}).mount('#app');
