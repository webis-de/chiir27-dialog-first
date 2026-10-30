"use strict";

/* Dialog-First product search: the dialog is a tree of turns. Every interaction that poses a new query
   (typed, clicked, or a suggested follow-up) becomes a user turn; interactions that only change the view
   of an answer (sorting or expanding already retrieved results, switching between cards and table,
   enlarging) stay within the answer. Facet values filter the answer in place: the answer is re-queried
   and replaced, without a new turn. With the design variant "Every action is a turn", sorting,
   expanding, and facets also become turns.

   Enlarged answers and product pages replace the dialog on the full page (the "stage"); the composer
   stays. Products selected with the circle on their card or page are attached to the next question, which
   then refers only to them; on a product page, the product is attached as well, without being selected.
   Asking closes the stage.

   Earlier answers are minimized when a new one arrives (trial; collapse=0 keeps them open). The cart is
   fake: "Add to cart" only shows a notice, nothing is ordered.

   URL parameters: variant=query|action, facets=0|1, collapse=0|1, figure=1 (dialog only, for screenshots;
   composer=1 adds the input box at the bottom of the window),
   scenario=<name> (replays a scripted session from scenarios.js and adds numbered badges), until=<n> (stops
   the replay after n steps and shows only the last turns, three or last=<k>, for storyboard frames). */

const params = new URLSearchParams(location.search);
const settings = {
  variant: params.get("variant") === "action" ? "action" : "query",
  facets: params.get("facets") !== "0",
  collapse: params.get("collapse") !== "0",
  figure: params.get("figure") === "1",
};

const turns = new Map();
let nextId = 1;
let leaf = null;
let busy = false;
let replaying = false;
let actions = new Map();
let nextAction = 1;
let stage = null;  // { kind: "answer", turn } or { kind: "product", turn, product, offers }
let chatScroll = 0;
const selected = new Map();  // product id -> product, attached to the next question

const $ = (sel) => document.querySelector(sel);
const thread = $("#thread");

// ---------------------------------------------------------------------------------------------------
// Formatting

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const euro = (v) => "€" + Math.round(v).toLocaleString("en-US");
const inch = (v) => `${+v}″`;
const storage = (v) => (v >= 1000 ? "1 TB" : `${v} GB`);
const delivery = (v) => String(v).replace("-", "–");
const FACET_LABELS = { ram_gb: "RAM", display_in: "Display", display_type: "Panel", delivery: "Delivery", brand: "Brand" };
const FACET_VALUES = { ram_gb: (v) => `${v} GB`, display_in: inch, delivery };
const METRIC_LABELS = { battery_per_100eur: "Battery h / €100", avg_rating: "Avg. rating" };
const SORTS = {
  "recommended:desc": "Recommended", "battery_h:desc": "Battery life", "price:asc": "Price", "weight_kg:asc": "Weight", "rating:desc": "Rating",
  "battery_per_100eur:desc": "Battery per euro",
};
const GROUP_MEMBER_SORT = {
  battery_per_100eur: ["battery_per_100eur", "desc"], avg_battery: ["battery_h", "desc"], avg_price: ["price", "asc"],
  avg_rating: ["rating", "desc"], count: ["rating", "desc"],
};

// ---------------------------------------------------------------------------------------------------
// Dialog tree

function addTurn(turn) {
  turn.id = nextId++;
  turn.ui = { tab: "result", view: "list", sort: null, expanded: new Set(), marks: {} };
  turns.set(turn.id, turn);
  return turn;
}

const children = (id) => [...turns.values()].filter((t) => t.parent === id);

function path() {
  const result = [];
  for (let t = turns.get(leaf); t; t = turns.get(t.parent)) result.unshift(t);
  return result;
}

function contextPlan(turn) {
  for (let t = turn; t; t = turns.get(t.parent)) if (t.answer && t.answer.plan) return t.answer.plan;
  return null;
}

async function post(url, body) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  return response.json();
}

async function start() {
  turns.clear();
  nextId = 1;
  const answer = await (await fetch("/api/start")).json();
  leaf = addTurn({ parent: null, role: "system", answer }).id;
  render();
}

async function run(parentId, user, request) {
  if (busy) return;
  busy = true;
  closeStage(false);
  for (const turn of turns.values()) turn.ui.open = false;
  const u = addTurn({ parent: parentId, role: "user", ...user });
  const s = addTurn({ parent: u.id, role: "system", pending: true });
  leaf = s.id;
  render(true);
  try {
    const result = await request();
    if (result.question) u.text = result.question;
    s.answer = result.answer || result;
  } catch (error) {
    s.answer = { kind: "error", interpretation: "Something went wrong. Please try again." };
    console.error(error);
  }
  s.pending = false;
  busy = false;
  render(true);
}

/** A typed (or suggested) question, answered in the context of the given turn. */
function ask(fromId, text, note = null, badge = null, selection = []) {
  const ids = selection.map((p) => p.id);
  return run(fromId, { text, note, badge, selection },
    () => post("/api/ask", { text, context: contextPlan(turns.get(fromId)), selection: ids }));
}

/** A click or follow-up: the plan is verbalized as the user's question (P4). */
function act(fromId, plan, note = "written for your click", badge = null) {
  return run(fromId, { text: "…", note, badge, clicked: true }, () => post("/api/query", { plan }));
}

// ---------------------------------------------------------------------------------------------------
// Rendering

function action(fn, tip = null) {
  const key = String(nextAction++);
  actions.set(key, { fn, tip });
  return `data-action="${key}"`;
}

const badge = (label) => (label ? `<span class="badge">${esc(label)}</span>` : "");

function render(scroll = false) {
  actions = new Map();
  const latest = lastSystem();
  thread.innerHTML = path().map((t) => renderTurn(t, t === latest)).join("");
  $("#stage").innerHTML = stage ? renderStage() : "";
  renderSelection();
  // The latest exchange starts at the top of the window: the question, then its answer. Scrolling to the
  // question at once, rather than smoothly, hides the shift caused by minimizing earlier answers; space below
  // the answer lets the question stay in place while the answer arrives.
  const question = [...thread.querySelectorAll(".turn.user")].pop();
  thread.style.paddingBottom = "";
  if (question && !settings.figure) {
    const below = thread.getBoundingClientRect().bottom - question.getBoundingClientRect().top;
    const room = window.innerHeight - $("#composer").offsetHeight - 16;
    thread.style.paddingBottom = `${Math.max(0, room - below)}px`;
  }
  if (scroll && !replaying) question?.scrollIntoView({ block: "start" });
  $("#composer button[type=submit]").disabled = busy;
}

function renderTurn(t, latest) {
  if (t.role === "user") {
    const siblings = children(t.parent);
    let branches = "";
    if (siblings.length > 1) {
      const i = siblings.indexOf(t);
      const prev = siblings[i - 1], next = siblings[i + 1];
      branches = `<div class="branches">
        <button type="button" ${prev ? action(() => switchTo(prev)) : "disabled"} aria-label="Previous branch">‹</button>
        branch ${i + 1} of ${siblings.length}
        <button type="button" ${next ? action(() => switchTo(next)) : "disabled"} aria-label="Next branch">›</button></div>`;
    }
    const note = t.note ? `<span class="note">${esc(t.note)}</span>` : "";
    const attached = (t.selection || []).length
      ? `<div class="attached">${t.selection.map((p) => miniProduct(p, action(() => openProduct(t, p), { view: true }))).join("")}</div>` : "";
    return `<div class="turn user ${t.clicked ? "clicked" : ""}">${branches}
      <div class="speaker">You ${note}</div>${attached}
      <div class="badge-row">${badge(t.badge)}<div class="bubble">${esc(t.text)}</div></div></div>`;
  }
  const head = `<div class="speaker">System</div>`;
  if (t.pending) return `<div class="turn system">${head}<p class="pending">Searching the catalog …</p></div>`;
  const a = t.answer;
  if (a.kind === "unanswerable" || a.kind === "error") {
    return `<div class="turn system">${head}<p class="interpretation">${esc(a.interpretation)}</p>${examples(t, a.examples || [])}</div>`;
  }
  if (a.kind === "clarify") return renderClarify(t, head, latest);
  const start = t.parent === null ? "start" : "";
  // Figures keep earlier answers open, unless they ask for minimizing (collapse=1).
  const minimizable = settings.collapse && !latest && (!settings.figure || params.get("collapse") === "1");
  if (minimizable && !t.ui.open) {
    return `<div class="turn system collapsed ${start}">${head}<p class="interpretation">${esc(a.interpretation)}</p>
      <span class="view toggle-turn" ${action(() => { t.ui.open = true; render(); }, { view: true })}>▸ Show the result (${resultSize(a)})</span></div>`;
  }
  const observations = (a.observations || []).map((o) => `<li>${esc(o)}</li>`).join("");
  const followups = (a.followups || []).map((f) =>
    `<span class="chip" ${action(() => act(t.id, f.plan, "suggested follow-up"), { plan: f.plan })}>${esc(f.question)}</span>`).join("");
  const minimize = minimizable
    ? `<span class="view toggle-turn" ${action(() => { t.ui.open = false; render(); }, { view: true })}>▴ Minimize</span>` : "";
  return `<div class="turn system ${start}">${head}
    <p class="interpretation">${esc(a.interpretation)}</p>
    ${renderPanel(t)}
    ${observations ? `<ul class="observations">${observations}</ul>` : ""}
    ${followups ? `<div class="followups">${followups}</div>` : ""}${examples(t, a.examples || [])}${minimize}</div>`;
}

/** A vague question: candidate interpretations, each an executable query verbalized as a question (P3);
    choosing one poses it as the user's question (P4). */
function renderClarify(t, head, latest) {
  const a = t.answer;
  const items = a.candidates.map((c, i) => {
    const noun = c.kind === "list" ? "laptop" : "brand";
    const size = `${c.total} ${noun}${c.total === 1 ? "" : "s"}`;
    const shown = t.ui.marks[`sql:${i}`];
    const query = `<span class="view" ${action(() => { t.ui.marks[`sql:${i}`] = !shown; render(); }, { view: true })}>${shown ? "▴ Query" : "▸ Query"}</span>`;
    return `<li><div class="candidate-row">${badge(t.ui.marks[`choose:${i}`])}<span class="chip ${t.ui.marks[`choose:${i}`] ? "marked" : ""}"
      ${action(() => act(t.id, c.plan, "chosen interpretation"), { note: c.interpretation })}>${esc(c.question)}</span>
      <span class="candidate-meta">${size} · ${query}</span></div>${shown ? `<pre class="sql">${esc(c.sql)}</pre>` : ""}</li>`;
  }).join("");
  return `<div class="turn system clarify">${head}<p class="interpretation">${esc(a.interpretation)}</p>
    <ol class="candidates">${items}</ol></div>`;
}

function resultSize(a) {
  const n = a.kind === "list" ? a.total : a.rows.length;
  const noun = { list: "laptop", group: "brand", offers: "shop offer" }[a.kind];
  return noun ? `${n} ${noun}${n === 1 ? "" : "s"}` : "count";
}

function examples(t, list) {
  if (!list.length) return "";
  return `<div class="followups">${list.map((q) =>
    `<span class="chip" ${action(() => ask(t.id, q, "suggested question"), { text: q })}>${esc(q)}</span>`).join("")}</div>`;
}

function renderPanel(t) {
  const a = t.answer, ui = t.ui;
  const tools = [];
  if (a.kind === "list" && a.rows.length > 1) {
    tools.push(sortSelect(t));
  }
  if (a.kind !== "count") tools.push(`<span class="tool" ${action(() => enlarge(t), { view: true })}>⤢ Enlarge</span>`);
  const tab = (name, label) =>
    `<span class="tab ${ui.tab === name ? "on" : ""}" ${action(() => { ui.tab = name; render(); }, { view: true })}>${label}</span>`;
  const body = ui.tab === "query" ? `<pre class="sql">${esc(a.sql)}</pre>` : renderResult(t, false);
  const facets = ui.tab === "result" && settings.facets && ((a.facets && a.facets.length) || activeFacets(t).length) ? renderFacets(t) : "";
  let foot = "";
  if (ui.tab === "result" && a.kind === "list") {
    const shown = Math.min(visibleCount(t, false), a.rows.length);
    if (a.total > shown) foot = `<div class="panel-foot">Showing ${shown} of ${a.total} · <span class="view act" ${action(() => enlarge(t), { view: true })}>show all</span></div>`;
  }
  return `<div class="panel ${ui.filtering ? "filtering" : ""}"><div class="panel-bar">${tab("query", "Query")}${tab("result", "Result")}<span class="grow"></span>${tools.join("")}</div>
    <div class="panel-main ${facets ? "with-facets" : ""}">${facets}<div class="panel-content"><div class="panel-body">${body}</div>${foot}</div></div></div>`;
}

function sortSelect(t) {
  const plan = t.answer.plan;
  const current = t.ui.sort || (plan.sort ? `${plan.sort.attr}:${plan.sort.dir}` : "");
  const options = Object.entries(SORTS).map(([value, label]) =>
    `<option value="${value}" ${value === current ? "selected" : ""}>${label}</option>`).join("");
  const key = action(null);
  actions.get(key.match(/"(\d+)"/)[1]).change = (value) => sortBy(t, value);
  return `<span class="tool">Sort <select ${key} aria-label="Sort by">${current ? "" : "<option></option>"}${options}</select></span>`;
}

/** Sorting already retrieved results is a view change; otherwise it poses a new query. */
function sortBy(t, value) {
  const [attr, dir] = value.split(":");
  if (settings.variant === "query" && !t.answer.truncated) {
    t.ui.sort = value;
    render();
  } else {
    return act(t.id, { ...t.answer.plan, sort: { attr, dir } });
  }
}

/** Rating weighted by the number of reviews, as the server's sort "recommended" (plan.py). */
const recommended = (r) => (r.rating * r.reviews + 4.2 * 50) / (r.reviews + 50);

function sortedRows(t) {
  const rows = [...t.answer.rows];
  if (!t.ui.sort) return rows;
  const [attr, dir] = t.ui.sort.split(":");
  const key = { battery_per_100eur: (r) => r.battery_h / r.price, recommended }[attr] || ((r) => r[attr]);
  rows.sort((x, y) => (dir === "asc" ? key(x) - key(y) : key(y) - key(x)));
  return rows;
}

const visibleCount = (t, large) => (large ? Infinity : { cards: 6, list: 4 }[t.ui.view] || 10);

/** Days within which offers must arrive to meet a delivery condition of the answer (as in plan.py). */
const DELIVERY_DAYS = { tomorrow: 1, "2-3 days": 3, "within a week": 7 };
const deliveryFilters = (plan) => (plan && plan.filters ? plan.filters.filter((f) => f.attr === "delivery") : []);

/** Shop offers for a product, keeping the delivery condition of the answer in which it was found. */
const offersPlan = (t, p) => ({ kind: "offers", filters: deliveryFilters(t.answer.plan), product_id: p.id, max_price: p.price });

function priceLink(t, p) {
  const plan = offersPlan(t, p);
  return `<span class="act price" ${action(() => act(t.id, plan), { plan })}>${euro(p.price)}</span>`;
}

/** Circle on a product that adds it to (or removes it from) the products the next question refers to. */
function selectCircle(p) {
  const on = selected.has(p.id);
  return `<span class="select ${on ? "on" : ""}" role="checkbox" aria-checked="${on}" aria-label="Select ${esc(p.name)}"
    ${action(() => toggleSelected(p), { note: on ? "remove from your question" : "ask about this laptop" })}></span>`;
}

function toggleSelected(p) {
  selected.has(p.id) ? selected.delete(p.id) : selected.set(p.id, p);
  render();
}

const productLink = (t, p) => `<span class="view product-link" ${action(() => openProduct(t, p), { view: true })}>${esc(p.name)}</span>`;

const miniProduct = (p, attrs, remove = "", cls = "") =>
  `<span class="mini ${cls}" ${attrs}><img src="/img/${p.id}.svg" alt="" width="32" height="22">${esc(p.name)}${remove}</span>`;

function renderResult(t, large) {
  const a = t.answer;
  if (a.kind === "count") {
    return `<div class="count">${a.rows[0].laptops} <small>laptops</small></div>`;
  }
  if (a.kind === "offers") return offersTable(a.rows, a.product);
  if (a.kind === "group") return renderGroups(t);
  const rows = sortedRows(t).slice(0, visibleCount(t, large));
  if (!rows.length) return `<p class="panel-foot">No matching laptops.</p>`;
  if (t.ui.view === "cards") return renderCards(t, rows);
  if (t.ui.view === "list") return renderList(t, rows);
  const body = rows.map((p) => `<tr class="${selected.has(p.id) ? "selected" : ""}"><td>${selectCircle(p)}${productLink(t, p)}</td><td>${inch(p.display_in)} ${p.display_type}</td><td class="num">${p.ram_gb} GB</td>
    <td class="num">${p.weight_kg} kg</td><td class="num">${p.battery_h} h</td><td class="num">${p.rating}</td><td class="num">${priceLink(t, p)}</td></tr>`).join("");
  return `<table class="result"><tr><th>Model</th><th>Display</th><th class="num">RAM</th><th class="num">Weight</th>
    <th class="num">Battery</th><th class="num">Rating</th><th class="num">Price</th></tr>${body}</table>`;
}

function renderCards(t, rows) {
  return `<div class="cards">${rows.map((p) => `<div class="card view ${selected.has(p.id) ? "selected" : ""}" ${action(() => openProduct(t, p), { view: true })}>
      ${selectCircle(p)}
      <img src="/img/${p.id}.svg" alt="Placeholder image of the ${esc(p.name)}" width="160" height="110">
      <div class="name">${esc(p.name)}</div>
      <div class="specs">${inch(p.display_in)} ${p.display_type} · ${p.ram_gb} GB RAM · ${storage(p.storage_gb)}<br>
        ${p.weight_kg} kg · ${p.battery_h} h battery</div>
      <div class="bottom">${priceLink(t, p)}<span class="rating">${p.rating} / 5</span></div></div>`).join("")}</div>`;
}

const stars = (rating) => {
  const full = Math.round(rating);
  return `<span class="stars" aria-hidden="true">${"★".repeat(full)}<span class="off">${"★".repeat(5 - full)}</span></span>`;
};

/** Result list as in online shops: image on the left, details on the right. */
function renderList(t, rows) {
  return `<div class="list">${rows.map((p) => `<div class="list-item view ${selected.has(p.id) ? "selected" : ""}" ${action(() => openProduct(t, p), { view: true })}>
    ${selectCircle(p)}
    <img src="/img/${p.id}.svg" alt="Placeholder image of the ${esc(p.name)}" width="200" height="138">
    <div class="list-info">
      <div class="name">${esc(p.name)} – ${inch(p.display_in)} ${p.display_type}, ${p.ram_gb} GB RAM, ${storage(p.storage_gb)}</div>
      <div class="rating">${stars(p.rating)} ${p.rating} <span class="reviews">(${p.reviews})</span></div>
      <div class="price-line">${priceLink(t, p)}</div>
      <div class="delivery">Delivery ${delivery(p.delivery)}</div>
      <ul class="facts"><li>${p.weight_kg} kg</li><li>${p.battery_h} h battery</li><li>${esc(p.brand)}</li></ul>
    </div></div>`).join("")}</div>`;
}

function renderGroups(t) {
  const a = t.answer, plan = a.plan;
  const metricLabel = METRIC_LABELS[plan.metric];
  const body = a.rows.map((g) => {
    const open = t.ui.expanded.has(g.brand);
    const [attr, dir] = GROUP_MEMBER_SORT[plan.metric];
    const brandPlan = { kind: "list", filters: [...plan.filters, { attr: "brand", op: "=", value: g.brand }], sort: { attr, dir } };
    const toggle = settings.variant === "query"
      ? action(() => { open ? t.ui.expanded.delete(g.brand) : t.ui.expanded.add(g.brand); render(); }, { view: true })
      : action(() => act(t.id, brandPlan), { plan: brandPlan });
    let html = `<tr><td>${badge(t.ui.marks[`expand:${g.brand}`])}<span class="${settings.variant === "query" ? "view" : "act"}" ${toggle}>
      <span class="toggle">${open ? "▾" : "▸"}</span>${esc(g.brand)}</span></td>
      <td class="num">${g.models}</td><td class="num">${euro(g.avg_price)}</td><td class="num">${g.avg_battery.toFixed(1)} h</td>
      ${metricLabel ? `<td class="num">${plan.metric === "avg_rating" ? g.metric.toFixed(2) : g.metric.toFixed(1)}</td>` : ""}</tr>`;
    if (open) {
      html += g.members.map((p) => `<tr class="member"><td colspan="${metricLabel ? 4 : 3}">${productLink(t, p)}<span class="member-specs"><span class="sep"> · </span>${inch(p.display_in)} ${p.display_type} ·
        ${p.ram_gb} GB · ${p.weight_kg} kg · ${p.battery_h} h</span></td><td class="num">${priceLink(t, p)}</td></tr>`).join("");
      if (g.more) {
        html += `<tr class="member"><td colspan="${metricLabel ? 5 : 4}"><span class="act" ${action(() => act(t.id, brandPlan), { plan: brandPlan })}>… ${g.more} more ${esc(g.brand)} laptops</span></td></tr>`;
      }
    }
    return html;
  }).join("");
  return `<table class="result"><tr><th>Brand</th><th class="num">Models</th><th class="num">Avg. price</th><th class="num">Avg. battery</th>
    ${metricLabel ? `<th class="num">${metricLabel}</th>` : ""}</tr>${body}</table>`;
}

function renderFacets(t) {
  const facetTip = settings.variant === "action" ? null : { note: "filters this answer (no new turn)" };
  const active = activeFacets(t).map((f) => {
    const fmt = FACET_VALUES[f.attr] || String;
    const mark = t.ui.marks[`facet:${f.attr}:${f.value}`];
    return `${badge(mark)}<span class="chip on" ${action(() => removeFacet(t, f), { note: "removes this filter (no new turn)" })}>
      ${FACET_LABELS[f.attr]}: ${esc(fmt(f.value))} ✕</span>`;
  }).join("");
  const rows = (t.answer.facets || []).map((f) => {
    const fmt = FACET_VALUES[f.attr] || String;
    const values = f.values.map((v) => {
      const mark = t.ui.marks[`facet:${f.attr}:${v.value}`];
      return `${badge(mark)}<span class="chip ${mark ? "marked" : ""}" ${action(() => filterAnswer(t, v.plan), facetTip || { plan: v.plan })}>${esc(fmt(v.value))} (${v.count})</span>`;
    }).join("");
    return `<span class="label">${FACET_LABELS[f.attr]}</span><span class="values">${values}</span>`;
  }).join("");
  const filtered = active ? `<span class="label">Filtered</span><span class="values">${active}</span>` : "";
  return `<div class="facets">${filtered}${rows}</div>`;
}

/** Facet filters added to the answer in place, relative to the answer of the turn. */
function activeFacets(t) {
  if (!t.base) return [];
  const base = t.base.plan.filters.map((f) => JSON.stringify(f));
  return t.answer.plan.filters.filter((f) => !base.includes(JSON.stringify(f)));
}

/** A facet value filters the answer in place (view change); with "Every action is a turn" it poses a turn. */
async function filterAnswer(t, plan) {
  if (settings.variant === "action") return act(t.id, plan);
  if (busy) return;
  busy = true;
  t.base = t.base || t.answer;
  t.ui.filtering = true;
  render();
  try {
    t.answer = (await post("/api/query", { plan })).answer;
  } catch (error) {
    console.error(error);
  }
  t.ui.filtering = false;
  busy = false;
  render();
}

function removeFacet(t, facet) {
  const rest = activeFacets(t).filter((f) => f !== facet);
  if (!rest.length) {
    t.answer = t.base;
    t.base = null;
    return render();
  }
  let filters = t.base.plan.filters;
  for (const f of rest) filters = [...filters.filter((g) => g.attr !== f.attr), f];
  filterAnswer(t, { ...t.base.plan, filters });
}

function switchTo(turn) {
  let t = turn;
  for (let next = children(t.id); next.length; next = children(t.id)) t = next[next.length - 1];
  leaf = t.id;
  render();
}

function offersTable(rows, product) {
  if (!rows.length) return `<p class="panel-foot">No offers.</p>`;
  const body = rows.map((o, i) => `<tr><td>${esc(o.shop)}${i === 0 ? ` <span class="best">best price</span>` : ""}</td>
    <td>Delivery ${o.delivery_days === 1 ? "tomorrow" : `in ${o.delivery_days} days`}</td>
    <td class="num price-cell">${euro(o.price)}</td>
    <td class="num">${cartButton(product, o, "small")}</td></tr>`).join("");
  return `<table class="offers"><tr><th>Shop</th><th>Delivery</th><th class="num">Price</th><th></th></tr>${body}</table>`;
}

/** The cheapest offer that meets the delivery condition of the answer the product was found in. */
function bestOffer(t, offers) {
  const condition = deliveryFilters(t.answer && t.answer.plan)[0];
  const days = condition ? DELIVERY_DAYS[condition.value] : Infinity;
  return offers.find((o) => o.delivery_days <= days) || offers[0];
}

/** Fake shopping cart: adding is a view change, nothing is ordered. */
function cartButton(product, offer, cls = "") {
  const label = cls === "small" ? "Add to cart" : `Add to cart · ${euro(offer.price)} at ${esc(offer.shop)}`;
  return `<button type="button" class="cart-add ${cls}" ${action(() => addToCart(product, offer), { note: "demo: adds it to the cart, nothing is ordered" })}>${label}</button>`;
}

function addToCart(product, offer) {
  const toast = $("#toast");
  toast.textContent = `${product.name} from ${offer.shop} (${euro(offer.price)}) added to the cart. This is a demo: nothing is ordered.`;
  toast.hidden = false;
  clearTimeout(addToCart.timer);
  addToCart.timer = setTimeout(() => { toast.hidden = true; }, 3500);
}

// ---------------------------------------------------------------------------------------------------
// Stage: enlarged answers and product pages on the full page, the composer stays

function openStage(next) {
  if (!stage) chatScroll = window.scrollY;
  stage = next;
  hideTip();
  $("#chat").hidden = true;
  $("#stage").hidden = false;
  render();
  window.scrollTo(0, 0);
}

function closeStage(restore = true) {
  if (!stage) return;
  stage = null;
  $("#stage").hidden = true;
  $("#chat").hidden = false;
  render();
  if (restore) window.scrollTo(0, chatScroll);
}

const enlarge = (t) => openStage({ kind: "answer", turn: t });

async function openProduct(t, p) {
  const next = { kind: "product", turn: t, product: p, offers: null };
  openStage(next);
  const data = await (await fetch(`/api/product/${p.id}`)).json();
  if (stage !== next) return;
  next.offers = data.offers;
  render();
}

function renderStage() {
  const close = `<button type="button" class="stage-close" ${action(() => closeStage(), { note: "back to the dialog" })}>✕ Close</button>`;
  if (stage.kind === "answer") {
    const t = stage.turn;
    return `<div class="stage-wrap"><div class="stage-bar"><h2>${esc(t.answer.interpretation)}</h2>${close}</div>
      <div class="panel">${renderResult(t, true)}</div></div>`;
  }
  const { turn: t, product: p, offers } = stage;
  const on = selected.has(p.id);
  const specs = [
    ["Display", `${inch(p.display_in)} ${p.display_type}`], ["RAM", `${p.ram_gb} GB`], ["Storage", storage(p.storage_gb)],
    ["Weight", `${p.weight_kg} kg`], ["Battery", `${p.battery_h} h`], ["Delivery", delivery(p.delivery)],
  ].map(([k, v]) => `<tr><th>${k}</th><td>${v}</td></tr>`).join("");
  return `<div class="stage-wrap"><div class="stage-bar"><h2>${[p.brand, p.series].filter(Boolean).map(esc).join(" · ")}</h2>${close}</div>
    <div class="product-page">
      <div class="product-image ${on ? "selected" : ""}">${selectCircle(p)}
        <img src="/img/${p.id}.svg" alt="Placeholder image of the ${esc(p.name)}" width="480" height="330"></div>
      <div class="product-info">
        <h1>${esc(p.name)}</h1>
        <div class="product-rating">${p.rating} / 5${p.reviews ? ` · ${p.reviews} reviews` : ""}</div>
        <div class="product-price">from ${priceLink(t, p)}</div>
        <table class="result specs">${specs}</table>
        <div class="buy-row">${offers && offers.length ? cartButton(p, bestOffer(t, offers), "primary") : ""}
          <button type="button" ${action(() => toggleSelected(p), { note: on ? "remove from your questions" : "keeps it attached after closing this page" })}>
            ${on ? "✓ Selected" : "Select for your questions"}</button></div>
      </div>
    </div>
    <div class="offers-section"><h3>Shop offers</h3>
    <div class="panel">${offers ? offersTable(offers, p) : `<p class="pending">Loading offers …</p>`}</div></div></div>`;
}

/** The product on view, if it is not selected: attached to questions asked on its page only. */
const onView = () => (stage && stage.kind === "product" && !selected.has(stage.product.id) ? stage.product : null);

/** Products attached to the next question: the selected ones and the product on view. */
const attachments = () => [...selected.values(), ...(onView() ? [onView()] : [])];

function takeAttachments() {
  const list = attachments();
  selected.clear();
  return list;
}

function renderSelection() {
  const box = $("#selection");
  const list = attachments();
  box.hidden = !list.length;
  $("#question").placeholder = list.length === 1 ? `Ask about the ${list[0].name} …`
    : list.length ? `Ask about the ${list.length} selected laptops …` : "Ask about the laptops in the catalog …";
  if (!list.length) { box.innerHTML = ""; return; }
  const chip = (p) => (p === onView()
    ? miniProduct(p, `title="The product on this page"`, "", "fixed")
    : miniProduct(p, "", `<button type="button" class="mini-remove" aria-label="Remove ${esc(p.name)}"
      ${action(() => toggleSelected(p), { note: "remove from your question" })}>✕</button>`));
  const clear = selected.size
    ? `<button type="button" class="selection-clear" ${action(() => { selected.clear(); render(); })}>Clear</button>` : "";
  box.innerHTML = `<span class="selection-label">Your question refers to</span>${list.map(chip).join("")}${clear}`;
}

// ---------------------------------------------------------------------------------------------------
// Events

document.addEventListener("click", (event) => {
  const el = event.target.closest("[data-action]");
  if (!el || el.tagName === "SELECT") return;
  const entry = actions.get(el.dataset.action);
  if (entry && entry.fn) {
    event.preventDefault();
    hideTip();
    entry.fn();
  }
});

document.addEventListener("change", (event) => {
  const el = event.target.closest("select[data-action]");
  const entry = el && actions.get(el.dataset.action);
  if (entry && entry.change) entry.change(el.value);
});

// Hover preview: the question a click would pose (P4), or a note that the view changes only.
const tip = $("#tooltip");
const tipCache = new Map();
function hideTip() { tip.hidden = true; }
document.addEventListener("mouseover", async (event) => {
  const el = event.target.closest("[data-action]");
  const entry = el && actions.get(el.dataset.action);
  if (!entry || !entry.tip) return hideTip();
  let text;
  if (entry.tip.view) text = "stays in this answer (no new turn)";
  else if (entry.tip.note) text = entry.tip.note;
  else if (entry.tip.text) text = entry.tip.text;
  else {
    const key = JSON.stringify(entry.tip.plan);
    if (!tipCache.has(key)) tipCache.set(key, post("/api/verbalize", { plan: entry.tip.plan }).then((r) => r.question));
    text = await tipCache.get(key);
  }
  if (event.target.closest("[data-action]") !== el) return;
  const box = el.getBoundingClientRect();
  tip.textContent = text;
  tip.style.left = `${box.left + window.scrollX}px`;
  tip.style.top = `${box.bottom + window.scrollY + 6}px`;
  tip.hidden = false;
});
document.addEventListener("mouseout", (event) => { if (event.target.closest("[data-action]")) hideTip(); });

document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeStage(); });

$("#composer").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("#question");
  const text = input.value.trim();
  if (!text || busy) return;
  input.value = "";
  ask(leaf, text, null, null, takeAttachments());
});

$("#restart").addEventListener("click", () => { selected.clear(); closeStage(false); start(); });
if (settings.figure) document.body.classList.add("figure");
if (settings.figure && params.get("composer") === "1") document.body.classList.add("with-composer");

// ---------------------------------------------------------------------------------------------------
// Scripted sessions for figures

function lastSystem() { return path().filter((t) => t.role === "system").pop(); }

async function replay(steps) {
  replaying = true;
  const until = params.has("until") ? Number(params.get("until")) : steps.length;
  if (Math.min(until, steps.length)) document.body.classList.add("hide-start");  // figures start with a question
  for (const step of steps.slice(0, until)) {
    const t = lastSystem();
    const a = t.answer;
    const find = (name) => a.rows.find((r) => r.name === name) || a.rows.flatMap((g) => g.members || []).find((r) => r.name === name);
    if (step.ask) {
      $("#question").value = "";
      document.body.classList.remove("composing");
      await ask(t.id, step.ask, null, step.badge, takeAttachments());
    } else if (step.select) {
      selected.set(find(step.select).id, find(step.select));
      document.body.classList.add("composing");
      render();
    } else if (step.open) {
      await openProduct(t, find(step.open));
    } else if (step.type) {
      $("#question").value = step.type;
      document.body.classList.add("composing");
    } else if (step.facet) {
      const [attr, value] = step.facet;
      const v = a.facets.find((f) => f.attr === attr).values.find((x) => x.value === value);
      t.ui.marks[`facet:${attr}:${value}`] = step.badge;
      await filterAnswer(t, v.plan);
    } else if (step.expand) {
      t.ui.marks[`expand:${step.expand}`] = step.badge;
      if (settings.variant === "query") { t.ui.expanded.add(step.expand); render(); }
    } else if (step.price) {
      const p = find(step.price);
      await act(t.id, offersPlan(t, p), "written for your click", step.badge);
    } else if (step.choose !== undefined) {
      t.ui.marks[`choose:${step.choose}`] = step.badge;  // the badge marks the candidate, not the turn
      await act(t.id, a.candidates[step.choose].plan, "chosen interpretation");
    } else if (step.query !== undefined) {
      t.ui.marks[`sql:${step.query}`] = true;
      render();
    } else if (step.followup !== undefined) {
      await act(t.id, a.followups[step.followup].plan, "suggested follow-up", step.badge);
    } else if (step.view) {
      t.ui.view = step.view;
      render();
    } else if (step.sort) {
      await sortBy(t, step.sort);
    } else if (step.close) {
      closeStage();
    } else if (step.cart) {
      addToCart(a.product, a.rows[0]);
      clearTimeout(addToCart.timer);  // keep the notice for the frame
    }
  }
  replaying = false;
  if (params.has("until")) {
    // Storyboard frame: the latest exchange and the answer before it, at the top of the page.
    const hidden = thread.children.length - Number(params.get("last") || 3);
    [...thread.children].forEach((el, i) => { if (i < hidden) el.classList.add("earlier"); });
  }
  window.scrollTo(0, 0);
  document.body.dataset.ready = "1";
}

start().then(() => {
  const name = params.get("scenario");
  if (name && window.SCENARIOS && window.SCENARIOS[name]) replay(window.SCENARIOS[name]);
  else document.body.dataset.ready = "1";
});
