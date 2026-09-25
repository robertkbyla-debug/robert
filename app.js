(() => {
  "use strict";

  const SITE = window.SITE || {};
  const STORE_KEY = "cabinet:additions";
  const THEME_KEY = "cabinet:theme";
  const LISTS = ["artists", "winemakers", "quotes"];

  // ── Small helpers ─────────────────────────────────────────
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    }
    for (const c of children.flat()) {
      if (c == null || c === false) continue;
      node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }

  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : null);

  // Deterministic randomness: same name → same artwork every time.
  function hash(str) {
    let h = 1779033703 ^ str.length;
    for (let i = 0; i < str.length; i++) {
      h = Math.imul(h ^ str.charCodeAt(i), 3432918353);
      h = (h << 13) | (h >>> 19);
    }
    return h >>> 0;
  }
  function rng(seed) {
    let a = typeof seed === "number" ? seed : hash(String(seed));
    return () => {
      a |= 0;
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const pick = (r, arr) => arr[Math.floor(r() * arr.length)];

  function palette() {
    const cs = getComputedStyle(document.documentElement);
    const v = (n) => cs.getPropertyValue(n).trim();
    return {
      paper: v("--paper-2"),
      ink: v("--ink"),
      colors: [v("--wine"), v("--ochre"), v("--sage"), v("--indigo"), v("--rose")],
      // overlapping shapes darken on paper, glow in the dark
      blend: `mix-blend-mode:${cs.colorScheme.includes("dark") ? "screen" : "multiply"}`,
    };
  }

  // ── Local additions (browser storage) ─────────────────────
  function loadLocal() {
    try {
      const raw = JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
      return Object.fromEntries(LISTS.map((k) => [k, Array.isArray(raw[k]) ? raw[k] : []]));
    } catch {
      return { artists: [], winemakers: [], quotes: [] };
    }
  }
  function saveLocal(data) {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(data));
    } catch {
      /* storage blocked — additions last for this visit only */
    }
  }
  let local = loadLocal();

  const allOf = (kind) => [
    ...(SITE[kind] || []),
    ...local[kind].map((x) => ({ ...x, _local: true })),
  ];

  // ── Generative art ────────────────────────────────────────
  const SVG_NS = "http://www.w3.org/2000/svg";
  function svg(tag, attrs = {}) {
    const n = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    return n;
  }

  // Each artist gets a small abstract composition seeded by their name.
  function artistArt(seed) {
    const r = rng(seed);
    const P = palette();
    const W = 400, H = 500;
    const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "art", role: "img", "aria-hidden": "true" });
    root.append(svg("rect", { width: W, height: H, fill: P.paper }));
    const cols = [...P.colors].sort(() => r() - 0.5);
    const style = Math.floor(r() * 4);

    if (style === 0) {
      // stacked colour fields (Rothko-ish)
      const n = 2 + Math.floor(r() * 2);
      let y = 40;
      const gap = 18, h = (H - 80 - gap * (n - 1)) / n;
      for (let i = 0; i < n; i++) {
        root.append(svg("rect", {
          x: 36 + r() * 6, y: y + r() * 4, width: W - 72 - r() * 8, height: h,
          fill: cols[i % cols.length], opacity: 0.78 + r() * 0.2, rx: 6,
        }));
        y += h + gap;
      }
    } else if (style === 1) {
      // overlapping circles
      for (let i = 0; i < 4 + Math.floor(r() * 3); i++) {
        root.append(svg("circle", {
          cx: 60 + r() * (W - 120), cy: 60 + r() * (H - 120), r: 50 + r() * 110,
          fill: pick(r, cols), opacity: 0.55 + r() * 0.3,
          style: P.blend,
        }));
      }
    } else if (style === 2) {
      // fine grid with a few filled cells (Martin-ish)
      const step = 20 + Math.floor(r() * 16);
      for (let x = step; x < W; x += step)
        root.append(svg("line", { x1: x, y1: 0, x2: x, y2: H, stroke: P.ink, "stroke-opacity": 0.14 }));
      for (let y = step; y < H; y += step)
        root.append(svg("line", { x1: 0, y1: y, x2: W, y2: y, stroke: P.ink, "stroke-opacity": 0.14 }));
      for (let i = 0; i < 6 + Math.floor(r() * 6); i++) {
        root.append(svg("rect", {
          x: Math.floor(r() * (W / step)) * step, y: Math.floor(r() * (H / step)) * step,
          width: step * (1 + Math.floor(r() * 3)), height: step,
          fill: pick(r, cols), opacity: 0.7,
        }));
      }
    } else {
      // arcs and a horizon
      const cy = H * (0.45 + r() * 0.2);
      root.append(svg("rect", { x: 0, y: cy, width: W, height: H - cy, fill: cols[0], opacity: 0.85 }));
      root.append(svg("circle", { cx: W * (0.3 + r() * 0.4), cy, r: 60 + r() * 70, fill: cols[1] }));
      for (let i = 0; i < 5; i++) {
        root.append(svg("path", {
          d: `M ${-20} ${cy - 30 - i * 26} Q ${W / 2} ${cy - 120 - i * 40 - r() * 40} ${W + 20} ${cy - 30 - i * 26}`,
          fill: "none", stroke: P.ink, "stroke-opacity": 0.35, "stroke-width": 1.2,
        }));
      }
    }
    // a signature stroke
    root.append(svg("path", {
      d: `M ${W - 110} ${H - 36} c 14 -12 26 6 40 -4 s 24 -8 36 2`,
      fill: "none", stroke: P.ink, "stroke-opacity": 0.5, "stroke-width": 1.5, "stroke-linecap": "round",
    }));
    return root;
  }

  // A wine-glass ring stain for each winemaker's label.
  function stain(seed) {
    const r = rng(seed + "stain");
    const P = palette();
    const root = svg("svg", { viewBox: "0 0 120 120", class: "stain", "aria-hidden": "true" });
    const c = P.colors[0];
    root.append(svg("circle", { cx: 60, cy: 60, r: 44, fill: "none", stroke: c, "stroke-width": 5 + r() * 3, opacity: 0.35 }));
    root.append(svg("circle", { cx: 60 + r() * 4, cy: 60 + r() * 4, r: 41, fill: "none", stroke: c, "stroke-width": 1.5, opacity: 0.5, "stroke-dasharray": `${60 + r() * 80} ${10 + r() * 30}` }));
    root.append(svg("circle", { cx: 60, cy: 60, r: 44, fill: c, opacity: 0.06 }));
    return root;
  }

  // Hero composition — click to redraw.
  let heroSeed = hash(SITE.owner || "cabinet");
  function drawHero() {
    const host = $("#hero-art");
    if (!host) return;
    const r = rng(heroSeed);
    const P = palette();
    const S = 500;
    const root = svg("svg", { viewBox: `0 0 ${S} ${S}`, width: "100%", height: "100%" });
    const cols = [...P.colors].sort(() => r() - 0.5);

    root.append(svg("circle", { cx: S / 2, cy: S / 2, r: 210, fill: cols[0], opacity: 0.9 }));
    root.append(svg("rect", { x: 70 + r() * 60, y: 250 + r() * 40, width: 300, height: 160, fill: cols[1], opacity: 0.85, style: P.blend }));
    root.append(svg("circle", { cx: 150 + r() * 200, cy: 120 + r() * 80, r: 50 + r() * 30, fill: cols[2], style: P.blend }));
    for (let i = 0; i < 9; i++) {
      const y = 80 + i * 40;
      root.append(svg("line", { x1: 40, y1: y, x2: 40 + 120 + r() * 300, y2: y, stroke: P.ink, "stroke-opacity": 0.35, "stroke-width": 1 }));
    }
    root.append(svg("circle", { cx: S / 2, cy: S / 2, r: 238, fill: "none", stroke: P.ink, "stroke-opacity": 0.4, "stroke-width": 1 }));
    host.replaceChildren(root);
  }

  // ── Renderers ─────────────────────────────────────────────
  function removeButton(kind, item) {
    if (!item._local) return null;
    return el("button", {
      class: "remove",
      text: "remove",
      title: "Remove this browser-only entry",
      onclick: () => {
        local[kind] = local[kind].filter((x) => x.id !== item.id);
        saveLocal(local);
        renderAll();
      },
    });
  }

  function linkFor(item, label = "visit ↗") {
    const u = safeUrl(item.link);
    return u ? el("a", { href: u, target: "_blank", rel: "noopener", text: label }) : null;
  }

  const filters = { artists: null, winemakers: null };

  function renderChips(kind) {
    const host = $(`[data-chips="${kind}"]`);
    const tags = [...new Set(allOf(kind).flatMap((x) => x.tags || []))].sort();
    if (!tags.length) return host.replaceChildren();
    const chip = (label, value) =>
      el("button", {
        class: "chip",
        "aria-pressed": String(filters[kind] === value),
        text: label,
        onclick: () => {
          filters[kind] = filters[kind] === value ? null : value;
          renderList(kind);
          renderChips(kind);
        },
      });
    host.replaceChildren(chip("all", null), ...tags.map((t) => chip(t, t)));
  }

  function filtered(kind) {
    const f = filters[kind];
    return allOf(kind).filter((x) => !f || (x.tags || []).includes(f));
  }

  function artistCard(a) {
    return el("article", { class: "artist reveal" },
      artistArt(a.name),
      el("div", { class: "body" },
        el("h3", { text: a.name }),
        el("div", { class: "meta", text: [a.medium, a.era].filter(Boolean).join(" · ") }),
        a.why && el("p", { class: "why", text: a.why }),
        el("div", { class: "card-foot" },
          linkFor(a),
          a._local && el("span", { class: "local-badge", text: "● draft" }),
          removeButton("artists", a),
        ),
      ),
    );
  }

  function winemakerCard(w) {
    const dl = el("dl");
    if (w.grapes) dl.append(el("dt", { text: "Grapes" }), el("dd", { text: w.grapes }));
    if (w.favorite) dl.append(el("dt", { text: "The bottle" }), el("dd", { text: w.favorite }));
    return el("article", { class: "label reveal" },
      stain(w.name),
      el("div", { class: "estate", text: w.estate && w.estate !== w.name ? w.estate : "Vigneron" }),
      el("h3", { text: w.name }),
      el("div", { class: "region", text: [w.region, w.country].filter(Boolean).join(", ") }),
      el("div", { class: "rule" }),
      dl.children.length ? dl : null,
      w.why && el("p", { class: "why", text: w.why }),
      el("div", { class: "card-foot" },
        linkFor(w, "estate ↗"),
        w._local && el("span", { class: "local-badge", text: "● draft" }),
        removeButton("winemakers", w),
      ),
    );
  }

  function quoteCard(q) {
    const len = (q.text || "").length;
    const size = len < 50 ? "l" : len < 110 ? "m" : "s";
    const accent = pick(rng(q.text), palette().colors);
    return el("figure", { class: `quote ${size} reveal`, style: `--accent:${accent}` },
      el("span", { class: "mark", "aria-hidden": "true", text: "“" }),
      el("blockquote", { text: q.text }),
      el("figcaption", {},
        q.author ? `— ${q.author}` : "— unknown",
        q.source && el("cite", { text: q.source }),
        removeButton("quotes", q),
      ),
    );
  }

  const cardFor = { artists: artistCard, winemakers: winemakerCard, quotes: quoteCard };
  const emptyText = {
    artists: "No artists yet — add someone whose work stops you in your tracks.",
    winemakers: "The cellar is empty. Add a winemaker you love.",
    quotes: "No quotes yet. Add a line you keep coming back to.",
  };

  function renderList(kind) {
    const host = $(`[data-list="${kind}"]`);
    const items = kind === "quotes" ? allOf(kind) : filtered(kind);
    host.replaceChildren(
      ...(items.length ? items.map(cardFor[kind]) : [el("p", { class: "empty", text: emptyText[kind] })]),
    );
    observeReveals(host);
  }

  // Featured quote in the hero
  let quoteIndex = -1;
  function nextQuote() {
    const qs = allOf("quotes");
    const fig = $("#featured-quote");
    if (!qs.length) return (fig.hidden = true);
    fig.hidden = false;
    let i = Math.floor(Math.random() * qs.length);
    if (qs.length > 1 && i === quoteIndex) i = (i + 1) % qs.length;
    quoteIndex = i;
    const q = qs[i];
    fig.classList.add("fading");
    setTimeout(() => {
      $("blockquote", fig).textContent = q.text;
      $("figcaption", fig).textContent = [q.author || "unknown", q.source].filter(Boolean).join(", ");
      fig.classList.remove("fading");
    }, fig.dataset.ready ? 300 : 0);
    fig.dataset.ready = "1";
  }

  function renderHeader() {
    const owner = SITE.owner || "";
    $("#hero-owner").textContent = owner ? `The inspirations of ${owner}` : "Inspirations";
    const title = SITE.title || "Cabinet of Inspiration";
    const words = title.split(" ");
    const last = words.pop();
    $("#hero-title").replaceChildren(words.join(" ") + (words.length ? " " : ""), el("em", { text: last }));
    $("#hero-intro").textContent = SITE.intro || "";
    $("#brand").textContent = owner ? owner[0] + "." : "✦";
    $("#footer-owner").textContent = owner || "me";
    document.title = owner ? `${title} — ${owner}` : title;
  }

  function renderCount() {
    const n = (k) => allOf(k).length;
    $("#footer-count").textContent =
      `${n("artists")} artists · ${n("winemakers")} winemakers · ${n("quotes")} quotes`;
  }

  function renderAll() {
    renderHeader();
    renderChips("artists");
    renderChips("winemakers");
    LISTS.forEach(renderList);
    renderCount();
  }

  // ── Scroll reveal ─────────────────────────────────────────
  const io = "IntersectionObserver" in window
    ? new IntersectionObserver((entries) => {
        for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      }, { rootMargin: "0px 0px -8% 0px" })
    : null;
  function observeReveals(root) {
    $$(".reveal", root).forEach((n, i) => {
      n.style.transitionDelay = `${Math.min(i, 6) * 60}ms`;
      io ? io.observe(n) : n.classList.add("in");
    });
  }

  // ── Add dialog ────────────────────────────────────────────
  const FIELDS = {
    artists: [
      ["name", "Name", true], ["medium", "Medium (painting, photography…)"], ["era", "Years / era"],
      ["why", "Why they move you", false, true], ["link", "Link (website, Instagram…)"], ["tags", "Tags, comma separated"],
    ],
    winemakers: [
      ["name", "Winemaker", true], ["estate", "Estate / domaine"], ["region", "Region"], ["country", "Country"],
      ["grapes", "Grapes"], ["favorite", "Favorite bottle"], ["why", "Why you love their wine", false, true],
      ["link", "Link"], ["tags", "Tags, comma separated"],
    ],
    quotes: [
      ["text", "Quote", true, true], ["author", "Who said it"], ["source", "Source (book, film, song…)"],
    ],
  };
  const TITLES = { artists: "Add an artist", winemakers: "Add a winemaker", quotes: "Add a quote" };

  let addingKind = null;
  const addDialog = $("#add-dialog");

  function openAdd(kind) {
    addingKind = kind;
    $("#add-title").textContent = TITLES[kind];
    $("#add-fields").replaceChildren(
      ...FIELDS[kind].map(([key, label, required, long]) =>
        el("label", {}, label,
          el(long ? "textarea" : "input", {
            name: key, required: required || null, rows: long ? 3 : null,
            type: key === "link" ? "url" : null,
            placeholder: key === "link" ? "https://" : null,
          }),
        ),
      ),
    );
    addDialog.showModal();
    $("input, textarea", addDialog)?.focus();
  }

  $("#add-form").addEventListener("submit", (e) => {
    if (e.submitter?.value !== "save") return;
    const data = Object.fromEntries(new FormData(e.target).entries());
    const item = { id: Date.now().toString(36) };
    for (const [k, v] of Object.entries(data)) {
      const val = String(v).trim();
      if (!val) continue;
      item[k] = k === "tags" ? val.split(",").map((t) => t.trim().toLowerCase()).filter(Boolean) : val;
    }
    local[addingKind].push(item);
    saveLocal(local);
    renderAll();
    if (addingKind === "quotes") nextQuote();
    document.getElementById(addingKind).scrollIntoView();
  });

  $$("[data-add]").forEach((b) => b.addEventListener("click", () => openAdd(b.dataset.add)));

  // ── Export dialog ─────────────────────────────────────────
  function exportText() {
    const blocks = LISTS.filter((k) => local[k].length).map((k) => {
      const items = local[k].map(({ id, ...rest }) => JSON.stringify(rest, null, 2).replace(/^/gm, "    "));
      return `  // → paste into ${k}: [ ... ]\n${items.join(",\n")},`;
    });
    return blocks.length ? blocks.join("\n\n") : "// Nothing added in this browser yet.";
  }
  $("#export-btn").addEventListener("click", () => {
    $("#export-text").value = exportText();
    $("#export-dialog").showModal();
  });
  $("#copy-export").addEventListener("click", (e) => {
    e.preventDefault();
    navigator.clipboard?.writeText($("#export-text").value);
    e.target.textContent = "copied ✓";
    setTimeout(() => (e.target.textContent = "copy"), 1500);
  });
  $("#clear-local").addEventListener("click", (e) => {
    if (!confirm("Remove every entry saved only in this browser?")) return e.preventDefault();
    local = { artists: [], winemakers: [], quotes: [] };
    saveLocal(local);
    renderAll();
    nextQuote();
  });

  // ── Theme ─────────────────────────────────────────────────
  function applyTheme(t) {
    if (t) document.documentElement.dataset.theme = t;
    else delete document.documentElement.dataset.theme;
  }
  try { applyTheme(localStorage.getItem(THEME_KEY)); } catch {}
  $("#theme-toggle").addEventListener("click", () => {
    const dark = getComputedStyle(document.documentElement).colorScheme.includes("dark");
    const next = dark ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem(THEME_KEY, next); } catch {}
    drawHero();
    renderAll(); // artwork picks up the new palette
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => { drawHero(); renderAll(); });

  // ── Boot ──────────────────────────────────────────────────
  $("#hero-art").addEventListener("click", () => { heroSeed = hash(String(Math.random())); drawHero(); });
  $("#another-quote").addEventListener("click", nextQuote);
  renderAll();
  drawHero();
  nextQuote();
})();
