"use strict";
// All text from the server (GitHub content, model answers) is untrusted:
// it is only ever inserted with textContent / createTextNode, never as HTML.

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const clear = (el) => { el.replaceChildren(); return el; };
const pct = (x) => (x === null || x === undefined ? "n/a" : Math.round(x * 100) + "%");
const day = (s) => (s || "").slice(0, 10);
const num = (n) => Number(n).toLocaleString();

async function api(path, opts) {
  const r = await fetch(path, opts);
  let j = {};
  try { j = await r.json(); } catch (e) { /* not JSON */ }
  if (!r.ok) throw new Error(j.error || `Request failed (${r.status})`);
  return j;
}
const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

let repo = null;
const loaded = {};

// ---- references like [pr:#123] become clickable when they can be opened ----
const REF = /\[((?:commit|pr|issue|review|fact|code|cochange):[^\]\s]+)\]/g;
function rich(text) {
  const frag = document.createDocumentFragment();
  let last = 0, m;
  REF.lastIndex = 0;
  while ((m = REF.exec(text)) !== null) {
    frag.append(document.createTextNode(text.slice(last, m.index)));
    const ref = m[1];
    frag.append(/^(commit|pr|issue):/.test(ref)
      ? h("a", { class: "ref", title: "Open details", onclick: () => openItem(ref) }, `[${ref}]`)
      : h("span", { class: "refplain" }, `[${ref}]`));
    last = m.index + m[0].length;
  }
  frag.append(document.createTextNode(text.slice(last)));
  return frag;
}

// ---- tabs -------------------------------------------------------------
function showTab(name) {
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + name));
  if (!repo) return;
  if (!loaded[name]) { loaded[name] = true; ({ overview: loadOverview, risk: loadRisk, map: loadMap, ask: loadExamples })[name]?.(); }
}
$$("#tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

const R = () => `/api/repo/${repo}`;
function failure(box, e) { clear(box).append(h("p", { class: "warn" }, e.message)); }

// ---- repositories -----------------------------------------------------
async function loadRepos(select) {
  const repos = await api("/api/repos");
  const sel = $("#repo");
  clear(sel);
  repos.forEach((r) => sel.append(h("option", { value: r.repo }, `${r.repo} (${num(r.commits)} commits)`)));
  if (select && repos.some((r) => r.repo === select)) sel.value = select;
  if (repos.length) selectRepo(sel.value);
}
function selectRepo(r) {
  repo = r;
  Object.keys(loaded).forEach((k) => delete loaded[k]);
  [ "#askOut", "#codeOut", "#searchOut", "#histOut", "#network" ].forEach((s) => clear($(s)));
  const active = $("#tabs button.active").dataset.tab;
  loaded[active] = false;
  showTab(active);
}
$("#repo").addEventListener("change", (e) => selectRepo(e.target.value));

// ---- overview ---------------------------------------------------------
async function loadOverview() {
  const box = clear($("#stats"));
  box.append(h("p", { class: "muted" }, "Loading… (large repositories take a few seconds the first time)"));
  try {
    const o = await api(R() + "/overview");
    clear(box);
    const c = o.counts;
    [["Commits", c.commits], ["Files", c.files], ["Human committers", c.human_committers], ["Bot identities", c.bot_identities],
     ["Pull requests", c.pull_requests], ["Issues", c.issues], ["Reviews", c.reviews]]
      .forEach(([label, v]) => box.append(h("div", { class: "card" }, h("b", {}, num(v)), h("span", {}, label))));
    const t = h("table", {}, h("tr", {}, h("th", {}, "Author"), h("th", {}, "Commits")));
    o.top_contributors.forEach((p) => t.append(h("tr", {}, h("td", {}, p.name), h("td", {}, num(p.commits)))));
    clear($("#contrib")).append(t);
    const max = Math.max(...o.commits_per_year.map((y) => y.commits), 1);
    const years = clear($("#years"));
    o.commits_per_year.forEach((y) => years.append(h("div", { class: "bar" }, h("span", {}, y.year), h("i", { style: `width:${(y.commits / max) * 100}%` }), h("span", {}, num(y.commits)))));
    const k = o.concentration, lv = k.risk_levels;
    clear($("#conc")).append(
      h("p", {}, `${k.components_with_one_author_at_80pct} of ${k.components_ranked} components (folders with at least 5 commits) had a single author making 80% or more of their commits.`),
      h("div", { class: "chips" }, ["high", "medium", "low", "dormant", "insufficient_evidence"].filter((l) => lv[l]).map((l) => h("span", { class: `lv lv-${l}` }, `${l.replace("_", " ")}: ${lv[l]}`))),
      h("p", { class: "muted small" }, `Risk levels are heuristic signals as of the latest commit (${day(k.as_of)}), not findings about any person. See the Risk tab for the evidence.`));
    $("#stats").append(h("div", { class: "card" }, h("b", {}, `${day(o.first_commit).slice(0, 4)}–${day(o.last_commit).slice(0, 4)}`), h("span", {}, "History span")));
  } catch (e) { failure(box, e); }
}

// ---- risk -------------------------------------------------------------
async function loadRisk() {
  const table = clear($("#riskTable"));
  $("#riskNote").textContent = "Loading… (large repositories take a few seconds the first time)";
  try {
    const r = await api(`${R()}/risk?depth=${$("#riskDepth").value}&active_days=${$("#riskDays").value}`);
    $("#riskNote").textContent = r.note + ` As of ${day(r.as_of)}.` + (r.components_total > r.components.length ? ` Showing the ${r.components.length} highest-priority of ${r.components_total} components.` : "");
    clear($("#riskLevels")).append(...Object.entries(r.level_counts).map(([l, n]) => h("span", { class: `lv lv-${l}` }, `${l.replace("_", " ")}: ${n}`)));
    table.append(h("tr", {}, ["Component", "Level", "Recent commits", "Active / total authors", "Bus factor", "Top active author", "History from inactive authors", "Signals"].map((x) => h("th", {}, x))));
    r.components.forEach((c) => table.append(h("tr", {},
      h("td", {}, c.component),
      h("td", {}, h("span", { class: `lv lv-${c.level}` }, c.level.replace("_", " "))),
      h("td", {}, c.recent_commits), h("td", {}, c.active_developers === undefined || c.active_developers === null ? "" : `${c.active_developers} / ${c.total_developers}`),
      h("td", {}, c.bus_factor_active ?? ""), h("td", {}, c.top_active_developer ? `${c.top_active_developer} (${pct(c.top_active_share)})` : ""),
      h("td", {}, c.departed_share === undefined || c.departed_share === null ? "" : pct(c.departed_share)),
      h("td", { class: "small" }, c.signals.length ? c.signals.join("; ") : (c.level === "dormant" ? "no commits in the window" : c.level === "insufficient_evidence" ? "too few commits" : "none triggered")))));
  } catch (e) { failure(table, e); }
}
$("#riskGo").addEventListener("click", loadRisk);

// ---- knowledge map ----------------------------------------------------
async function loadMap() {
  const msg = $("#mapMsg"), box = clear($("#network"));
  msg.textContent = "Loading…";
  try {
    const g = await api(`${R()}/map?top=${$("#mapTop").value}`);
    if (!window.vis) { msg.textContent = "The map library could not be loaded (it comes from a CDN; check your internet connection)."; return; }
    msg.textContent = `${g.nodes.length} nodes, ${g.edges.length} links. Drag, zoom and hover to explore.`;
    g.nodes.forEach((n) => {
      const dev = n.group === "developer";
      n.color = dev ? { background: "#4f8cff", border: "#2f5fbf" } : { background: "#ff9d4f", border: "#cc7a2f" };
      n.size = dev ? 10 + Math.min(n.value, 300) / 12 : 6 + Math.min(n.value, 100) / 10;
      n.font = { size: dev ? 14 : 11 };
    });
    g.edges.forEach((e) => { e.width = Math.max(1, Math.min(e.value, 30) / 4); e.color = { color: "#8a93a3", opacity: 0.5 }; });
    new vis.Network(box, { nodes: new vis.DataSet(g.nodes), edges: new vis.DataSet(g.edges) },
      { physics: { stabilization: true, barnesHut: { gravitationalConstant: -8000, springLength: 120 } }, interaction: { hover: true } });
  } catch (e) { msg.textContent = e.message; }
}
$("#mapGo").addEventListener("click", loadMap);

// ---- results shared by Ask and Code -----------------------------------
function renderLLM(out, llm) {
  if (!llm) return;
  if (!llm.ok) {
    out.append(h("div", { class: "warn" }, `The AI could not answer: ${llm.error}`, h("br"), "The evidence it would have used is shown below."));
    return;
  }
  const card = h("div", { class: "panel" }, h("h2", {}, "Answer"), h("div", { class: "answer" }, rich(llm.answer)));
  if (llm.invalid_citations?.length) card.append(h("div", { class: "warn" }, "This answer cites sources that were not in the evidence: " + llm.invalid_citations.join(", ")));
  if (llm.unverified_identifiers?.length) card.append(h("div", { class: "warn" }, "This answer mentions numbers or hashes that do not appear in the evidence: " + llm.unverified_identifiers.join(", ")));
  const u = llm.usage || {};
  card.append(h("p", { class: "ok-note" }, `Written by ${llm.model || "the model"} from the evidence below. Citations only prove a source exists, not that it supports the sentence; check the ones that matter.` + (u.prompt_tokens ? ` (${num(u.prompt_tokens)} tokens in, ${num(u.output_tokens || 0)} out)` : "")));
  out.append(card);
}
function renderEvidence(out, o, title) {
  const panel = h("div", { class: "panel" }, h("h2", {}, title));
  (o.notes || []).forEach((n) => panel.append(h("p", { class: "warn" }, n)));
  if (o.empty || !o.evidence_text) {
    panel.append(h("p", {}, "No repository evidence was found for this question, so there is nothing to answer from. Try naming a file, a PR/issue number or a person that exists in this repository."));
  } else {
    panel.append(h("details", { open: true }, h("summary", {}, "Evidence used (click a [commit], [pr] or [issue] reference to open it)"), h("pre", { class: "evidence" }, rich(o.evidence_text))));
  }
  out.append(panel);
}

// ---- ask --------------------------------------------------------------
async function loadExamples() {
  const box = clear($("#examples"));
  try {
    const files = await api(`${R()}/files?q=`);
    const f = files[0]?.path;
    const dir = f && f.includes("/") ? f.split("/").slice(0, -1).join("/") : null;
    const ex = f ? [`Who has worked most on ${f}?`, `Who reviewed changes to ${f}?`, `What changed recently in ${f}?`, ...(dir ? [`What is the bus factor of ${dir}?`] : [])] : [];
    ex.forEach((q) => box.append(h("button", { class: "chip", onclick: () => { $("#question").value = q; ask(); } }, q)));
  } catch (e) { /* examples are optional */ }
}
async function ask() {
  const out = clear($("#askOut")), btn = $("#askGo");
  btn.disabled = true;
  out.append(h("p", { class: "muted" }, "Searching the repository history…"));
  try {
    const o = await post(R() + "/ask", { question: $("#question").value, use_llm: $("#askAI").checked });
    clear(out);
    out.append(h("p", { class: "muted small" }, `Understood as: ${o.plan.intents.join(", ")}` + (o.plan.scopes.length ? ` about ${o.plan.scopes.join(", ")}` : "")));
    renderLLM(out, o.llm);
    renderEvidence(out, o, "Evidence");
  } catch (e) { failure(out, e); }
  btn.disabled = false;
}
$("#askGo").addEventListener("click", ask);
$("#question").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } });

// ---- code -------------------------------------------------------------
let fileTimer;
$("#codeFile").addEventListener("input", (e) => { clearTimeout(fileTimer); fileTimer = setTimeout(() => suggestFiles(e.target.value), 200); });
$("#histFile").addEventListener("input", (e) => { clearTimeout(fileTimer); fileTimer = setTimeout(() => suggestFiles(e.target.value), 200); });
async function suggestFiles(text, min = 2) {
  if (!repo || text.length < min) return;
  try { clear($("#fileList")).append(...(await api(`${R()}/files?q=${encodeURIComponent(text)}`)).map((f) => h("option", { value: f.path }, `${f.commits} commits`))); } catch (e) { /* optional */ }
}
$("#codeFile").addEventListener("focus", () => suggestFiles("", 0));
$("#histFile").addEventListener("focus", () => suggestFiles("", 0));
$("#codeFile").addEventListener("change", async (e) => {
  const sel = clear($("#codeFn"));
  sel.append(h("option", { value: "" }, "(none: use lines or whole file)"));
  try {
    const s = await api(`${R()}/symbols?path=${encodeURIComponent(e.target.value)}`);
    s.symbols.forEach((x) => sel.append(h("option", { value: x.name }, `${x.name} (${x.kind}, lines ${x.start}-${x.end})`)));
    if (s.note) sel.append(h("option", { value: "", disabled: true }, s.note));
  } catch (err) { /* function list is optional */ }
});
async function runCode() {
  const out = clear($("#codeOut")), btn = $("#codeGo");
  btn.disabled = true;
  out.append(h("p", { class: "muted" }, "Reading the code and its history…"));
  try {
    const mode = $('input[name="mode"]:checked').value;
    const o = await post(R() + "/code", { mode, path: $("#codeFile").value.trim(), function: $("#codeFn").value, lines: $("#codeLines").value, text: $("#codeText").value, use_llm: $("#codeAI").checked });
    clear(out);
    out.append(h("p", { class: "muted small" }, `${mode === "brief" ? "Briefing for" : "Explanation of"} ${o.target} (lines ${o.lines[0]}-${o.lines[1]})`));
    renderLLM(out, o.llm);
    renderEvidence(out, o, mode === "brief" ? "Evidence for the briefing" : "The code and its history");
  } catch (e) { failure(out, e); }
  btn.disabled = false;
}
$("#codeGo").addEventListener("click", runCode);

// ---- history ----------------------------------------------------------
async function search() {
  const out = clear($("#searchOut"));
  try {
    const r = await api(`${R()}/search?q=${encodeURIComponent($("#searchQ").value)}`);
    if (!r.results.length) out.append(h("p", { class: "muted" }, "Nothing matched."));
    r.results.forEach((x) => out.append(h("div", { class: "result", onclick: () => /^(commit|pr|issue):/.test(x.ref) && openItem(x.ref) },
      h("span", { class: "lv lv-dormant" }, x.ref), " ", h("b", {}, x.title), h("br"), h("small", {}, `${day(x.date)} ${x.author || ""}`), x.snippet && x.kind !== "commit" ? h("div", { class: "small muted" }, x.snippet) : null)));
  } catch (e) { failure(out, e); }
}
$("#searchGo").addEventListener("click", search);
$("#searchQ").addEventListener("keydown", (e) => e.key === "Enter" && search());
async function fileHistory() {
  const out = clear($("#histOut"));
  try {
    const f = await api(`${R()}/file?path=${encodeURIComponent($("#histFile").value.trim())}`);
    const c = f.contributors;
    out.append(h("h3", {}, `Commit authors (${c.total_commits} commits, bots excluded)`),
      h("table", {}, c.contributors.map((p) => h("tr", {}, h("td", {}, p.name), h("td", {}, p.commits), h("td", {}, pct(p.share)), h("td", { class: "muted small" }, "last " + day(p.last_commit))))),
      h("h3", {}, "Reviewers of related pull requests"),
      f.reviewers.length ? h("table", {}, f.reviewers.map((p) => h("tr", {}, h("td", {}, p.name), h("td", {}, p.prs_reviewed + " PRs"), h("td", { class: "muted small" }, "last " + day(p.last_review))))) : h("p", { class: "muted small" }, "none found"),
      h("h3", {}, "Recent changes"),
      ...f.history.map((x) => h("div", { class: "result", onclick: () => openItem("commit:" + x.sha.slice(0, 7)) }, h("small", {}, `${day(x.date)} ${x.author}`), h("br"), x.subject)),
      h("h3", {}, "Pull requests"),
      ...f.prs.map((p) => h("div", { class: "result", onclick: () => openItem("pr:#" + p.number) }, h("b", {}, "#" + p.number), " " + p.title, h("br"), h("small", {}, `${p.state} ${day(p.merged_at || p.created_at)} by ${p.author} (${p.link === "linked" ? "linked by GitHub" : "inferred from commit subject"})`))));
  } catch (e) { failure(out, e); }
}
$("#histGo").addEventListener("click", fileHistory);

// ---- detail drawer ----------------------------------------------------
function section(title, ...kids) { return [h("h3", {}, title), ...kids]; }
async function openItem(ref) {
  const body = clear($("#drawerBody"));
  $("#drawer").hidden = false;
  body.append(h("p", { class: "muted" }, "Loading…"));
  try {
    const it = await api(`${R()}/item?ref=${encodeURIComponent(ref)}`);
    clear(body);
    if (it.type === "pr") {
      body.append(h("h2", {}, `PR #${it.number}: ${it.title}`), h("p", { class: "muted small" }, `${it.state}, by ${it.author}, created ${day(it.created_at)}, merged ${day(it.merged_at) || "no"}`),
        h("div", { class: "answer" }, it.body || "(no description)"),
        ...section("Reviews", it.reviews.length ? h("ul", {}, it.reviews.map((r) => h("li", {}, `${r.reviewer}: ${r.state} (${day(r.submitted_at)})`))) : h("p", { class: "muted small" }, "none recorded")),
        ...section("Closes issues", it.closes_issues.length ? h("ul", {}, it.closes_issues.map((i) => h("li", {}, h("a", { class: "ref", onclick: () => openItem("issue:#" + i.number) }, "#" + i.number), " " + i.title))) : h("p", { class: "muted small" }, "none")),
        ...section("Files changed", it.files.length ? h("ul", {}, it.files.map((f) => h("li", {}, f))) : h("p", { class: "muted small" }, "not linked (this repository may squash-merge)")));
    } else if (it.type === "issue") {
      body.append(h("h2", {}, `Issue #${it.number}: ${it.title}`), h("p", { class: "muted small" }, `${it.state}, by ${it.author}, opened ${day(it.created_at)}, closed ${day(it.closed_at) || "no"}`),
        h("div", { class: "answer" }, it.body || "(no description)"),
        ...section("Closed by pull requests", it.closed_by_prs.length ? h("ul", {}, it.closed_by_prs.map((p) => h("li", {}, h("a", { class: "ref", onclick: () => openItem("pr:#" + p.number) }, "#" + p.number), " " + p.title))) : h("p", { class: "muted small" }, "none linked")));
    } else {
      body.append(h("h2", {}, `Commit ${it.sha.slice(0, 7)}`), h("p", { class: "muted small" }, `${day(it.date)} by ${it.author}`), h("p", {}, h("b", {}, it.subject)),
        it.body ? h("div", { class: "answer" }, it.body) : null,
        ...section("Files", h("ul", {}, it.files.map((f) => h("li", {}, `${f.path} (+${f.additions ?? 0} −${f.deletions ?? 0})`)))),
        ...section("Pull request", it.prs_linked.length || it.pr_from_subject ? h("p", {}, h("a", { class: "ref", onclick: () => openItem("pr:#" + (it.prs_linked[0] || it.pr_from_subject)) }, "#" + (it.prs_linked[0] || it.pr_from_subject)), it.prs_linked.length ? "" : " (inferred from the commit subject)") : h("p", { class: "muted small" }, "none found")));
    }
  } catch (e) { failure(body, e); }
}
$("#drawerClose").addEventListener("click", () => { $("#drawer").hidden = true; });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#drawer").hidden = true; });

// ---- add repository ---------------------------------------------------
let poll;
const announced = new Set();
$("#addBtn").addEventListener("click", () => { $("#addErr").textContent = ""; $("#addDialog").showModal(); });
$("#addStart").addEventListener("click", async (e) => {
  e.preventDefault();
  try {
    await post("/api/jobs", { repo: $("#addRepo").value.trim(), skip_github: $("#addSkip").checked });
    $("#addDialog").close();
    pollJobs();
  } catch (err) { $("#addErr").textContent = err.message; }
});
async function pollJobs() {
  clearTimeout(poll);
  const jobs = await api("/api/jobs");
  const running = jobs.find((j) => j.status === "running");
  const last = jobs[jobs.length - 1];
  const s = $("#jobStatus");
  if (running) {
    s.textContent = `Adding ${running.repo}… ${running.seconds}s ` + (running.log_tail.length ? "· " + running.log_tail[running.log_tail.length - 1].slice(0, 70) : "");
    poll = setTimeout(pollJobs, 3000);
  } else if (last && !announced.has(last.repo + last.status)) {
    announced.add(last.repo + last.status);
    s.textContent = last.status === "done" ? `${last.repo} added.` : `Adding ${last.repo} failed: ${last.log_tail.slice(-1)[0] || "see data/processed/_ui logs"}`;
    if (last.status === "done") loadRepos(last.repo);
  }
}

// ---- start ------------------------------------------------------------
loadRepos().then(pollJobs).catch((e) => { document.body.prepend(h("p", { class: "warn" }, e.message)); });
