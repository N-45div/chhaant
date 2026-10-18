// Chhaant page: start a run, follow its trace, answer questions, open evidence.
const $ = (sel) => document.querySelector(sel);
const photo = (ref, w = 160) => `/api/photo?ref=${encodeURIComponent(ref)}&w=${w}`;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const angle = (l) => ("azimuth" in l ? (l.azimuth == null ? "overhead" : `${l.azimuth}°`) : "side photo");
const fmtForecast = (f) => (f ? `${f.days} days left (${f.low}-${f.high})` : "no shelf-life number");

let runId = null, cursor = 0, timer = null, items = {}, live = false;
const answered = new Set();

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, body };
}

async function loadCrate() {
  const { body } = await api("/api/crate?seed=3");
  $("#crate").innerHTML = body.items.map((i) =>
    `<div class="thumb" title="${esc(i.produce)}"><img src="${photo(i.thumb)}" alt="${esc(i.item_id)}, ${esc(i.produce)}"><span>${esc(i.item_id)}</span></div>`).join("");
}

function li(cls, html) {
  const feed = $("#feed");
  const following = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 120;
  const el = document.createElement("li");
  el.className = `ev ${cls}`;
  el.innerHTML = html;
  feed.appendChild(el);
  if (live && following) feed.scrollTop = feed.scrollHeight;  // follow a live run inside the feed only
  return el;
}

function renderToolResult(tool, input, out) {
  if (!out.ok) return li("refused", `<div class="head">The cell refused: ${esc(tool)}</div>${esc(out.error)}`);
  if (tool === "inspect") {
    const routes = (out.routing_for_open_lines || []).map((r) => `<div class="small">line ${r.line}: <b>${esc(r.action)}</b>, ${esc(r.reason)}</div>`).join("");
    const el = li("inspect", `<div class="head">Inspected ${esc(out.item_id)} (${esc(out.produce)}) <span class="pill ${esc(out.verdict)}">${esc(out.verdict)}</span>
      <button class="link" data-item="${esc(out.item_id)}">evidence</button></div>
      <div class="small">${esc(out.capability)}</div>
      <div class="small">${out.views_used} views${out.coverage != null ? `, ${Math.round(out.coverage * 100)}% of the surface inspected` : ""}${out.defect_score != null ? `, agreed defect score ${out.defect_score}` : ""}; ${esc(fmtForecast(out.forecast_days_left))}</div>
      <div class="views" data-views="${esc(out.item_id)}"></div>${routes}`);
    fillViews(out.item_id, el.querySelector(".views"));
    return el;
  }
  if (tool === "look_closer") return li("action", `<div class="head">Looked closer at ${esc(out.item_id)}, ${out.azimuth}°</div>
      <div class="views"><div class="view"><img src="${photo(out.photo, 152)}" alt="">defect ${out.defect}</div></div>`);
  if (tool === "place") return li("action", `<div class="head">${esc(input.item_id)} → ${esc(out.now)}</div><div class="small">${esc(input.reason || "")}</div>`);
  if (tool === "read_order") return li("action", `<div class="head">Read the order</div>` +
      out.order.map((l) => `<div class="small">line ${l.line}: ${l.quantity} × ${esc(l.produce)}, ${l.eat_in_days == null ? "no timing" : `eaten in ${l.eat_in_days} days`} (${l.in_crate} in crate)</div>`).join(""));
  if (tool === "finish") return li("model", `<b>Done.</b> ${out.order.map((l) => `line ${l.line}: ${l.packed.length ? esc(l.packed.join(", ")) : "nothing"}${l.short_by ? ` (short by ${l.short_by})` : ""}`).join("; ")}`);
  return null;
}

// A photo that failed the capture checks was never scored: say why instead of showing a number.
const unusable = (l) => (l.problem ? `<br><span class="unusable">not used: ${esc(l.problem)}</span>` : "");

async function fillViews(itemId, box) {
  const { body } = await api(`/api/runs/${runId}/items/${itemId}`);
  const looks = body.inspection?.looks || [];
  box.innerHTML = looks.map((l) => `<div class="view"><img src="${photo(l.photo, 152)}" alt="view of ${esc(itemId)}">
    ${angle(l)}${l.defect != null ? `<br>defect ${l.defect}` : ""}${l.ripeness != null ? `<br>ripe ${l.ripeness}` : ""}${unusable(l)}</div>`).join("");
}

function renderEvent(e) {
  if (e.kind === "start") return li("model", `<b>Order:</b> ${esc(e.order)}`);
  if (e.kind === "model" && e.text) return li("model", esc(e.text));
  if (e.kind === "tool_result") {
    const call = pendingCalls.shift() || {};
    return renderToolResult(e.tool, call.input || {}, e.output);
  }
  if (e.kind === "tool_call") { pendingCalls.push(e); return null; }
  if (e.kind === "ask_person") {
    const forLine = e.order_line != null ? ` into line ${esc(e.order_line)}${e.eat_in_days != null ? ` (eaten in ${esc(e.eat_in_days)} d)` : ""}` : "";
    if (e.batch) {  // one review of several items: one card, one row (and one answer) per item
      let card = document.querySelector(`#feed li[data-batch="${e.batch}"]`);
      if (!card) {
        card = li("ask", `<div class="head">Asks a person about ${esc(e.batch_size)} items in one review: ${esc(e.request_kind)}${forLine}</div>${esc(e.question)}<div class="batch-items"></div>`);
        card.dataset.batch = e.batch;
      }
      const row = document.createElement("div");
      row.className = "batch-item";
      const t = items[e.item_id]?.thumb;
      row.innerHTML = `${t ? `<img src="${photo(t, 72)}" alt="${esc(e.item_id)}">` : ""}<b>${esc(e.item_id)}</b> <span class="small muted">${esc(e.request)}</span><div class="answer" data-request="${esc(e.request)}"></div>`;
      card.querySelector(".batch-items").appendChild(row);
      return card;
    }
    return li("ask", `<div class="head">Asks a person (${esc(e.request)}): ${esc(e.request_kind)} ${esc(e.item_id)}${forLine}</div>${esc(e.question)}<div class="answer" data-request="${esc(e.request)}"></div>`);
  }
  if (e.kind === "answer") return li("action", `<div class="head">${esc(e.by)} ${e.approved ? "approved" : "declined"} ${esc(e.request)}</div><div class="small">${esc(e.answer)}</div>`);
  if (e.kind === "no_answer") return li("refused", `No answer to ${esc(e.request)} in time; it stays pending.`);
  if (e.kind === "error") return li("refused", `Run failed: ${esc(e.error)}`);
  return null;
}
const pendingCalls = [];

function renderWaiting(waiting) {
  document.querySelectorAll(".answer[data-request]").forEach((box) => {
    const id = box.dataset.request;
    const w = waiting.find((x) => x.request_id === id);
    if (!w || answered.has(id)) { box.innerHTML = ""; return; }
    if (box.childElementCount) return;
    box.innerHTML = `<input aria-label="note" placeholder="optional note"><button class="yes">Approve</button><button class="no">Decline</button>`;
    const send = async (approved) => {
      answered.add(id);
      box.innerHTML = `<span class="small">sent…</span>`;
      await api(`/api/runs/${runId}/answer`, { method: "POST", body: JSON.stringify({ request_id: id, approved, answer: box.querySelector("input")?.value || "" }) });
    };
    box.querySelector(".yes").onclick = () => send(true);
    box.querySelector(".no").onclick = () => send(false);
  });
}

function renderResult(snap) {
  items = Object.fromEntries(snap.items.map((i) => [i.item_id, i]));
  const thumb = (id) => `<button class="thumb" data-item="${esc(id)}"><img src="${photo(items[id].thumb, 120)}" alt="${esc(id)}"><span>${esc(id)}</span></button>`;
  $("#lines").innerHTML = snap.order.map((l) => `<div class="line"><div class="head"><span>Line ${l.line}: ${l.quantity} × ${esc(l.produce)}</span>
    <span class="muted">${l.eat_in_days == null ? "no timing" : `in ${l.eat_in_days} d`}</span></div>
    <div class="small muted">${l.packed.length}/${l.quantity} packed${l.packed.length < l.quantity && snap.status !== "running" ? `, short by ${l.quantity - l.packed.length}` : ""}</div>
    <div class="thumbs">${l.packed.map(thumb).join("")}</div></div>`).join("") || `<p class="muted">No order read yet.</p>`;
  const bins = { "reject bin": [], "sell today": [], crate: [] };
  snap.items.forEach((i) => { if (bins[i.location]) bins[i.location].push(i.item_id); });
  $("#bins").innerHTML = Object.entries(bins).map(([k, ids]) => `<div class="line"><div class="head"><span>${k === "crate" ? "Left in the crate" : k[0].toUpperCase() + k.slice(1)}</span><span class="muted">${ids.length}</span></div>
    <div class="thumbs">${ids.map(thumb).join("")}</div></div>`).join("");
  if (snap.status !== "running" && snap.result) {
    const s = snap.result.score;
    $("#check").hidden = false;
    $("#check").innerHTML = `<b>Checked against the datasets' hidden labels</b> <span class="muted">(the agent never saw them)</span>
      <table><tr><td>Packed and right for the order</td><td>${s.packed_ok}</td></tr><tr><td>Packed but wrong</td><td>${s.packed_bad}</td></tr>
      <tr><td>Sound items thrown away</td><td>${s.wasted_sound_items}</td></tr><tr><td>Lines filled</td><td>${s.lines_filled}/${s.lines}</td></tr>
      <tr><td>Items inspected / photos used</td><td>${s.inspected} / ${s.views}</td></tr><tr><td>Questions to a person</td><td>${s.person_requests}</td></tr>
      <tr><td>Moves the cell refused</td><td>${s.refused_moves}</td></tr></table>`;
  }
}

async function poll() {
  if (!runId) return;
  const { ok, body } = await api(`/api/runs/${runId}?after=${cursor}`);
  if (!ok) return;
  live = body.status === "running";
  items = Object.fromEntries(body.items.map((i) => [i.item_id, i]));  // before the events: cards show item photos
  body.events.forEach(renderEvent);
  cursor = body.next;
  renderWaiting(body.waiting);
  renderResult(body);
  $("#status").textContent = body.status === "running" ? `running ${body.elapsed_s}s` : body.status;
  $("#status").className = `pill ${body.status}`;
  if (body.status !== "running") { clearInterval(timer); timer = null; $("#run").disabled = false; }
}

function watch(id) {
  runId = id; cursor = 0; pendingCalls.length = 0; answered.clear();
  window.chhaantRun = id;
  window.dispatchEvent(new CustomEvent("chhaant:watch", { detail: id })); // the 3D viewer follows the same run
  $("#feed").innerHTML = ""; $("#check").hidden = true;
  if (timer) clearInterval(timer);
  timer = setInterval(poll, 900);
  poll();
}

async function start() {
  $("#run").disabled = true;
  const reviewer = document.querySelector("input[name=reviewer]:checked").value;
  const { ok, status, body } = await api("/api/runs", { method: "POST", body: JSON.stringify({ order: $("#order").value, reviewer, seed: 3, faults: $("#faults").checked }) });
  if (ok) return watch(body.id);
  $("#run").disabled = false;
  $("#run-note").textContent = body.error || `could not start (${status})`;
  if (status === 409 && body.active) watch(body.active);
}

async function openEvidence(itemId) {
  if (!runId) return;
  const { ok, body } = await api(`/api/runs/${runId}/items/${itemId}`);
  if (!ok) return;
  const ins = body.inspection;
  const looks = (ins?.looks || []).concat(body.extra_looks || []);
  $("#ev-title").textContent = `Evidence for ${itemId} (${body.produce})`;
  $("#ev-body").innerHTML = `<div class="kv"><span>Now</span><span>${esc(body.location)}</span>
      <span>Verdict</span><span>${ins ? `<span class="pill ${esc(ins.verdict)}">${esc(ins.verdict)}</span> ${esc(ins.reason)}` : "not inspected"}</span>
      <span>Measured</span><span>${ins ? esc(ins.capability) : ""}</span>
      <span>Shelf life</span><span>${ins ? esc(fmtForecast(ins.forecast)) : ""} at ${body.storage_temp_c} °C</span></div>
    <h3>Every photo it used</h3><div class="views">${looks.map((l) => `<div class="view"><img src="${photo(l.photo, 152)}" alt="">${angle(l)}${l.defect != null ? `<br>defect ${l.defect}` : ""}${l.ripeness != null ? `<br>ripe ${l.ripeness}` : ""}${unusable(l)}${l.why ? `<br><i>${esc(l.why)}</i>` : ""}</div>`).join("")}</div>
    <h3>Questions to a person</h3>${body.requests.map((r) => `<div class="small">${esc(r.id)} ${esc(r.kind)}: ${esc(r.question)} → <b>${esc(r.status)}</b> ${esc(r.answer)} ${r.by ? `(${esc(r.by)})` : ""}</div>`).join("") || `<div class="small muted">none</div>`}
    <h3>Moves</h3>${body.actions.map((a) => `<div class="small">${a.kind === "guardrail" ? `refused: ${esc(a.refused)}` : `${esc(a.destination)}${a.order_line ? ` line ${a.order_line}` : ""}: ${esc(a.reason)}`}</div>`).join("") || `<div class="small muted">none</div>`}`;
  $("#evidence").showModal();
}

document.addEventListener("click", (e) => {
  const target = e.target.closest("[data-item]");
  if (target && target.tagName !== "DIV") openEvidence(target.dataset.item);
});
$("#run").addEventListener("click", start);

(async function init() {
  const health = await api("/api/health");
  $("#backend").textContent = health.ok ? health.body.backend || "ready" : "offline";
  loadCrate();
  const active = await api("/api/runs/active");
  if (active.body.id) return watch(active.body.id);
  const latest = await api("/api/runs/latest");
  if (latest.body.id) watch(latest.body.id);
})();
