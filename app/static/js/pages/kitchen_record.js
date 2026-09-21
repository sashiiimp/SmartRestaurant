SR.createApp({
  data() {
    return {
      date: ui.todayIso(), items: [], loading: true, error: null, ui,
      served: {}, savingServed: false, servedErrors: {}, conflicts: null, servedMessages: [],
      waste: { menu_item_id: '', quantity: '', reason: 'overproduction', note: '' }, wasteErrors: {}, savingWaste: false,
    };
  },
  async mounted() { await this.load(); },
  methods: {
    async load() {
      this.loading = true; this.error = null; this.conflicts = null; this.servedMessages = [];
      try {
        const { data } = await api.get('/kitchen/daily-summary', { date: this.date });
        this.items = data.items;
        this.served = {};
        data.items.forEach(i => { this.served[i.menu_item_id] = i.served === null || i.served === undefined ? '' : String(i.served); });
        if (!this.waste.menu_item_id && data.items.length) this.waste.menu_item_id = data.items[0].menu_item_id;
      } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    async saveServed(confirm) {
      this.savingServed = true; this.servedErrors = {}; this.servedMessages = [];
      const lines = this.items.filter(i => this.served[i.menu_item_id] !== '').map(i => ({ menu_item_id: i.menu_item_id, quantity: this.served[i.menu_item_id] }));
      try {
        const { data } = await api.post('/sales/served', { date: this.date, lines, confirm_overwrite: !!confirm });
        this.conflicts = null; this.servedMessages = data.warnings;
        ui.toast('Served quantities saved (' + data.saved + ' changed).');
        await this.load(); this.servedMessages = data.warnings;
      } catch (e) {
        if (e.code === 'duplicate_record') this.conflicts = e.conflicts || [];
        else { this.servedErrors = e.fields || {}; this.servedMessages = [ui.errorText(e)]; }
      } finally { this.savingServed = false; }
    },
    async saveWaste() {
      this.savingWaste = true; this.wasteErrors = {};
      try {
        const { data } = await api.post('/kitchen/waste', { date: this.date, ...this.waste });
        ui.toast('Waste recorded (' + data.total_waste + ' today).');
        if (data.warnings.length) ui.toast(data.warnings[0], 'warning');
        this.waste.quantity = ''; this.waste.note = '';
        await this.load();
      } catch (e) { this.wasteErrors = e.fields || {}; if (!Object.keys(this.wasteErrors).length) ui.toast(ui.errorText(e), 'danger'); }
      finally { this.savingWaste = false; }
    },
  },
}).mount('#app');
