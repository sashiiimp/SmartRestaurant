// phones get a card list instead of the wide day-by-day table (only one is rendered)
const PHONE = '(max-width: 575.98px)';
SR.createApp({
  data() { return { f: null, loading: true, error: null, phone: window.matchMedia(PHONE).matches, ui }; },
  computed: { days() { return this.f ? Array.from({ length: this.f.days }, (_, i) => ui.addDays(this.f.from, i)) : []; },
              rows() { return this.f ? this.f.ingredients.filter(r => r.total_need > 0 || r.first_shortfall_date) : []; } },
  async mounted() {
    window.matchMedia(PHONE).addEventListener('change', e => { this.phone = e.matches; });
    try { this.f = (await api.get('/recommendations/ingredient-forecast', { from: ui.todayIso(), days: 7 })).data; }
    catch (e) { this.error = ui.errorText(e); } finally { this.loading = false; }
  },
}).mount('#app');
