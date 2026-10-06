/* Factline front-end: plain JS, no build step. */
(() => {
  "use strict";

  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const pct = (x, d = 0) => `${(x * 100).toFixed(d)}%`;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  async function api(path, opts = {}) {
    const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `${res.status} ${res.statusText}`);
    return body;
  }

  // ------------------------------------------------------------------ samples
  // Short illustrative texts written for this demo (not real articles).
  const SAMPLES = [
    {
      label: "Wire report",
      title: "City council approves revised transit budget after public hearing",
      text: "The city council voted 7-2 on Tuesday to approve a revised transit budget that increases bus service on four routes and delays a planned fare increase until next year, officials said.\n\nThe measure follows a three-hour public hearing in which residents raised concerns about service gaps in outlying neighborhoods. The transportation department said the changes would cost about $4.2 million, funded in part by a state grant announced in March.\n\nCouncil member Ana Ruiz, who sponsored the amendment, said the plan was a compromise. \"We heard clearly that reliability matters more than new routes,\" she told reporters after the vote. The two members who voted against the plan said they wanted more detail on long-term costs. The mayor is expected to sign the budget later this week.",
    },
    {
      label: "Viral hoax",
      title: "SHOCKING: Doctors HATE this one secret they don't want you to know!!!",
      text: "You won't BELIEVE what they've been hiding from you. Insiders have finally leaked the truth the mainstream media refuses to report: a simple kitchen ingredient cures everything from diabetes to cancer in just 3 days!!\n\nBig Pharma is TERRIFIED. The globalist elites have been censoring this information for decades because it would destroy their profits. Share this before it gets deleted! Wake up, people — the establishment is lying to you and the evidence is everywhere if you open your eyes.\n\nThousands of patriots are already spreading the word. Don't let them silence you.",
    },
    {
      label: "Political claim",
      title: "",
      text: "Says the governor cut education funding by 40 percent while giving millionaires a massive tax break.",
    },
    {
      label: "Election rumor",
      title: "BREAKING: Leaked emails PROVE the election was rigged, insiders say",
      text: "An anonymous source has revealed bombshell evidence that thousands of illegal ballots were secretly shipped in overnight. The corrupt media is covering it up and refuses to investigate. Patriots are demanding answers as the deep state scrambles to hide the truth. This changes EVERYTHING. Share now before Facebook deletes it!",
    },
    {
      label: "Science brief",
      title: "Researchers report modest gains from new drought-tolerant wheat variety",
      text: "A five-year field study published on Monday found that a drought-tolerant wheat variety produced yields about 8 percent higher than conventional seed in dry seasons, though the advantage disappeared in years with normal rainfall.\n\nThe research team, which tested the crop across 14 sites, said further trials were needed before the variety could be recommended widely. An agricultural economist not involved in the study said the results were encouraging but cautioned that seed costs and local soil conditions would affect adoption.",
    },
  ];

  // ------------------------------------------------------------------ theme
  const root = document.documentElement;
  const THEME_KEY = "factline-theme";
  try { const t = localStorage.getItem(THEME_KEY); if (t) root.dataset.theme = t; } catch { /* storage unavailable */ }
  $("#themeToggle").addEventListener("click", () => {
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem(THEME_KEY, root.dataset.theme); } catch { /* ignore */ }
    if (modelData) renderModel(modelData);
    drawSpark(lastFeed);
  });

  $("#today").textContent = new Date().toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "long", day: "numeric" });

  // ------------------------------------------------------------------ tabs
  let activeView = "analyze";
  function showView(name) {
    activeView = name;
    $$(".tab").forEach((t) => { const on = t.dataset.view === name; t.classList.toggle("is-active", on); t.setAttribute("aria-selected", on); });
    $$(".view").forEach((v) => v.classList.toggle("is-active", v.id === `view-${name}`));
    if (name === "model") loadModel();
    if (name === "live") pollFeed();
    history.replaceState(null, "", `#${name}`);
  }
  $$(".tab").forEach((t) => t.addEventListener("click", () => showView(t.dataset.view)));

  // ------------------------------------------------------------------ health
  async function pollHealth() {
    try {
      const h = await api("/health");
      $$(".status__item").forEach((el) => {
        const ok = !!h[el.dataset.key];
        el.classList.toggle("is-up", ok);
        el.classList.toggle("is-down", !ok);
        el.title = `${el.textContent.trim()}: ${ok ? "online" : "offline"}`;
      });
    } catch {
      $$(".status__item").forEach((el) => { el.classList.remove("is-up"); el.classList.add("is-down"); });
    }
  }

  // ------------------------------------------------------------------ analyze
  const titleEl = $("#title"), textEl = $("#text"), toast = $("#toast");
  const META_INPUTS = { speaker: "#mSpeaker", party: "#mParty", subject: "#mSubject", context: "#mContext" };

  function payload() {
    const body = { title: titleEl.value.trim() || null, text: textEl.value.trim() };
    for (const [k, sel] of Object.entries(META_INPUTS)) { const v = $(sel).value.trim(); if (v) body[k] = v; }
    return body;
  }

  // Claim-metadata features look like "spk_barack_obama"; show them as "speaker: barack obama".
  const META_LABEL = { spk: "speaker", party: "party", subj: "topic", ctx: "venue", st: "state" };
  function prettyTerm(term) {
    const parts = term.split(" ").map((w) => {
      const m = w.match(/^(spk|party|subj|ctx|st)_(.+)$/);
      return m ? `${META_LABEL[m[1]]}: ${m[2].replace(/_/g, " ")}` : w;
    });
    const meta = parts.join(" ") !== term;
    return { text: parts.join(meta ? " · " : " "), meta };
  }
  const termHtml = (t) => { const p = prettyTerm(t); return `<span class="${p.meta ? "term-meta" : ""}">${esc(p.text)}</span>`; };

  function say(msg, isError = false) {
    toast.textContent = msg;
    toast.classList.toggle("is-error", isError);
  }
  function updateCount() {
    const n = (textEl.value.match(/\S+/g) || []).length;
    $("#charCount").textContent = `${n.toLocaleString()} word${n === 1 ? "" : "s"}`;
  }
  textEl.addEventListener("input", updateCount);

  const samplesEl = $("#samples");
  SAMPLES.forEach((s) => {
    const b = document.createElement("button");
    b.className = "chip";
    b.textContent = s.label;
    b.addEventListener("click", () => { titleEl.value = s.title; textEl.value = s.text; updateCount(); analyze(); });
    samplesEl.appendChild(b);
  });

  async function analyze() {
    const text = textEl.value.trim();
    if (!text) { say("Paste some article text first.", true); textEl.focus(); return; }
    const btn = $("#analyzeBtn");
    btn.disabled = true; btn.classList.add("is-loading");
    say("");
    try {
      const res = await api("/predict", { method: "POST", body: JSON.stringify(payload()) });
      renderVerdict(res);
      renderAnnotated(titleEl.value.trim(), text, res.top_terms);
    } catch (e) {
      say(e.message, true);
    } finally {
      btn.disabled = false; btn.classList.remove("is-loading");
    }
  }
  $("#analyzeBtn").addEventListener("click", analyze);
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && activeView === "analyze") analyze();
  });
  $("#clearBtn").addEventListener("click", () => {
    titleEl.value = ""; textEl.value = ""; updateCount(); say("");
    Object.values(META_INPUTS).forEach((sel) => { $(sel).value = ""; });
    $("#verdict").dataset.state = "empty"; $("#annotated").hidden = true;
  });

  $("#ingestBtn").addEventListener("click", async () => {
    const text = textEl.value.trim();
    if (!text) { say("Paste some article text first.", true); return; }
    try {
      const r = await api("/ingest", { method: "POST", body: JSON.stringify(payload()) });
      say(`Published to Kafka topic “${r.topic}” as ${r.id}. Watch it arrive on the Live Wire.`);
    } catch (e) { say(e.message, true); }
  });

  const CIRC = 2 * Math.PI * 52;
  function renderVerdict(r) {
    const v = $("#verdict");
    const unrel = r.label === "unreliable";
    v.dataset.state = "result";

    const fill = $("#gaugeFill");
    fill.style.stroke = unrel ? "var(--unrel)" : "var(--rel)";
    fill.style.strokeDashoffset = CIRC;
    requestAnimationFrame(() => requestAnimationFrame(() => { fill.style.strokeDashoffset = CIRC * (1 - r.confidence); }));
    countUp($("#confValue"), r.confidence);

    const stamp = $("#stamp");
    stamp.textContent = r.label;
    stamp.classList.toggle("is-unrel", unrel);
    stamp.classList.remove("is-stamping"); void stamp.offsetWidth; stamp.classList.add("is-stamping");

    const model = (r.model || "").replace(/_/g, " ");
    const routeTxt = r.route === "claim" ? "claim model" : "article model";
    $("#verdictMeta").innerHTML = `<span class="route-chip" title="Short headline-less claims use the claim model; everything else the article model">${routeTxt}</span>${esc(model)} · v${esc(r.model_version || "?")}<br>scored in ${r.latency_ms} ms`;

    $("#probRel").style.transform = `scaleX(${r.probabilities.reliable})`;
    $("#probRelTxt").textContent = pct(r.probabilities.reliable, 1);
    $("#probUnrelTxt").textContent = pct(r.probabilities.unreliable, 1);

    const max = Math.max(...r.top_terms.map((t) => Math.abs(t.weight)), 1e-9);
    const list = (dir) => {
      const items = r.top_terms.filter((t) => t.direction === dir).slice(0, 6);
      if (!items.length) return `<li><span class="none">No strong signals</span></li>`;
      return items.map((t) => `<li title="weight ${t.weight}">${termHtml(t.term)}<div class="bar"><i data-w="${(Math.abs(t.weight) / max) * 100}"></i></div></li>`).join("");
    };
    $("#termsUnrel").innerHTML = list("unreliable");
    $("#termsRel").innerHTML = list("reliable");
    requestAnimationFrame(() => $$(".terms .bar i").forEach((i) => { i.style.transform = `scaleX(${i.dataset.w / 100})`; }));
  }

  function countUp(el, target) {
    const t0 = performance.now(), dur = 900;
    const step = (t) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = pct(target * e);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  // Stop words removed by the vectorizer before bigrams are formed (subset of sklearn's list).
  const STOP = new Set("a about above after again against all also am an and any are as at be because been before being below between both but by can could did do does doing down during each few for from further had has have having he her here hers herself him himself his how i if in into is it its itself just me more most my myself no nor not now of off on once only or other our ours ourselves out over own same she should so some such than that the their theirs them themselves then there these they this those through to too under until up very was we were what when where which while who whom why will with would you your yours yourself yourselves said says".split(" "));

  function renderAnnotated(title, text, terms) {
    const weights = new Map(terms.map((t) => [t.term, t]));
    const max = Math.max(...terms.map((t) => Math.abs(t.weight)), 1e-9);
    const toks = [...text.matchAll(/[A-Za-z0-9]+/g)].map((m) => ({ s: m.index, e: m.index + m[0].length, w: m[0].toLowerCase() }));
    const content = toks.filter((t) => t.w.length >= 2 && !STOP.has(t.w));
    const marks = []; // {s, e, term}
    for (let i = 0; i < content.length; i++) {
      const a = content[i], b = content[i + 1];
      if (b && weights.has(`${a.w} ${b.w}`)) { marks.push({ s: a.s, e: b.e, term: weights.get(`${a.w} ${b.w}`) }); i++; continue; }
      if (weights.has(a.w)) marks.push({ s: a.s, e: a.e, term: weights.get(a.w) });
    }
    let html = "", pos = 0;
    for (const m of marks) {
      const cls = m.term.direction === "unreliable" ? "hl--unrel" : "hl--rel";
      const a = (0.35 + 0.65 * Math.abs(m.term.weight) / max).toFixed(2);
      html += esc(text.slice(pos, m.s));
      html += `<mark class="hl ${cls}" style="--a:${a}" title="“${esc(m.term.term)}” → ${m.term.direction} (${m.term.weight > 0 ? "+" : ""}${m.term.weight})">${esc(text.slice(m.s, m.e))}</mark>`;
      pos = m.e;
    }
    html += esc(text.slice(pos));
    $("#annTitle").textContent = title;
    $("#annText").innerHTML = html;
    $("#annotated").hidden = false;
  }

  // ------------------------------------------------------------------ live wire
  let lastFeed = [];
  const seen = new Set();
  let firstFeedLoad = true;

  async function pollFeed() {
    try {
      const r = await api("/stream/recent?limit=60");
      const ws = $("#wireState");
      ws.textContent = r.connected ? "connected to news-predictions" : "waiting for Kafka…";
      ws.classList.toggle("is-on", r.connected);
      lastFeed = r.items;
      renderFeed(r.items);
    } catch { /* API down; health lights already show it */ }
  }

  function renderFeed(items) {
    const n = items.length;
    const unrel = items.filter((i) => i.label === "unreliable").length;
    const avg = n ? items.reduce((s, i) => s + i.confidence, 0) / n : 0;
    $("#liveCount").textContent = n.toLocaleString();
    $("#liveUnrel").textContent = n ? pct(unrel / n) : "0%";
    $("#liveConf").textContent = n ? pct(avg) : "0%";
    const newest = items[0] && Date.now() - new Date(items[0].scored_at).getTime() < 60_000;
    $("#livePulse").classList.toggle("is-live", !!newest);
    drawSpark(items);

    if (activeView !== "live" && !firstFeedLoad) return;
    if (!n) return;
    const feed = $("#feed");
    feed.innerHTML = items.map((it) => {
      const isNew = !seen.has(it.id) && !firstFeedLoad;
      const u = it.label === "unreliable";
      const when = new Date(it.scored_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      const terms = (it.top_terms || []).filter((t) => t.direction === it.label).slice(0, 4).map((t) => `<span>${esc(prettyTerm(t.term).text)}</span>`).join("");
      return `<article class="wire ${u ? "is-unrel" : ""} ${isNew ? "is-new" : ""}">
        <div class="wire__top mono"><span class="verdict-chip">${esc(it.label)}</span><span>${when} · ${esc(it.source || "live")}</span></div>
        ${it.title ? `<h4>${esc(it.title)}</h4>` : ""}
        <p>${esc(it.snippet)}</p>
        <div class="wire__conf mono"><div class="bar"><i style="width:${pct(it.confidence)}"></i></div><span>${pct(it.confidence)}</span></div>
        ${terms ? `<div class="wire__terms">${terms}</div>` : ""}
      </article>`;
    }).join("");
    items.forEach((i) => seen.add(i.id));
    firstFeedLoad = false;
  }

  function drawSpark(items) {
    const c = $("#spark");
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth || 220, h = c.clientHeight || 44;
    c.width = w * dpr; c.height = h * dpr;
    const ctx = c.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);
    const now = Date.now(), buckets = new Array(15).fill(0);
    for (const it of items) {
      const age = Math.floor((now - new Date(it.scored_at).getTime()) / 60_000);
      if (age >= 0 && age < 15) buckets[14 - age]++;
    }
    const max = Math.max(...buckets, 1), bw = w / buckets.length;
    buckets.forEach((v, i) => {
      const bh = Math.max(2, (v / max) * (h - 4));
      ctx.fillStyle = i === buckets.length - 1 ? cssVar("--accent") : cssVar("--ink-3");
      ctx.globalAlpha = v ? 1 : 0.35;
      ctx.fillRect(i * bw + 1.5, h - bh, bw - 3, bh);
    });
    ctx.globalAlpha = 1;
  }

  $("#burstBtn").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      for (const s of SAMPLES) {
        await api("/ingest", { method: "POST", body: JSON.stringify({ title: s.title || null, text: s.text }) });
        await new Promise((r) => setTimeout(r, 350));
      }
      setTimeout(pollFeed, 1200);
    } catch (err) {
      $("#wireState").textContent = err.message;
    } finally { btn.disabled = false; }
  });

  // ------------------------------------------------------------------ model desk
  let modelData = null, compareChart = null, cmScope = "overall", vocabRoute = "article";
  const NICE = { logistic_regression: "Logistic Regression", naive_bayes: "Multinomial Naive Bayes" };

  async function loadModel() {
    try {
      modelData = await api("/model");
      $("#modelEmpty").hidden = true; $("#modelBody").hidden = false;
      renderModel(modelData);
    } catch {
      $("#modelEmpty").hidden = false; $("#modelBody").hidden = true;
    }
  }

  function renderModel(m) {
    const best = m.models[m.best_model];
    const other = Object.keys(m.models).find((k) => k !== m.best_model);
    const o = best.overall, oo = other ? m.models[other].overall : null;

    $("#modelName").textContent = `TF-IDF + ${NICE[m.best_model] || m.best_model}`;
    $("#modelSub").innerHTML = [
      `version ${esc(m.version)}`,
      `trained ${new Date(m.trained_at).toLocaleString()}`,
      `${m.n_train.toLocaleString()} train · ${m.n_test.toLocaleString()} test · ${m.n_features.toLocaleString()} features`,
      best.routing_accuracy != null ? `routing ${pct(best.routing_accuracy, 1)} of test items reach the right sub-model` : null,
      `source ${esc(m.loaded_from || m.data_source)}`,
    ].filter(Boolean).join("<br>");

    const kpi = (label, key, fmt = (x) => (x * 100).toFixed(1), suffix = "<small>%</small>") => {
      const isPct = suffix !== "";
      const d = oo && oo[key] != null && o[key] != null ? o[key] - oo[key] : null;
      const dTxt = d == null ? "&nbsp;"
        : `${d >= 0 ? "+" : ""}${isPct ? `${(d * 100).toFixed(1)} pts` : d.toFixed(3)} vs ${other === "naive_bayes" ? "NB" : "LR"}`;
      return `<div class="kpi"><div class="kpi__label">${label}</div>
        <div class="kpi__value">${o[key] == null ? "—" : fmt(o[key]) + suffix}</div>
        <div class="kpi__delta mono">${dTxt}</div></div>`;
    };
    $("#kpis").innerHTML = kpi("Accuracy", "accuracy") + kpi("Macro F1", "macro_f1") + kpi("ROC-AUC", "roc_auc", (x) => x.toFixed(3), "") + kpi("Recall · fake", "recall");

    // comparison chart
    const keys = [["accuracy", "Accuracy"], ["precision", "Precision"], ["recall", "Recall"], ["f1", "F1"], ["macro_f1", "Macro F1"], ["roc_auc", "ROC-AUC"]];
    const names = Object.keys(m.models);
    const palette = Object.fromEntries(names.map((n) => [n, n === m.best_model ? cssVar("--ink") : cssVar("--ink-3")]));
    if (window.Chart) {
      Chart.defaults.font.family = cssVar("--sans") || "Inter Tight";
      Chart.defaults.color = cssVar("--ink-2");
      compareChart?.destroy();
      compareChart = new Chart($("#compareChart"), {
        type: "bar",
        data: {
          labels: keys.map((k) => k[1]),
          datasets: names.map((n) => ({
            label: `${NICE[n] || n}${n === m.best_model ? " ★" : ""}`,
            data: keys.map(([k]) => m.models[n].overall[k]),
            backgroundColor: palette[n] || cssVar("--ink-3"),
            borderRadius: 3, barPercentage: 0.75, categoryPercentage: 0.7,
          })),
        },
        options: {
          responsive: true, maintainAspectRatio: false, animation: { duration: 700 },
          scales: {
            y: { min: Math.max(0, Math.floor(Math.min(...names.flatMap((n) => keys.map(([k]) => m.models[n].overall[k] ?? 1))) * 10) / 10 - 0.1),
                 max: 1, grid: { color: cssVar("--rule") }, border: { display: false }, ticks: { callback: (v) => `${Math.round(v * 100)}%` } },
            x: { grid: { display: false }, border: { color: cssVar("--rule") } },
          },
          plugins: {
            legend: { position: "bottom", labels: { boxWidth: 10, boxHeight: 10, useBorderRadius: true, borderRadius: 2 } },
            tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${(c.parsed.y * 100).toFixed(2)}%` } },
          },
        },
      });
    }

    // confusion matrix scope switch
    const scopes = ["overall", ...Object.keys(best.by_source)];
    if (!scopes.includes(cmScope)) cmScope = "overall";
    $("#cmSource").innerHTML = scopes.map((s) => `<button data-s="${s}" class="${s === cmScope ? "is-active" : ""}">${s === "overall" ? "All" : s === "liar" ? "LIAR" : s[0].toUpperCase() + s.slice(1)}</button>`).join("");
    $$("#cmSource button").forEach((b) => b.addEventListener("click", () => { cmScope = b.dataset.s; renderModel(m); }));
    renderCM(cmScope === "overall" ? o : best.by_source[cmScope]);

    // per source table
    const srcRows = Object.entries(best.by_source).map(([s, r]) => `<tr><td>${s === "liar" ? "LIAR (claims)" : "Kaggle (articles)"}</td>
      <td>${r.n.toLocaleString()}</td>
      <td>${pct(r.accuracy, 1)}<span class="meter"><i style="width:${pct(r.accuracy)}"></i></span></td>
      <td>${pct(r.macro_f1, 1)}</td><td>${r.roc_auc == null ? "—" : r.roc_auc.toFixed(3)}</td></tr>`).join("");
    $("#sourceTable").innerHTML = `<thead><tr><th>Dataset</th><th>Test n</th><th>Accuracy</th><th>Macro F1</th><th>AUC</th></tr></thead><tbody>${srcRows}</tbody>`;
    $("#sourceNote").innerHTML = best.by_source.liar
      ? "LIAR items are one-sentence political claims with six truth grades, binarized here as <b>true / mostly-true / half-true → reliable</b> and <b>barely-true / false / pants-fire → unreliable</b>. Short text gives TF-IDF little to work with, so expect much lower scores than on full Kaggle articles."
      : "";

    // vocabulary
    const voc = (arr) => arr.slice(0, 12).map((t) => `<li>${termHtml(t.term)}<em>${t.weight > 0 ? "+" : ""}${t.weight.toFixed(2)}</em></li>`).join("");
    const byRoute = m.top_terms_by_route || { article: m.top_terms };
    if (!byRoute[vocabRoute]) vocabRoute = Object.keys(byRoute)[0];
    $("#vocabRoute").innerHTML = Object.keys(byRoute).length > 1
      ? Object.keys(byRoute).map((r) => `<button data-r="${r}" class="${r === vocabRoute ? "is-active" : ""}">${r === "claim" ? "Claims" : "Articles"}</button>`).join("")
      : "";
    $$("#vocabRoute button").forEach((b) => b.addEventListener("click", () => { vocabRoute = b.dataset.r; renderModel(m); }));
    const terms = byRoute[vocabRoute];
    $("#vocabUnrel").innerHTML = voc(terms?.unreliable || []);
    $("#vocabRel").innerHTML = voc(terms?.reliable || []);

    // lineage
    const rows = m.rows_by_source || {};
    $("#flow").innerHTML = [
      ["Datasets", `Kaggle Fake News ${(rows.kaggle || 0).toLocaleString()} · LIAR ${(rows.liar || 0).toLocaleString()}`],
      ["Kafka", "<code>news-articles</code> topic, JSON keyed by article id"],
      ["HDFS", "<code>/news/raw/dt=…/part-*.jsonl</code> via batching sink"],
      ["Training", m.architecture === "routed"
        ? `Article model (Kaggle) + claim model (LIAR + speaker/party/topic tokens); LR vs NB, best by ${esc(m.selection_metric)}`
        : `TF-IDF 1–2 grams → LR vs NB, best by ${esc(m.selection_metric)}`],
      ["Serving", "<code>/news/models/latest</code> → FastAPI + live scorer"],
    ].map(([b, s]) => `<li><b>${b}</b><span>${s}</span></li>`).join("");
  }

  function renderCM(r) {
    const [[tn, fp], [fn, tp]] = r.confusion_matrix;
    const total = tn + fp + fn + tp || 1;
    const cell = (v, good, label) => {
      const share = v / total;
      const strength = Math.round(Math.min(1, share * 2) * 85 + 8);
      const color = good ? "var(--rel)" : "var(--unrel)";
      return `<div class="cm__cell ${strength > 55 ? "is-dark" : ""}" style="background:color-mix(in srgb, ${color} ${strength}%, var(--card))">
        <strong>${v.toLocaleString()}</strong><span>${label} · ${pct(share, 1)}</span></div>`;
    };
    $("#cm").innerHTML = `
      <div></div><div class="cm__axis cm__axis--col">Pred. reliable</div><div class="cm__axis cm__axis--col">Pred. unreliable</div>
      <div class="cm__axis">Actually reliable</div>${cell(tn, true, "true negative")}${cell(fp, false, "false alarm")}
      <div class="cm__axis">Actually unreliable</div>${cell(fn, false, "missed")}${cell(tp, true, "caught")}`;
  }

  // ------------------------------------------------------------------ boot
  updateCount();
  pollHealth();
  pollFeed();
  setInterval(pollHealth, 15_000);
  setInterval(() => (activeView === "live" ? pollFeed() : null), 2_500);
  setInterval(() => (activeView !== "live" ? pollFeed() : null), 15_000);
  window.addEventListener("resize", () => drawSpark(lastFeed));
  const initial = location.hash.slice(1);
  if (["analyze", "live", "model"].includes(initial)) showView(initial);
})();
