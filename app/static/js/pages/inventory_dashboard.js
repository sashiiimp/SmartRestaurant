SR.createApp({
  data() { return { d: null, alerts: [], reorder: null, today: ui.todayIso(), loading: true, error: null, ui }; },
  async mounted() { await this.load(); },
  computed: {
    stockTotal() { return this.d ? this.d.counts.ok + this.d.counts.low + this.d.counts.out : 0; },
    expiredCount() { return this.d ? this.d.expiring.filter(b => b.expired).length : 0; },
    // Only ingredients whose 7-day need is above usable stock; the full list is on Ingredient demand.
    chain() {
      const d = this.d, c = d.counts, exp = this.expiredCount, soon = d.expiring.length;
      const r = this.reorder ? this.reorder.length : null;
      return [
        { title: 'Historical sales', value: 'Administrator', mine: false, href: null, caption: 'past sales per menu item, the basis of the forecast', owner: 'Admin imports · kitchen records' },
        { title: 'ML demand forecast', value: 'Every day', mine: false, href: null, caption: 'predicts portions per menu item for the next 7 days', owner: 'ML model' },
        { title: 'Preparation recommendations', value: 'Kitchen', mine: false, href: null, caption: 'how much to prepare; drives the ingredient need', owner: 'Kitchen accepts or overrides' },
        { title: 'BOM & ingredient requirements', value: this.risks.length ? this.risks.length + ' at risk' : 'All covered', mine: true, href: '/inventory/reorder?tab=demand',
          tone: this.risks.length ? 'danger' : 'success', caption: '7-day need (forecast x recipes) against usable stock', owner: 'Inventory reviews' },
        { title: 'Inventory decisions', value: r === null ? (this.reorder === false ? '-' : 'loading') : (r ? r + ' to reorder' : 'Nothing to order'), mine: true, href: '/inventory/reorder',
          tone: c.out ? 'danger' : (c.low ? 'warning' : 'success'), caption: (c.low + c.out) + ' of ' + this.stockTotal + ' ingredients low or out · ' + d.pending_requests + ' kitchen request' + (d.pending_requests === 1 ? '' : 's'), owner: 'Inventory orders and issues' },
        { title: 'Food waste monitoring', value: exp ? exp + (soon >= 10 ? '+' : '') + ' expired' : (soon ? soon + ' expiring' : 'None expiring'), mine: true, href: '/inventory/stock?tab=record',
          tone: exp ? 'danger' : (soon ? 'warning' : 'success'), caption: 'record expired or damaged stock as inventory wastage', owner: 'Inventory records' },
      ];
    },
    risks() { return this.d ? this.d.need_vs_stock.filter(r => Number(r.need) > Number(r.usable)) : []; },
  },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try { this.d = (await api.get('/dashboards/inventory')).data; } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
      // After the dashboard (never in parallel) so the alert check runs once.
      if (this.d) { try { this.alerts = (await api.get('/alerts', { status: 'open' })).data; } catch (e) { this.alerts = this.d.alerts; } }
      // the dashboard lists the top 5 suggestions; the workflow strip counts all of them (read-only)
      if (this.d) { try { this.reorder = (await api.get('/recommendations/reorder')).data; } catch (e) { this.reorder = false; } }
    },
    cover(r) { return Number(r.need) ? Math.max(0, Math.min(100, Math.round(Number(r.usable) / Number(r.need) * 100))) : 100; },
    async ack(a) { try { await api.post('/alerts/' + a.id + '/acknowledge'); await this.load(); } catch (e) { ui.toast(ui.errorText(e), 'danger'); } },
  },
}).mount('#app');
