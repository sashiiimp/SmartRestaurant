/* Shared Vue components (UI_PLAN section 2). Templates use [[ ]] because Jinja owns {{ }}.
   Visual design lives in css/app.css; nothing here changes data or behaviour. */
window.SR = (function () {
  const css = (name, fallback) => (getComputedStyle(document.body).getPropertyValue(name) || '').trim() || fallback;
  const palette = () => [css('--accent', '#4338ca'), '#e0a020', '#2f9e6b', '#64748b', '#c2410c', '#0e7490'];
  const hexToRgba = (hex, a) => {
    const m = /^#?([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(hex); if (!m) return hex;
    return `rgba(${parseInt(m[1], 16)}, ${parseInt(m[2], 16)}, ${parseInt(m[3], 16)}, ${a})`;
  };
  if (window.Chart) {
    Chart.defaults.font.family = css('--font', 'system-ui, sans-serif');
    Chart.defaults.font.size = 12;
    Chart.defaults.color = '#667085';
    Chart.defaults.borderColor = '#eef1f5';
    Chart.defaults.plugins.tooltip.backgroundColor = '#101828';
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
    Chart.defaults.plugins.tooltip.titleFont = { weight: '600' };
    Chart.defaults.animation.duration = 450;
    Object.assign(Chart.defaults.plugins.legend.labels, { usePointStyle: true, pointStyle: 'circle', boxWidth: 8, boxHeight: 8, padding: 16 });
  }
  const chartOptions = (self, extra) => ({
    responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
    plugins: {
      title: { display: !!self.title, text: self.title, align: 'start', color: '#182230', font: { size: 13, weight: '650' }, padding: { bottom: 14 } },
      legend: { display: (self.datasets || []).length > 1, position: 'bottom' },
    },
    ...extra,
  });
  const yScale = (self, stacked) => ({
    beginAtZero: true, stacked: !!stacked, border: { display: false }, grid: { color: '#eef1f5' }, ticks: { padding: 6, maxTicksLimit: 6 },
    title: { display: !!self.yTitle, text: self.yTitle, color: '#667085', font: { weight: '600', size: 11 } },
  });
  const chartHeight = (self) => ({ position: 'relative', height: (self.height || 280) + 'px' });

  const components = {
    'sr-icon': {
      props: { name: String, size: { type: [Number, String], default: 18 } },
      render() {
        const s = window.SRIcons.svg(this.name, this.size);
        return Vue.h('i', { class: 'sr-i', style: { width: this.size + 'px', height: this.size + 'px' }, innerHTML: s.outerHTML });
      },
    },
    'sr-status-badge': {
      props: ['status'],
      computed: {
        cls() { return { ok: 'success', sufficient: 'success', accepted: 'success', low: 'warning', warning: 'warning', suggested: 'accent', overridden: 'warning', short: 'danger', out: 'danger', critical: 'danger', open: 'danger', no_forecast: 'neutral', acknowledged: 'neutral', draft: 'neutral', pending: 'warning', approved: 'accent', issued: 'success', rejected: 'danger', sent: 'accent', partially_received: 'warning', received: 'success', cancelled: 'neutral' }[this.status] || 'neutral'; },
        text() { const t = { no_forecast: 'no forecast' }[this.status] || String(this.status || '').replace(/_/g, ' '); return t.charAt(0).toUpperCase() + t.slice(1); },
      },
      template: '<span :class="\'sr-badge sr-badge-\' + cls">[[ text ]]</span>',
    },
    'sr-stat-tile': {
      props: ['label', 'value', 'hint', 'tone', 'href', 'icon'],
      computed: { toneClass() { return 'tone-' + ({ success: 'success', warning: 'warning', danger: 'danger', info: 'info', neutral: 'neutral' }[this.tone] ? this.tone : 'accent'); } },
      template: `<div class="card stat-tile h-100" :class="toneClass"><div class="card-body">
        <div class="stat-top"><div class="stat-label">[[ label ]]</div><span v-if="icon" class="stat-icon"><sr-icon :name="icon" :size="18"></sr-icon></span></div>
        <div class="value" :class="{ 'value-long': String(value).length > 11 }"><a v-if="href" :href="href" class="stretched-link">[[ value ]]</a><span v-else>[[ value ]]</span></div>
        <div v-if="hint" class="stat-hint">[[ hint ]]</div></div></div>`,
    },
    'sr-field-error': {
      props: ['errors', 'name'],
      template: '<div v-if="errors && errors[name]" class="text-danger small mt-1" role="alert">[[ errors[name] ]]</div>',
    },
    'sr-empty': {
      props: { message: String, icon: { type: String, default: 'inbox' } },
      template: '<div class="sr-empty"><span class="empty-icon"><sr-icon :name="icon" :size="22"></sr-icon></span><p>[[ message ]]</p></div>',
    },
    'sr-loading': {
      props: { tiles: { type: Number, default: 0 }, cards: { type: Number, default: 1 } },
      template: `<div class="sr-loading" role="status" aria-live="polite"><span class="visually-hidden">Loading</span>
        <div v-if="tiles" class="row-tiles"><div v-for="n in tiles" :key="'t' + n" class="sk sk-tile"></div></div>
        <div v-for="n in cards" :key="'c' + n" class="sk sk-card"></div></div>`,
    },
    'sr-date-nav': {
      props: ['modelValue'],
      emits: ['update:modelValue', 'change'],
      methods: {
        set(v) { this.$emit('update:modelValue', v); this.$emit('change', v); },
        shift(n) { this.set(window.ui.addDays(this.modelValue, n)); },
        today() { this.set(window.ui.todayIso()); },
      },
      template: `<div class="date-nav">
        <button class="btn btn-outline-secondary btn-lg-touch btn-icon-only" type="button" @click="shift(-1)" aria-label="Previous day">&lsaquo;</button>
        <input type="date" class="form-control" style="max-width: 11rem" :value="modelValue" @change="set($event.target.value)" aria-label="Date">
        <button class="btn btn-outline-secondary btn-lg-touch btn-icon-only" type="button" @click="shift(1)" aria-label="Next day">&rsaquo;</button>
        <button class="btn btn-outline-primary btn-lg-touch" type="button" @click="today()">Today</button></div>`,
    },
    'sr-alert-list': {
      props: ['alerts'],
      emits: ['acknowledge'],
      methods: { icon(sev) { return { critical: 'alert', warning: 'warning' }[sev] || 'info'; } },
      template: `<div><sr-empty v-if="!alerts || !alerts.length" message="No open alerts." icon="check"></sr-empty>
        <div v-else>
          <div v-for="a in alerts" :key="a.id" class="alert-item" :class="['sev-' + a.severity, a.status === 'acknowledged' ? 'is-ack' : '']">
            <span class="sev-icon"><sr-icon :name="icon(a.severity)" :size="18"></sr-icon></span>
            <div class="flex-grow-1 min-w-0">
              <div class="alert-msg">[[ a.message ]]</div>
              <div class="alert-meta"><span class="sev-tag">[[ a.severity ]]</span><span>[[ a.alert_type.replace('_', ' ') ]]</span><span v-if="a.status === 'acknowledged'">&middot; acknowledged</span>
                <button v-if="a.status === 'open'" class="btn btn-sm btn-outline-secondary ms-auto" type="button" @click="$emit('acknowledge', a)">Acknowledge</button></div>
            </div>
          </div></div></div>`,
    },
    'sr-line-chart': {
      props: ['labels', 'datasets', 'title', 'yTitle', 'height'],
      mounted() { this.draw(); },
      watch: { labels() { this.draw(); }, datasets: { deep: true, handler() { this.draw(); } } },
      beforeUnmount() { if (this.chart) this.chart.destroy(); },
      methods: {
        draw() {
          if (this.chart) this.chart.destroy();
          const colors = palette();
          const sets = (this.datasets || []).map((d, i) => ({
            borderColor: colors[i % colors.length], backgroundColor: i === 0 ? hexToRgba(colors[0], 0.1) : colors[i % colors.length], fill: i === 0 && (this.datasets || []).length === 1,
            borderWidth: 2.25, tension: 0.3, pointRadius: 2.5, pointHoverRadius: 5, pointBackgroundColor: '#fff', pointBorderWidth: 2, ...d,
          }));
          this.chart = new Chart(this.$refs.canvas, {
            type: 'line', data: { labels: this.labels, datasets: sets },
            options: chartOptions(this, { scales: { x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 10 } }, y: yScale(this) } }),
          });
        },
      },
      template: '<div class="chart-wrap" :style="chartHeight"><canvas ref="canvas" role="img" :aria-label="title"></canvas></div>',
      computed: { chartHeight() { return chartHeight(this); } },
    },
    'sr-bar-chart': {
      props: ['labels', 'datasets', 'title', 'yTitle', 'stacked', 'height', 'horizontal', 'allLabels'],
      mounted() { this.draw(); },
      watch: { labels() { this.draw(); }, datasets: { deep: true, handler() { this.draw(); } } },
      beforeUnmount() { if (this.chart) this.chart.destroy(); },
      methods: {
        draw() {
          if (this.chart) this.chart.destroy();
          const colors = palette();
          const sets = (this.datasets || []).map((d, i) => ({ backgroundColor: colors[i % colors.length], borderRadius: 6, maxBarThickness: 34, borderSkipped: false, ...d }));
          const x = { stacked: !!this.stacked, grid: { display: false }, ticks: this.allLabels ? { autoSkip: false, maxRotation: 40, minRotation: 0 } : { maxRotation: 0, autoSkip: true, maxTicksLimit: 14 } };
          const y = yScale(this, this.stacked);
          this.chart = new Chart(this.$refs.canvas, {
            type: 'bar', data: { labels: this.labels, datasets: sets },
            options: chartOptions(this, this.horizontal ? { indexAxis: 'y', scales: { x: { ...y, grid: { color: '#eef1f5' } }, y: { ...x } } } : { scales: { x, y } }),
          });
        },
      },
      template: '<div class="chart-wrap" :style="chartHeight"><canvas ref="canvas" role="img" :aria-label="title"></canvas></div>',
      computed: { chartHeight() { return chartHeight(this); } },
    },
    'sr-doughnut-chart': {
      props: ['labels', 'data', 'colors', 'centerValue', 'centerLabel', 'title'],
      mounted() { this.draw(); },
      watch: { data: { deep: true, handler() { this.draw(); } } },
      beforeUnmount() { if (this.chart) this.chart.destroy(); },
      methods: {
        draw() {
          if (this.chart) this.chart.destroy();
          const total = (this.data || []).reduce((a, b) => a + Number(b || 0), 0);
          this.chart = new Chart(this.$refs.canvas, {
            type: 'doughnut',
            data: { labels: this.labels, datasets: [{ data: total ? this.data : [1], backgroundColor: total ? this.colors : ['#e9edf3'], borderWidth: 2, borderColor: '#fff', hoverOffset: 4 }] },
            options: { responsive: true, maintainAspectRatio: false, cutout: '72%', plugins: { legend: { display: false }, tooltip: { enabled: !!total } } },
          });
        },
      },
      template: `<div class="doughnut-box"><canvas ref="canvas" role="img" :aria-label="title"></canvas>
        <div class="doughnut-centre"><strong>[[ centerValue ]]</strong><span>[[ centerLabel ]]</span></div></div>`,
    },
    'sr-csv-import': {
      props: ['endpoint', 'extra', 'label'],
      data() { return { file: null, result: null, busy: false, error: null, conflict: 'skip' }; },
      methods: {
        pick(e) { this.file = e.target.files[0] || null; this.result = null; this.error = null; },
        async send(dry) {
          if (!this.file) { this.error = 'Choose a CSV file first.'; return; }
          this.busy = true; this.error = null;
          const fd = new FormData();
          fd.append('file', this.file); fd.append('dry_run', dry ? 'true' : 'false'); fd.append('on_conflict', this.conflict);
          try {
            const { data } = await window.api.post(this.endpoint, fd);
            this.result = data;
            if (!dry) window.ui.toast(data.accepted + ' rows saved.');
          } catch (e) { this.error = window.ui.errorText(e); } finally { this.busy = false; }
        },
      },
      template: `<div>
        <div class="row g-2 align-items-end">
          <div class="col-12 col-md-6"><label class="form-label">[[ label || 'CSV file' ]]</label>
            <input class="form-control" type="file" accept=".csv,text/csv" @change="pick"></div>
          <div class="col-6 col-md-3"><label class="form-label">If a row already exists</label>
            <select class="form-select" v-model="conflict"><option value="skip">Skip it</option><option value="overwrite">Overwrite it</option></select></div>
          <div class="col-6 col-md-3"><button class="btn btn-outline-primary w-100" type="button" :disabled="busy" @click="send(true)">Check file</button></div>
        </div>
        <div v-if="error" class="alert alert-danger mt-3" role="alert">[[ error ]]</div>
        <div v-if="result" class="mt-3">
          <div class="alert" :class="result.rejected ? 'alert-warning' : 'alert-success'" role="status">
            [[ result.accepted ]] rows accepted, [[ result.rejected ]] rejected<span v-if="result.skipped_unchanged">, [[ result.skipped_unchanged ]] unchanged</span>.
            <span v-if="result.dry_run"> Nothing has been saved yet.</span></div>
          <div class="table-responsive" v-if="result.errors.length" style="max-height: 16rem; overflow: auto">
            <table class="table table-sm"><thead><tr><th>Row</th><th>Field</th><th>Problem</th></tr></thead>
              <tbody><tr v-for="e in result.errors" :key="e.row + e.field"><td>[[ e.row ]]</td><td>[[ e.field ]]</td><td>[[ e.message ]]</td></tr></tbody></table>
          </div>
          <button v-if="result.dry_run && result.accepted" class="btn btn-primary" type="button" :disabled="busy" @click="send(false)">Save [[ result.accepted ]] rows</button>
        </div></div>`,
    },
  };

  function createApp(options) {
    const app = Vue.createApp(options);
    app.config.compilerOptions.delimiters = ['[[', ']]'];
    Object.entries(components).forEach(([name, def]) => app.component(name, def));
    return app;
  }
  return { createApp, components };
})();
