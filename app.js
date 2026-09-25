(() => {
  "use strict";

  const SITE = window.SITE || {};
  const STORE_KEY = "cabinet:additions";
  const THEME_KEY = "cabinet:theme";
  const LISTS = ["artists", "winemakers", "quotes"];

  // ── Small helpers ─────────────────────────────────────────
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const pad = (n, width = 2) => String(n).padStart(width, "0");
  const note = (s) => (s && !/^\s*todo\s*$/i.test(s) ? s : "");
  const fold = (s) => String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

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

  function palette() {
    const cs = getComputedStyle(document.documentElement);
    const v = (n) => cs.getPropertyValue(n).trim();
    return { paper: v("--paper"), ink: v("--ink"), signal: v("--signal"), grey: v("--grey") };
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

  // ── Generative artwork ────────────────────────────────────
  // Hard-edged, three colours only: ink, paper, signal red.
  const SVG_NS = "http://www.w3.org/2000/svg";
  function svg(tag, attrs = {}) {
    const n = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    return n;
  }

  let clipIds = 0;
  function artwork(seed, label = "") {
    const r = rng(seed);
    const P = palette();
    const W = 400, H = 500;
    const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, "aria-hidden": "true" });
    const clip = `art${++clipIds}`;
    const defs = svg("defs");
    const cp = svg("clipPath", { id: clip });
    cp.append(svg("rect", { width: W, height: H }));
    defs.append(cp);
    root.append(defs);
    const g = svg("g", { "clip-path": `url(#${clip})` });
    root.append(g);
    const style = hash(String(seed)) % 4;

    if (style === 0) {
      // halftone field swelling toward a focal point, over a red disc
      g.append(svg("rect", { width: W, height: H, fill: P.paper }));
      const fx = W * (0.2 + r() * 0.6), fy = H * (0.2 + r() * 0.6);
      g.append(svg("circle", { cx: W - fx, cy: H - fy, r: 110 + r() * 60, fill: P.signal }));
      const step = 13 + Math.floor(r() * 6);
      const reach = 260 + r() * 140;
      for (let y = step / 2; y < H; y += step)
        for (let x = step / 2; x < W; x += step) {
          const d = Math.hypot(x - fx, y - fy);
          const rad = Math.max(0, 1 - d / reach) * step * 0.62;
          if (rad > 0.6) g.append(svg("circle", { cx: x, cy: y, r: rad.toFixed(2), fill: P.ink }));
        }
    } else if (style === 1) {
      // vertical bars, a cut-out circle
      g.append(svg("rect", { width: W, height: H, fill: P.paper }));
      let x = 0;
      while (x < W) {
        const w = 6 + Math.floor(r() * 48);
        const t = r();
        const fill = t < 0.5 ? P.ink : t < 0.68 ? P.signal : P.paper;
        g.append(svg("rect", { x, y: 0, width: w, height: H, fill }));
        x += w;
      }
      g.append(svg("circle", { cx: W * (0.3 + r() * 0.4), cy: H * (0.3 + r() * 0.4), r: 70 + r() * 60, fill: P.paper }));
      g.append(svg("rect", { x: 0, y: H * (0.7 + r() * 0.15), width: W, height: 3, fill: P.signal }));
    } else if (style === 2) {
      // a giant cropped initial
      const bg = r() < 0.5 ? P.signal : P.ink;
      g.append(svg("rect", { width: W, height: H, fill: bg }));
      for (let i = 1; i < 5; i++)
        g.append(svg("line", { x1: 0, y1: (H / 5) * i, x2: W, y2: (H / 5) * i, stroke: P.paper, "stroke-opacity": 0.25 }));
      const t = svg("text", {
        x: -30 - r() * 60,
        y: H + 40 + r() * 60,
        fill: P.paper,
        "font-family": "Archivo, Helvetica, Arial, sans-serif",
        "font-weight": 900,
        "font-size": 620,
        style: "font-stretch:62%",
      });
      t.textContent = String(label || seed).trim().charAt(0).toUpperCase() || "✺";
      g.append(t);
      g.append(svg("circle", { cx: W * (0.55 + r() * 0.3), cy: H * (0.15 + r() * 0.2), r: 22 + r() * 18, fill: bg === P.ink ? P.signal : P.ink }));
    } else {
      // a disc cut into shifted slices
      g.append(svg("rect", { width: W, height: H, fill: P.paper }));
      const cx = W / 2, cy = H / 2, R = 150 + r() * 30;
      const n = 7 + Math.floor(r() * 8);
      const hot = Math.floor(r() * n);
      for (let i = 0; i < n; i++) {
        const y0 = cy - R + (2 * R * i) / n;
        const h = (2 * R) / n;
        const sc = svg("clipPath", { id: `${clip}s${i}` });
        sc.append(svg("rect", { x: 0, y: y0, width: W, height: h - 2 }));
        defs.append(sc);
        g.append(svg("circle", {
          cx: cx + (r() - 0.5) * 90, cy, r: R,
          fill: i === hot ? P.signal : P.ink,
          "clip-path": `url(#${clip}s${i})`,
        }));
      }
      g.append(svg("line", { x1: 24, y1: 24, x2: W - 24, y2: 24, stroke: P.ink }));
    }
    return root;
  }

  // ── Fit text to container width (magazine-style wordmarks) ─
  function fit(container) {
    const width = container.clientWidth;
    $$(".fit", container).forEach((span) => {
      span.style.fontSize = "100px";
      const w = span.getBoundingClientRect().width;
      if (w) span.style.fontSize = `${Math.floor(((100 * width) / w) * 0.995)}px`;
    });
  }
  // Shrink big headlines until their longest word fits — words never break mid-way.
  function shrinkToFit(nodes) {
    nodes.forEach((n) => {
      n.style.fontSize = "";
      let size = parseFloat(getComputedStyle(n).fontSize);
      for (let i = 0; i < 24 && n.scrollWidth > n.clientWidth + 1 && size > 18; i++) {
        size *= 0.93;
        n.style.fontSize = `${size}px`;
      }
    });
  }
  function fitAll() {
    fit($("#wordmark"));
    fit($("#colophon-mark"));
    shrinkToFit($$(".bottle .place, .section h2"));
  }

  // ── Cover ─────────────────────────────────────────────────
  function season(d) {
    const m = d.getMonth();
    return m < 2 || m === 11 ? "Winter" : m < 5 ? "Spring" : m < 8 ? "Summer" : "Autumn";
  }

  function renderCover() {
    const owner = SITE.owner || "";
    const title = SITE.title || "Cabinet of Inspiration";
    const words = title.split(/\s+/);
    const last = words.length > 1 ? words.pop() : null;
    const line = (text, cls = "") => el("span", { class: `line ${cls}` }, el("span", { class: "fit", text }));
    $("#wordmark").replaceChildren(line(words.join(" ")), last ? line(last, "serif") : null);

    const now = new Date();
    $("#issue").textContent = `Issue ${pad(1)} — ${season(now)} ${now.getFullYear()}`;
    $("#kept-by").textContent = owner ? `Kept by ${owner}` : "";
    $("#intro").textContent = SITE.intro || "";
    $("#brand").replaceChildren(owner || title, owner ? el("span", { class: "bar-title", text: ` / ${title}` }) : null);
    $("#footer-owner").textContent = owner || "—";
    $("#colophon-mark").replaceChildren(el("span", { class: "fit", text: owner || title }));
    $("#cover-year").textContent = now.getFullYear();
    document.title = owner ? `${title} — ${owner}` : title;
  }

  let coverSeed = SITE.owner || "cabinet";
  let studyNo = 1;
  function drawCover() {
    $("#cover-art").replaceChildren(artwork(String(coverSeed), SITE.owner));
    $("#cover-caption").textContent = `Untitled (study no. ${studyNo})`;
  }

  function renderCounts() {
    $$("[data-count]").forEach((n) => (n.textContent = pad(allOf(n.dataset.count).length)));
    const c = (k) => allOf(k).length;
    $("#counts").textContent = `${c("artists")} artists / ${c("winemakers")} winemakers / ${c("quotes")} quotes`;
  }

  function renderTicker() {
    const qs = allOf("quotes");
    const host = $("#ticker");
    host.parentElement.hidden = !qs.length;
    if (!qs.length) return;
    const items = qs.map((q) => `${q.text} — ${q.author || "unknown"}`);
    const spans = () => items.map((t) => el("span", { text: t }));
    host.replaceChildren(...spans(), ...spans()); // doubled for a seamless loop
    const chars = items.join("").length;
    host.style.setProperty("--tick-dur", `${Math.max(30, chars * 0.18)}s`);
  }

  // ── Filters ───────────────────────────────────────────────
  const filters = { artists: null, winemakers: null };
  const query = { artists: "", winemakers: "" };
  const moreTags = { artists: false, winemakers: false };
  const showAll = { artists: false, winemakers: false };
  const TOP_TAGS = 12;
  const PAGE = 30;

  function renderFilters(kind) {
    const host = $(`[data-chips="${kind}"]`);
    const counts = {};
    allOf(kind).forEach((x) => (x.tags || []).forEach((t) => (counts[t] = (counts[t] || 0) + 1)));
    let tags = Object.keys(counts).sort((a, b) => counts[b] - counts[a] || a.localeCompare(b));
    if (!tags.length) return host.replaceChildren();
    const hidden = tags.length - TOP_TAGS;
    if (hidden > 0 && !moreTags[kind]) {
      tags = tags.slice(0, TOP_TAGS);
      if (filters[kind] && !tags.includes(filters[kind])) tags.push(filters[kind]);
    }
    const btn = (label, value) =>
      el("button", {
        "aria-pressed": String(filters[kind] === value),
        text: label,
        onclick: () => {
          filters[kind] = filters[kind] === value ? null : value;
          renderList(kind);
          renderFilters(kind);
        },
      });
    const toggle = hidden > 0 && el("button", {
      class: "more",
      text: moreTags[kind] ? "Fewer" : `+${hidden} more`,
      onclick: () => { moreTags[kind] = !moreTags[kind]; renderFilters(kind); },
    });
    host.replaceChildren(btn("All", null), ...tags.map((t) => btn(t, t)), toggle || null);
  }

  const filtered = (kind, all) => {
    const f = filters[kind];
    const q = fold(query[kind]).trim();
    return all.filter((x) =>
      (!f || (x.tags || []).includes(f)) &&
      (!q || fold([x.name, x.medium, x.region, x.country, x.grapes, (x.tags || []).join(" "), note(x.why)].join(" ")).includes(q)));
  };

  function removeButton(kind, item) {
    if (!item._local) return null;
    return el("button", {
      class: "remove",
      text: "Remove draft",
      onclick: (e) => {
        e.stopPropagation();
        local[kind] = local[kind].filter((x) => x.id !== item.id);
        saveLocal(local);
        renderAll();
      },
    });
  }

  // ── Artists: index with hover preview ─────────────────────
  const peek = $("#peek");
  let peekX = 0, peekY = 0, curX = 0, curY = 0, peekRaf = 0;
  function peekLoop() {
    curX += (peekX - curX) * 0.18;
    curY += (peekY - curY) * 0.18;
    peek.style.left = `${curX + 140}px`;
    peek.style.top = `${curY}px`;
    peekRaf = peek.classList.contains("show") ? requestAnimationFrame(peekLoop) : 0;
  }
  function showPeek(a, e) {
    peek.replaceChildren(artwork(a.name, a.name));
    peekX = curX = e.clientX;
    peekY = curY = e.clientY;
    peek.classList.add("show");
    if (!peekRaf) peekRaf = requestAnimationFrame(peekLoop);
  }
  document.addEventListener("mousemove", (e) => { peekX = e.clientX; peekY = e.clientY; });

  function artistRow(a, i, total) {
    const row = el("li", { class: "row reveal" });
    const width = Math.max(2, String(total).length);
    const main = el("button", {
      class: "row-main",
      "aria-expanded": "false",
      onclick: () => {
        const open = row.classList.toggle("open");
        main.setAttribute("aria-expanded", String(open));
        peek.classList.remove("show");
        const frame = $(".art-frame", row);
        if (open && !frame.firstChild) frame.append(artwork(a.name, a.name)); // drawn on first open
      },
      onmouseenter: (e) => !row.classList.contains("open") && showPeek(a, e),
      onmouseleave: () => peek.classList.remove("show"),
    },
      el("span", { class: "no", text: pad(i + 1, width) }),
      el("span", { class: "name" }, a.name, a._local && el("span", { class: "draft", text: "draft" })),
      el("span", { class: "cell medium", text: a.medium || "—" }),
      el("span", { class: "cell years", text: a.era || "—" }),
      el("span", { class: "cell tags", text: (a.tags || []).join(", ") || "—" }),
      el("span", { class: "arrow", "aria-hidden": "true", text: "+" }),
    );
    const link = safeUrl(a.link);
    const detail = el("div", { class: "row-detail" },
      el("span", { class: "spacer" }),
      el("div", { class: "art-frame" }),
      el("div", {},
        note(a.why)
          ? el("p", { class: "why", text: a.why })
          : el("p", { class: "why pending", text: "Notes to come." }),
        el("div", { class: "cap", text: [a.name, a.medium, a.era].filter(Boolean).join(", ") }),
        el("div", { class: "detail-links" },
          link && el("a", { href: link, target: "_blank", rel: "noopener", text: "See the work ↗" }),
          removeButton("artists", a),
        ),
      ),
    );
    row.append(main, detail);
    return row;
  }

  // ── Winemakers ────────────────────────────────────────────
  function bottleCard(w, i, total) {
    // headline: the first place named, minus asides — "Naoussa (Trilofos), Macedonia" → "Naoussa"
    const place = (w.region || w.country || "—").replace(/\s*\(.*?\)/g, "").split(",")[0].split(" / ")[0].trim();
    const size = place.length > 15 ? " longest" : place.length > 9 ? " long" : "";
    const spec = el("dl", { class: "spec" });
    const add = (k, v) => v && spec.append(el("dt", { text: k }), el("dd", { text: v }));
    if (w.estate && w.estate !== w.name) add("Estate", w.estate);
    add("Region", [w.region, w.country].filter(Boolean).join(", "));
    add("Grapes", w.grapes);
    add("The bottle", w.favorite);
    const link = safeUrl(w.link);
    return el("article", { class: "bottle reveal" },
      el("div", { class: "bottle-top label" },
        el("span", { text: `No. ${pad(i + 1, Math.max(2, String(total).length))}` }),
        el("span", { text: w.country || "" }),
      ),
      el("div", { class: `place${size}`, text: place }),
      el("h3", { text: w.name }),
      spec,
      note(w.why) && el("p", { class: "why", text: w.why }),
      el("div", { class: "foot" },
        link && el("a", { href: link, target: "_blank", rel: "noopener", text: "Estate ↗" }),
        w._local && el("span", { class: "draft-tag", text: "draft" }),
        removeButton("winemakers", w),
      ),
    );
  }

  // ── Words ─────────────────────────────────────────────────
  let current = 0;
  function showQuote(i, animate = true) {
    const qs = allOf("quotes");
    const stage = $("#stage");
    if (!qs.length) { stage.hidden = true; return; }
    stage.hidden = false;
    current = (i + qs.length) % qs.length;
    const q = qs[current];
    const paint = () => {
      $("#stage-text").textContent = q.text;
      $("#stage-author").textContent = [q.author || "Unknown", q.source].filter(Boolean).join(" — ");
      $("#stage-count").textContent = `${pad(current + 1)} / ${pad(qs.length)}`;
      stage.classList.remove("swap");
      $$(".quote-list li").forEach((li, n) => li.classList.toggle("on", n === current));
    };
    if (!animate) return paint();
    stage.classList.add("swap");
    setTimeout(paint, 250);
  }

  function quoteItem(q, i) {
    return el("li", { class: "reveal" },
      el("button", {
        onclick: () => {
          showQuote(i);
          $("#stage").scrollIntoView({ block: "center" });
        },
      },
        el("span", { class: "qn", text: pad(i + 1) }),
        el("span", {},
          el("span", { class: "qt", text: q.text }),
          el("span", { class: "qa", text: q.author || "Unknown" }),
        ),
      ),
      removeButton("quotes", q),
    );
  }

  // ── Lists ─────────────────────────────────────────────────
  const itemFor = { artists: artistRow, winemakers: bottleCard, quotes: quoteItem };
  const emptyText = {
    artists: "No artists yet — add someone whose work stops you in your tracks.",
    winemakers: "The cellar is empty.",
    quotes: "No words yet.",
  };

  function renderList(kind) {
    const host = $(`[data-list="${kind}"]`);
    const all = allOf(kind);
    if (kind === "quotes") {
      host.replaceChildren(...(all.length ? all.map((q, i) => quoteItem(q, i)) : [el("p", { class: "empty", text: emptyText.quotes })]));
      return observeReveals(host);
    }
    const matches = filtered(kind, all);
    const narrowed = filters[kind] || query[kind].trim();
    const paged = kind === "artists"; // the cellar is grouped instead
    const shown = narrowed || showAll[kind] || !paged ? matches : matches.slice(0, PAGE);
    const nodes = [];
    let group;
    shown.forEach((x) => {
      if (!narrowed && x.group && x.group !== group) {
        group = x.group;
        const n = matches.filter((y) => y.group === group).length;
        nodes.push(el("div", { class: "group-head" }, el("span", { text: group }), el("span", { class: "gc", text: pad(n) })));
      }
      nodes.push(itemFor[kind](x, all.indexOf(x), all.length));
    });
    if (!matches.length) nodes.push(el("p", { class: "empty", text: narrowed ? "Nothing matches." : emptyText[kind] }));
    if (paged && (shown.length < matches.length || (showAll[kind] && !narrowed && matches.length > PAGE))) {
      const expanded = showAll[kind];
      nodes.push(el("li", { class: "show-all" }, el("button", {
        class: "add-btn",
        text: expanded ? "Show fewer ↑" : `Show all ${matches.length} →`,
        onclick: () => {
          showAll[kind] = !expanded;
          renderList(kind);
          if (expanded) document.getElementById(kind).scrollIntoView();
        },
      })));
    }
    host.replaceChildren(...nodes);
    const status = $(`[data-status="${kind}"]`);
    if (status) status.textContent = narrowed ? `${matches.length} of ${all.length}` : "";
    shrinkToFit($$(".place", host));
    observeReveals(host);
  }

  $$("[data-search]").forEach((input) => {
    const kind = input.dataset.search;
    input.placeholder = `Search ${allOf(kind).length} ${kind}…`;
    input.addEventListener("input", () => { query[kind] = input.value; renderList(kind); });
  });

  function renderAll() {
    renderCover();
    renderCounts();
    renderTicker();
    renderFilters("artists");
    renderFilters("winemakers");
    LISTS.forEach(renderList);
    showQuote(current, false);
    fitAll();
  }

  // ── Scroll reveal ─────────────────────────────────────────
  const io = "IntersectionObserver" in window
    ? new IntersectionObserver((entries) => {
        for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      }, { rootMargin: "0px 0px -6% 0px" })
    : null;
  function observeReveals(root) {
    $$(".reveal", root).forEach((n, i) => {
      n.style.transitionDelay = `${Math.min(i, 8) * 45}ms`;
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
      ["name", "Winemaker", true], ["group", "Group (e.g. Loire, Tasted)"], ["estate", "Estate / domaine"], ["region", "Region"], ["country", "Country"],
      ["grapes", "Grapes"], ["favorite", "Favorite bottle"], ["why", "Why you love their wine", false, true],
      ["link", "Link"], ["tags", "Tags, comma separated"],
    ],
    quotes: [
      ["text", "Quote", true, true], ["author", "Who said it"], ["source", "Source (book, film, song…)"],
    ],
  };
  const TITLES = { artists: "New artist", winemakers: "New winemaker", quotes: "New quote" };

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
    if (addingKind === "quotes") current = allOf("quotes").length - 1;
    renderAll();
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
    e.target.textContent = "Copied ✓";
    setTimeout(() => (e.target.textContent = "Copy"), 1500);
  });
  $("#clear-local").addEventListener("click", (e) => {
    if (!confirm("Remove every entry saved only in this browser?")) return e.preventDefault();
    local = { artists: [], winemakers: [], quotes: [] };
    saveLocal(local);
    current = 0;
    renderAll();
  });

  // ── Theme ─────────────────────────────────────────────────
  const isDark = () => getComputedStyle(document.documentElement).colorScheme.includes("dark");
  function applyTheme(t) {
    if (t) document.documentElement.dataset.theme = t;
    else delete document.documentElement.dataset.theme;
    $("#theme-toggle").textContent = isDark() ? "Light" : "Dark";
  }
  try { applyTheme(localStorage.getItem(THEME_KEY)); } catch { applyTheme(null); }
  function repaint() { drawCover(); renderAll(); }
  $("#theme-toggle").addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem(THEME_KEY, next); } catch {}
    repaint(); // artwork picks up the new palette
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => {
    applyTheme(document.documentElement.dataset.theme);
    repaint();
  });

  // ── Boot ──────────────────────────────────────────────────
  $("#cover-art").addEventListener("click", () => {
    coverSeed = Math.random().toString(36);
    studyNo += 1;
    drawCover();
  });
  $("#prev-quote").addEventListener("click", () => showQuote(current - 1));
  $("#next-quote").addEventListener("click", () => showQuote(current + 1));

  let resizeT;
  addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(fitAll, 80); });

  renderAll();
  drawCover();
  document.fonts?.ready.then(fitAll);
})();
