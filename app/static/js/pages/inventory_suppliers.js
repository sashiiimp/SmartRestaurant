const BLANK = { id: null, name: '', contact_person: '', phone: '', email: '', lead_time_days: 2, notes: '' };
SR.createApp({
  data() { return { rows: [], loading: true, error: null, form: null, errors: {}, saving: false, ui }; },
  async mounted() { await this.load(); },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try { this.rows = (await api.get('/suppliers')).data; } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    add() { this.form = { ...BLANK }; this.errors = {}; },
    edit(r) { this.form = { ...r, contact_person: r.contact_person || '', phone: r.phone || '', email: r.email || '', notes: r.notes || '' }; this.errors = {}; },
    async save() {
      this.saving = true; this.errors = {};
      const f = this.form;
      const body = { name: f.name, contact_person: f.contact_person, phone: f.phone, email: f.email, lead_time_days: f.lead_time_days, notes: f.notes };
      try {
        if (f.id) await api.patch('/suppliers/' + f.id, body); else await api.post('/suppliers', body);
        ui.toast('Supplier saved.'); this.form = null; await this.load();
      } catch (e) { this.errors = e.fields || {}; if (!Object.keys(this.errors).length) ui.toast(ui.errorText(e), 'danger'); }
      finally { this.saving = false; }
    },
    async toggle(r) {
      if (r.is_active && !confirm('Deactivate ' + r.name + '? Existing ingredients and orders keep it, but it cannot be chosen for new ones.')) return;
      try { await api.patch('/suppliers/' + r.id, { is_active: !r.is_active }); await this.load(); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); }
    },
  },
}).mount('#app');
