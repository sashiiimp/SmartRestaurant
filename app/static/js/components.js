/* Shared Vue components (UI_PLAN section 2). Templates use [[ ]] because Jinja owns {{ }}. */
window.SR = (function () {
  const components = {
    'sr-status-badge': {
      props: ['status'],
      computed: {
        cls() { return { ok: 'success', sufficient: 'success', accepted: 'success', low: 'warning', warning: 'warning', suggested: 'primary', overridden: 'warning', short: 'danger', out: 'danger', critical: 'danger', open: 'danger', no_forecast: 'secondary', acknowledged: 'secondary' }[this.status] || 'secondary'; },
        text() { return { no_forecast: 'no forecast', sufficient: 'sufficient' }[this.status] || this.status; },
      },
      template: '<span :class="\'badge text-bg-\' + cls">[[ text ]]</span>',
    },
    'sr-stat-tile': {
      props: ['label', 'value', 'hint', 'tone', 'href'],
      template: `<div class="card stat-tile h-100"><div class="card-body py-2">
        <div class="text-muted small">[[ label ]]</div>
        <div class="value" :class="tone ? 'text-' + tone : ''"><a v-if="href" :href="href" class="text-reset text-decoration-none">[[ value ]]</a><span v-else>[[ value ]]</span></div>
        <div v-if="hint" class="text-muted small">[[ hint ]]</div></div></div>`,
    },
    'sr-field-error': {
      props: ['errors', 'name'],
      template: '<div v-if="errors && errors[name]" class="text-danger small mt-1" role="alert">[[ errors[name] ]]</div>',
    },
    'sr-empty': {
      props: ['message'],
      template: '<div class="text-center text-muted py-4">[[ message ]]</div>',
    },
    'sr-date-nav': {
      props: ['modelValue'],
      emits: ['update:modelValue', 'change'],
      methods: {
        set(v) { this.$emit('update:modelValue', v); this.$emit('change', v); },
        shift(n) { this.set(window.ui.addDays(this.modelValue, n)); },
        today() { this.set(window.ui.todayIso()); },
      },
      template: `<div class="d-flex align-items-center gap-2 flex-wrap">
        <button class="btn btn-outline-secondary btn-lg-touch" type="button" @click="shift(-1)" aria-label="Previous day">&lsaquo;</button>
        <input type="date" class="form-control" style="max-width: 11rem" :value="modelValue" @change="set($event.target.value)" aria-label="Date">
        <button class="btn btn-outline-secondary btn-lg-touch" type="button" @click="shift(1)" aria-label="Next day">&rsaquo;</button>
        <button class="btn btn-outline-primary btn-lg-touch" type="button" @click="today()">Today</button></div>`,
    },
    'sr-alert-list': {
      props: ['alerts'],
      emits: ['acknowledge'],
      template: `<div><sr-empty v-if="!alerts || !alerts.length" message="No open alerts."></sr-empty>
        <ul v-else class="list-group list-group-flush">
          <li v-for="a in alerts" :key="a.id" class="list-group-item d-flex justify-content-between align-items-start gap-2">
            <div><sr-status-badge :status="a.severity"></sr-status-badge> <span class="ms-1">[[ a.message ]]</span>
              <div class="text-muted small">[[ a.alert_type.replace('_', ' ') ]]<span v-if="a.status === 'acknowledged'"> &middot; acknowledged</span></div></div>
            <button v-if="a.status === 'open'" class="btn btn-sm btn-outline-secondary" type="button" @click="$emit('acknowledge', a)">Acknowledge</button>
          </li></ul></div>`,
    },
    'sr-line-chart': {
      props: ['labels', 'datasets', 'title', 'yTitle'],
      mounted() { this.draw(); },
      watch: { labels() { this.draw(); }, datasets: { deep: true, handler() { this.draw(); } } },
      beforeUnmount() { if (this.chart) this.chart.destroy(); },
      methods: {
        draw() {
          if (this.chart) this.chart.destroy();
          const colors = ['#0d6efd', '#fd7e14', '#198754', '#6f42c1'];
          this.chart = new Chart(this.$refs.canvas, {
            type: 'line',
            data: { labels: this.labels, datasets: (this.datasets || []).map((d, i) => ({ borderColor: colors[i % 4], backgroundColor: colors[i % 4], tension: 0.2, pointRadius: 3, ...d })) },
            options: { responsive: true, maintainAspectRatio: false, plugins: { title: { display: !!this.title, text: this.title } },
              scales: { y: { beginAtZero: true, title: { display: !!this.yTitle, text: this.yTitle } } } },
          });
        },
      },
      template: '<div style="position: relative; height: 280px"><canvas ref="canvas" role="img" :aria-label="title"></canvas></div>',
    },
    'sr-bar-chart': {
      props: ['labels', 'datasets', 'title', 'yTitle', 'stacked'],
      mounted() { this.draw(); },
      watch: { labels() { this.draw(); }, datasets: { deep: true, handler() { this.draw(); } } },
      beforeUnmount() { if (this.chart) this.chart.destroy(); },
      methods: {
        draw() {
          if (this.chart) this.chart.destroy();
          const colors = ['#0d6efd', '#fd7e14', '#198754', '#6f42c1'];
          this.chart = new Chart(this.$refs.canvas, {
            type: 'bar',
            data: { labels: this.labels, datasets: (this.datasets || []).map((d, i) => ({ backgroundColor: colors[i % 4], ...d })) },
            options: { responsive: true, maintainAspectRatio: false, plugins: { title: { display: !!this.title, text: this.title } },
              scales: { x: { stacked: !!this.stacked }, y: { beginAtZero: true, stacked: !!this.stacked, title: { display: !!this.yTitle, text: this.yTitle } } } },
          });
        },
      },
      template: '<div style="position: relative; height: 280px"><canvas ref="canvas" role="img" :aria-label="title"></canvas></div>',
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
