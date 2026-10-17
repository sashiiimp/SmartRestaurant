/* Inline SVG icon set (24x24, 2px stroke, no external font or CDN). Display only.
   Static markup uses <i class="sr-i" data-icon="home"></i>; Vue pages use <sr-icon name="home"></sr-icon>. */
window.SRIcons = (function () {
  const circle = (cx, cy, r) => `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`;
  const ICONS = {
    home: ['M3 11.5 12 4l9 7.5', 'M5 10v10h5v-6h4v6h5V10'],
    activity: ['M3 12h4l3-8 4 16 3-8h4'],
    layers: ['M12 3 3 8l9 5 9-5-9-5z', 'M3 13l9 5 9-5'],
    database: ['M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z', 'M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6', 'M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3'],
    book: ['M2 5h6a4 4 0 0 1 4 4v11a3 3 0 0 0-3-3H2z', 'M22 5h-6a4 4 0 0 0-4 4v11a3 3 0 0 1 3-3h7z'],
    users: ['M16 20v-1.5a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4V20', circle(9.5, 8, 3.5), 'M21 20v-1.5a4 4 0 0 0-3-3.9', 'M15.5 4.6a3.5 3.5 0 0 1 0 6.8'],
    sliders: ['M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1', circle(15, 6, 2), circle(9, 12, 2), circle(17, 18, 2)],
    clipboard: ['M9 4h6v3H9z', 'M7 5H6a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-1', 'M8 12h8M8 16h5'],
    trending: ['M3 17l6-6 4 4 8-8', 'M15 7h6v6'],
    package: ['M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z', 'M4 7.5l8 4.5 8-4.5', 'M12 12v9'],
    leaf: ['M5 19c0-8.5 6-14 15-14 0 9-5.5 15-14 15', 'M5 19c2.5-4 6-7 10-9'],
    trash: ['M4 7h16', 'M9 7V4h6v3', 'M6 7l1 13h10l1-13', 'M10 11v6M14 11v6'],
    swap: ['M4 8h14l-3-3', 'M20 16H6l3 3'],
    refresh: ['M20 11a8 8 0 0 0-14.5-3.5L4 9', 'M4 4v5h5', 'M4 13a8 8 0 0 0 14.5 3.5L20 15', 'M20 20v-5h-5'],
    bars: ['M5 20V10M12 20V4M19 20v-7'],
    bell: ['M6 9a6 6 0 0 1 12 0c0 6 2 7 2 7H4s2-1 2-7', 'M10 20a2 2 0 0 0 4 0'],
    logout: ['M9 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h4', 'M16 8l4 4-4 4M20 12H9'],
    menu: ['M4 6h16M4 12h16M4 18h16'],
    x: ['M6 6l12 12M18 6 6 18'],
    warning: ['M12 4 2.5 20h19L12 4z', 'M12 10v4M12 17.5v.01'],
    alert: [circle(12, 12, 9), 'M12 8v5M12 16.5v.01'],
    info: [circle(12, 12, 9), 'M12 11v5M12 8v.01'],
    check: [circle(12, 12, 9), 'M8 12.5l3 3 5-6'],
    dollar: ['M12 3v18', 'M16.5 7.5C16 6 14.3 5 12 5S8 6 8 8s1.5 2.7 4 3.5 4 1.5 4 3.5-1.7 3-4 3-4-1-4.5-2.5'],
    bag: ['M6 7h12l1 13H5L6 7z', 'M9 10V6a3 3 0 0 1 6 0v4'],
    eye: ['M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z', circle(12, 12, 3)],
    eyeoff: ['M3 3l18 18', 'M10.6 6.1A9.8 9.8 0 0 1 12 5c6 0 10 7 10 7a17 17 0 0 1-3.2 4', 'M6.4 7.4C3.7 9.2 2 12 2 12s4 7 10 7c1.4 0 2.7-.3 3.8-.8', 'M9.9 9.9a3 3 0 0 0 4.2 4.2'],
    utensils: ['M6 3v7a2 2 0 0 0 2 2 2 2 0 0 0 2-2V3M8 3v18', 'M17 3c-2 1.5-3 4-3 7 0 2 1 3 3 3v8'],
    flame: ['M12 3c1 3 5 5 5 10a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-5 1-9z'],
    shield: ['M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6l8-3z', 'M9 12l2 2 4-4'],
    clock: [circle(12, 12, 9), 'M12 7v5l3 2'],
    flask: ['M9 3h6', 'M10 3v6L4.5 19a1.5 1.5 0 0 0 1.3 2.2h12.4a1.5 1.5 0 0 0 1.3-2.2L14 9V3', 'M7.5 15h9'],
    plus: ['M12 5v14M5 12h14'],
    inbox: ['M3 13l3-8h12l3 8', 'M3 13v6h18v-6', 'M3 13h5a4 4 0 0 0 8 0h5'],
    target: [circle(12, 12, 9), circle(12, 12, 5), circle(12, 12, 1)],
    user: ['M19 20v-1.5a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4V20', circle(12, 8, 3.5)],
    search: [circle(11, 11, 6.5), 'M16 16l4.5 4.5'],
    calendar: ['M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z', 'M4 10h16M8 3v4M16 3v4'],
    lock: ['M6.5 10.5h11a1.5 1.5 0 0 1 1.5 1.5v7a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 5 19v-7a1.5 1.5 0 0 1 1.5-1.5z', 'M8 10.5V7.5a4 4 0 0 1 8 0v3'],
    arrow: ['M5 12h14M13 6l6 6-6 6'],
    chevron: ['M9 6l6 6-6 6'],
    cart: ['M3 4h2l2.4 11h10.2L20 8H6.2', circle(9, 19.5, 1.2), circle(17, 19.5, 1.2)],
  };

  function svg(name, size) {
    const ns = 'http://www.w3.org/2000/svg';
    const el = document.createElementNS(ns, 'svg');
    el.setAttribute('viewBox', '0 0 24 24'); el.setAttribute('width', size || 18); el.setAttribute('height', size || 18);
    el.setAttribute('fill', 'none'); el.setAttribute('stroke', 'currentColor'); el.setAttribute('stroke-width', '2');
    el.setAttribute('stroke-linecap', 'round'); el.setAttribute('stroke-linejoin', 'round'); el.setAttribute('aria-hidden', 'true');
    (ICONS[name] || []).forEach(d => { const p = document.createElementNS(ns, 'path'); p.setAttribute('d', d); el.appendChild(p); });
    return el;
  }

  function hydrate(root) {
    (root || document).querySelectorAll('i.sr-i[data-icon]').forEach(i => {
      if (i.firstChild) return;
      i.appendChild(svg(i.dataset.icon, i.dataset.size));
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => hydrate());
  else hydrate();
  return { ICONS, svg, hydrate };
})();
