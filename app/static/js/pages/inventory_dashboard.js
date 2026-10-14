SR.createApp({
  data() { return { d: null, alerts: [], today: ui.todayIso(), loading: true, error: null, ui }; },
  async mounted() { await this.load(); },
  computed: {
    t() { return this.d.totals; },
    stockTotal() { return this.d ? this.d.counts.ok + this.d.counts.low + this.d.counts.out : 0; },
    expiryTotal() { return this.d ? this.d.totals.expired_batches + this.d.totals.expiring_batches : 0; },
    // the ingredients whose 7-day need is above usable stock, most short first (the full list is on Ingredient demand)
    risks() { return this.d ? this.d.need_vs_stock.filter(r => Number(r.need) > Number(r.usable)) : []; },
    // What needs attention, what the system recommends, and the page that handles it. Plain rules over the counts
    // above; nothing is calculated anew.
    actions() {
      const d = this.d, t = this.t, out = [], s = (n, one, many) => n + ' ' + (n === 1 ? one : many);
      if (d.pending_requests) out.push({ key: 'req', tone: 'warning', title: s(d.pending_requests, 'kitchen request waits', 'kitchen requests wait'),
        detail: 'Approve and issue the stock, or reject with a reason.', action: 'Kitchen requests', href: '/inventory/requests' });
      if (t.approved_requests) out.push({ key: 'issue', tone: 'info', title: s(t.approved_requests, 'approved request is', 'approved requests are') + ' not issued yet',
        detail: 'Issue the stock; the earliest expiry goes first.', action: 'Issue stock', href: '/inventory/requests' });
      if (t.expired_batches) out.push({ key: 'exp', tone: 'danger', title: s(t.expired_batches, 'expired batch is', 'expired batches are') + ' still in stock',
        detail: 'Expired stock is not usable. Record it as wastage.', action: 'Record wastage', href: '/inventory/stock?tab=record' });
      if (t.reorder) out.push({ key: 'reorder', tone: d.counts.out ? 'danger' : 'warning', title: s(t.reorder, 'ingredient needs', 'ingredients need') + ' reordering',
        detail: 'Create purchase orders with the suggested quantities.', action: 'Reorder', href: '/inventory/reorder' });
      if (t.po_draft) out.push({ key: 'draft', tone: 'info', title: s(t.po_draft, 'purchase order is', 'purchase orders are') + ' still a draft',
        detail: 'Mark it as sent once it is ordered from the supplier.', action: 'Purchase orders', href: '/inventory/reorder?tab=orders' });
      if (t.po_awaiting) out.push({ key: 'receive', tone: 'info', title: s(t.po_awaiting, 'purchase order awaits', 'purchase orders await') + ' delivery',
        detail: 'Receive the stock when it arrives, with its expiry date.', action: 'Receive', href: '/inventory/reorder?tab=orders' });
      if (t.expiring_batches) out.push({ key: 'soon', tone: 'warning', title: s(t.expiring_batches, 'batch expires', 'batches expire') + ' within 3 days',
        detail: 'Issue these first.', action: 'Stock levels', href: '/inventory/stock' });
      return out;
    },
  },
  methods: {
    async load() {
      this.loading = true; this.error = null;
      try { this.d = (await api.get('/dashboards/inventory')).data; } catch (e) { this.d = null; this.error = ui.errorText(e); } finally { this.loading = false; }
      // After the dashboard (never in parallel) so the alert check runs once.
      if (this.d) { try { this.alerts = (await api.get('/alerts', { status: 'open' })).data; } catch (e) { this.alerts = this.d.alerts; } }
    },
    cover(r) { return Number(r.need) ? Math.max(0, Math.min(100, Math.round(Number(r.usable) / Number(r.need) * 100))) : 100; },
    async ack(a) { try { await api.post('/alerts/' + a.id + '/acknowledge'); await this.load(); } catch (e) { ui.toast(ui.errorText(e), 'danger'); } },
  },
}).mount('#app');
