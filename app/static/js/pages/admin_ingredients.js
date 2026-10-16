// Admin > Menu & Recipes (BOM) > Ingredients: the same ingredient list and form (sr-ingredient-form) as Inventory >
// Stock levels, plus which recipes use each ingredient (read from the recipes, nothing stored twice).
SR.createApp({
  data() { return { ingredients: [], suppliers: [], uses: {}, filter: '', form: null, loading: true, error: null, ui }; },
  computed: {
    shown() { const f = this.filter.trim().toLowerCase(); return this.ingredients.filter(g => !f || g.name.toLowerCase().includes(f)); },
  },
  async mounted() {
    try {
      const [ings, sups, items] = await Promise.all([api.get('/ingredients'), api.get('/suppliers'), api.get('/menu-items')]);
      this.ingredients = ings.data; this.suppliers = sups.data;
      const withRecipe = items.data.filter(i => i.has_recipe);
      const recipes = await Promise.all(withRecipe.map(i => api.get('/menu-items/' + i.id + '/recipe').then(r => r.data)));
      const uses = {};
      withRecipe.forEach((i, n) => recipes[n].forEach(l => { (uses[l.ingredient_id] = uses[l.ingredient_id] || []).push(i.name); }));
      this.uses = uses;
    } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
  },
  methods: {
    usedIn(g) { return this.uses[g.id] || []; },
    supplierName(id) { const s = this.suppliers.find(x => x.id === id); return s ? s.name : '-'; },
    openBom(g) { location.href = '/admin/catalog?tab=bom&q=' + encodeURIComponent(g.name); },
    async saved() { this.form = null; this.ingredients = (await api.get('/ingredients')).data; },
  },
}).mount('#app');
