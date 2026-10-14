SR.createApp({
  data() { return { rows: [], noForecast: [], loading: true, error: null, message: null, selected: [], busy: false, ui }; },
  computed: {
    orderable() { return this.rows.filter(r => r.supplier_id); },
    allSelected() { return this.orderable.length > 0 && this.selected.length === this.orderable.length; },
    supplierCount() { return new Set(this.rows.filter(r => this.selected.includes(r.ingredient_id)).map(r => r.supplier_id)).size; },
  },
  async mounted() {
    try { const r = await api.get('/recommendations/reorder'); this.rows = r.data; this.noForecast = (r.meta && r.meta.items_without_forecast) || []; }
    catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
  },
  methods: {
    toggleAll(on) { this.selected = on ? this.orderable.map(r => r.ingredient_id) : []; },
    // one draft purchase order per supplier, built from the suggested quantities
    async createOrders() {
      this.busy = true; this.message = null;
      const bySupplier = {};
      this.rows.filter(r => this.selected.includes(r.ingredient_id)).forEach(r => {
        (bySupplier[r.supplier_id] = bySupplier[r.supplier_id] || []).push({ ingredient_id: r.ingredient_id, qty_ordered: r.suggested_qty });
      });
      const made = [];
      try {
        for (const [supplier_id, lines] of Object.entries(bySupplier)) {
          made.push((await api.post('/purchase-orders', { supplier_id: Number(supplier_id), lines })).data);
        }
      } catch (e) {
        this.message = (made.length ? made.length + ' order(s) were created before this problem. ' : '') + ui.errorText(e) + Object.values(e.fields || {}).join('; ');
        this.busy = false; return;
      }
      window.location = '/inventory/reorder?tab=orders' + (made.length === 1 ? '&open=' + made[0].id : '');
    },
  },
}).mount('#app');
