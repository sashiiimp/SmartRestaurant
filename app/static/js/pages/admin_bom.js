// BOM overview: read-only, from the same calls as Menu items (GET /menu-items, GET /menu-items/<id>/recipe).
// Editing stays in one place: "Edit recipe" opens the item's recipe editor on the Menu items tab.
SR.createApp({
  data() { return { items: [], open: [], filter: new URLSearchParams(location.search).get('q') || '', loading: true, error: null, ui }; },
  computed: {
    missing() { return this.items.filter(i => i.is_active && !i.lines.length).length; },
    usedIngredients() { return new Set(this.items.flatMap(i => i.lines.map(l => l.ingredient_id))).size; },
    // an item matches by its name or by any of its ingredients (so "Chicken" lists every item that uses chicken)
    shown() {
      const f = this.filter.trim().toLowerCase();
      if (!f) return this.items;
      return this.items.filter(i => i.name.toLowerCase().includes(f) || i.lines.some(l => l.ingredient.toLowerCase().includes(f)));
    },
  },
  async mounted() {
    try {
      const items = (await api.get('/menu-items')).data;
      const recipes = await Promise.all(items.map(i => (i.has_recipe ? api.get('/menu-items/' + i.id + '/recipe').then(r => r.data) : [])));
      // active items first, each group in the menu's order
      this.items = items.map((i, n) => ({ ...i, lines: recipes[n] })).sort((a, b) => Number(b.is_active) - Number(a.is_active));
    } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
  },
  methods: {
    // each recipe opens on its own; a search opens every item it finds, so the matching ingredient is in view
    isOpen(i) { return !!this.filter.trim() || this.open.includes(i.id); },
    toggle(i) { this.open = this.open.includes(i.id) ? this.open.filter(x => x !== i.id) : [...this.open, i.id]; },
    toggleAll() { this.open = this.open.length === this.items.length ? [] : this.items.map(i => i.id); },
    hit(name) { const f = this.filter.trim().toLowerCase(); return !!f && name.toLowerCase().includes(f); },
  },
}).mount('#app');
