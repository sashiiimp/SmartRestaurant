#!/usr/bin/env bash
# Fetch front-end libraries once and commit them (no CDN at demo time). Versions are pinned here.
set -euo pipefail
cd "$(dirname "$0")/../app/static/vendor"
BS=5.3.3; VUE=3.5.13; CJS=4.4.7
curl -fsSL "https://cdn.jsdelivr.net/npm/bootstrap@$BS/dist/css/bootstrap.min.css" -o bootstrap.min.css
curl -fsSL "https://cdn.jsdelivr.net/npm/bootstrap@$BS/dist/js/bootstrap.bundle.min.js" -o bootstrap.bundle.min.js
curl -fsSL "https://cdn.jsdelivr.net/npm/vue@$VUE/dist/vue.global.prod.js" -o vue.global.prod.js
curl -fsSL "https://cdn.jsdelivr.net/npm/chart.js@$CJS/dist/chart.umd.js" -o chart.umd.js
printf 'bootstrap %s\nvue %s\nchart.js %s\n' "$BS" "$VUE" "$CJS" > VERSIONS.txt
ls -la
