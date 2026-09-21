SR.createApp({
  data() { return { users: [], loading: true, error: null, form: null, errors: {}, saving: false, ui }; },
  async mounted() { await this.load(); },
  methods: {
    async load() {
      this.loading = true;
      try { this.users = (await api.get('/users')).data; } catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
    },
    add() { this.form = { full_name: '', username: '', email: '', role: 'kitchen', password: '' }; this.errors = {}; },
    async create() {
      this.saving = true; this.errors = {};
      try { await api.post('/users', this.form); ui.toast('User created.'); this.form = null; await this.load(); }
      catch (e) { this.errors = e.fields || {}; if (e.code === 'duplicate_record') this.errors = { username: e.message }; else if (!Object.keys(this.errors).length) ui.toast(ui.errorText(e), 'danger'); }
      finally { this.saving = false; }
    },
    async change(u, changes) {
      try { await api.patch('/users/' + u.id, changes); ui.toast('Saved.'); }
      catch (e) { ui.toast(ui.errorText(e), 'danger'); }
      await this.load();
    },
    toggle(u) {
      if (u.is_active && !confirm('Deactivate ' + u.username + '? They will no longer be able to log in.')) return;
      this.change(u, { is_active: !u.is_active });
    },
  },
}).mount('#app');
