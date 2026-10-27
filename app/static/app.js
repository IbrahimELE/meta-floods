/* FirstHour frontend – vanilla JS + Leaflet. Talks to app/server.py. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const state = {
    incident: null,          // incident meta from snapshot
    images: new Map(),       // id -> image
    selected: null,          // image id shown in detail
    pinTarget: null,         // image id waiting for a map click
    fitted: false,
    events: null,
    refreshTimer: null,
  };

  // ------------------------------------------------------------------ map
  const map = L.map("map", { zoomControl: true }).setView([43.86, 18.41], 7); // Sarajevo until data arrives
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  const zoneLayer = L.layerGroup().addTo(map);
  const layer = L.layerGroup().addTo(map);
  map.on("movestart", () => { if (!state.programmaticMove) state.userMoved = true; });
  const PRIO_COLOR = { 5: "#c8102e", 4: "#e8590c", 3: "#e0a800", 2: "#2b8a3e", 1: "#7b8a97" };

  const prioClass = (img) => (img.priority ? `p${img.priority}` : "unassessed");

  function marker(img) {
    const loc = img.location;
    const cls = [prioClass(img), loc.kind === "ai_scene_estimate" ? "proposed" : "", state.selected === img.id ? "selected" : ""].join(" ");
    const icon = L.divIcon({
      className: "",
      html: `<div class="fh-marker ${cls}">${img.priority ?? "?"}</div>`,
      iconSize: [30, 30],
      iconAnchor: [0, 30],
    });
    const m = L.marker([loc.lat, loc.lon], { icon, keyboard: true, title: img.original_name });
    m.on("click", () => openDetail(img.id));
    return m;
  }

  function renderMap() {
    layer.clearLayers();
    zoneLayer.clearLayers();
    for (const z of state.zones || []) {
      if (!z.center) continue;
      const color = z.priority ? PRIO_COLOR[z.priority] : "#6741d9";
      L.circle(z.center, { radius: Math.max(z.radius_m, 200), color, weight: 2, fillColor: color, fillOpacity: 0.08, interactive: false }).addTo(zoneLayer);
      // zone circle only; zone names are in the panel
    }
    const pts = [];
    for (const img of state.images.values()) {
      if (!img.published || !img.location) continue;
      const loc = img.location;
      L.circle([loc.lat, loc.lon], {
        radius: loc.uncertainty_m || 300,
        color: "#4b5966", weight: 1.5, dashArray: "5 5", fillOpacity: 0.05,
        interactive: false,
      }).addTo(layer);
      marker(img).addTo(layer);
      pts.push([loc.lat, loc.lon]);
    }
    if (pts.length && !state.userMoved && pts.length !== state.fittedCount) {
      state.programmaticMove = true;
      map.fitBounds(pts, { padding: [60, 60], maxZoom: 14 });
      state.fittedCount = pts.length;
      setTimeout(() => { state.programmaticMove = false; }, 600);
    }
  }

  // ------------------------------------------------------------------ list + counts
  function renderList() {
    const imgs = [...state.images.values()];
    const onMap = imgs.filter((i) => i.published);
    const ranked = onMap.filter((i) => i.priority).sort((a, b) => b.priority - a.priority || (b.points ?? 0) - (a.points ?? 0));
    const unassessed = onMap.filter((i) => !i.priority);
    const working = imgs.filter((i) => i.processing_state === "queued" || i.processing_state === "running");
    const failed = imgs.filter((i) => i.processing_state === "failed");
    const needPin = imgs.filter((i) => i.location_state === "needs_pin");

    $("counts").innerHTML =
      `<span><b>${working.length}</b>being assessed</span>` +
      `<span><b>${onMap.length}</b>on the map</span>` +
      `<span><b>${needPin.length}</b>need a location</span>` +
      (failed.length ? `<span><b>${failed.length}</b>failed</span>` : "");

    $("empty-state").hidden = imgs.length > 0;

    $("check-list").innerHTML = unassessed.length
      ? `<div class="check-box"><h3>Check these first – could not be assessed</h3>
         <p class="small muted">Not low priority: the photos did not show enough to judge. Look at them yourself.</p>
         <ol class="rank">${unassessed.map(row).join("")}</ol></div>`
      : "";

    const rows = [
      ...working.map((i) => `<li tabindex="0" data-id="${i.id}"><span class="prio p1">…</span>${thumb(i)}
        <div><div class="title">${esc(i.original_name)}</div><div class="state">${i.processing_state === "running" ? `assessing (${esc(i.stage)})` : "waiting"}</div></div></li>`),
      ...ranked.map(row),
      ...failed.map((i) => `<li tabindex="0" data-id="${i.id}"><span class="prio p1">!</span>${thumb(i)}
        <div><div class="title">${esc(i.original_name)}</div><div class="why">Failed: ${esc(i.last_error)}</div></div></li>`),
    ];
    $("rank").innerHTML = rows.join("");
    for (const li of document.querySelectorAll(".rank li")) {
      li.onclick = () => openDetail(li.dataset.id);
      li.onkeydown = (e) => { if (e.key === "Enter") openDetail(li.dataset.id); };
    }
  }

  const thumb = (i) => `<img src="/api/images/${i.id}/photo" alt="" loading="lazy">`;

  function row(i) {
    const s = i.summary || {};
    const d = s.damage || {};
    const why = [
      d.destroyed ? `${d.destroyed} destroyed` : "",
      d.major ? `${d.major} major damage` : "",
      s.roads_blocked ? `${s.roads_blocked} road blocked` : "",
      s.roads_caution ? `${s.roads_caution} road caution` : "",
      i.scene?.water_depth && !["none", "unknown"].includes(i.scene.water_depth) ? `water ${i.scene.water_depth.replace("_", " ")}` : "",
    ].filter(Boolean).join(", ") || i.scene?.summary?.slice(0, 80) || "";
    const loc = i.location?.kind === "human_pin" ? "pinned" : i.location?.kind === "camera_exif" ? "camera GPS" : "AI guess";
    return `<li tabindex="0" data-id="${i.id}"><span class="prio ${prioClass(i)}">${i.priority ?? "?"}</span>${thumb(i)}
      <div><div class="title">${esc(i.original_name)}</div><div class="why">${esc(why)}</div>
      <div class="why">${loc}${i.age !== "fresh" ? ` · photo age ${i.age}` : ""}</div></div></li>`;
  }

  // ------------------------------------------------------------------ tray (needs a location)
  function renderTray() {
    const need = [...state.images.values()].filter((i) => i.location_state === "needs_pin");
    $("tray").hidden = need.length === 0;
    $("tray-count").textContent = need.length ? `(${need.length}) – pick a photo, then click the map` : "";
    $("tray-items").innerHTML = need.map((i) => `
      <button type="button" class="tray-item ${state.pinTarget === i.id ? "active" : ""}" data-id="${i.id}">
        ${thumb(i)}<div>${esc(i.original_name)}</div>
        <div class="st">${i.processing_state === "done" ? "assessed, waiting for location" : i.processing_state}</div>
      </button>`).join("");
    for (const b of document.querySelectorAll(".tray-item")) b.onclick = () => startPin(b.dataset.id);
  }

  function startPin(id) {
    state.pinTarget = id;
    const img = state.images.get(id);
    $("pin-hint-text").textContent = `Click the map where “${img.original_name}” was taken`;
    $("pin-hint").hidden = false;
    $("drop-zone").classList.add("pinning");
    renderTray();
  }
  function stopPin() {
    state.pinTarget = null;
    $("pin-hint").hidden = true;
    $("drop-zone").classList.remove("pinning");
    renderTray();
  }
  $("pin-cancel").onclick = stopPin;
  map.on("click", async (e) => {
    if (!state.pinTarget) return;
    const id = state.pinTarget;
    stopPin();
    await api(`/api/images/${id}/pin`, { method: "POST", body: JSON.stringify({ lat: e.latlng.lat, lon: e.latlng.lng }) });
    refresh();
  });

  // ------------------------------------------------------------------ detail panel
  async function openDetail(id) {
    state.selected = id;
    const d = await api(`/api/images/${id}`);
    if (!d) return;
    $("list-view").hidden = true;
    const v = $("detail-view");
    v.hidden = false;
    const loc = d.location;
    const locText = !loc ? "unknown – place it on the map"
      : loc.kind === "human_pin" ? `pinned by a responder (±${loc.uncertainty_m} m)`
      : loc.kind === "camera_exif" ? `camera GPS (±${loc.uncertainty_m} m – objects can be further away)`
      : `AI suggestion (±${loc.uncertainty_m} m) – verify`;
    const sc = d.scene || {};
    const scene = d.findings?.find((f) => !f.object_id);
    const hazards = scene ? JSON.parse(scene.hazards_json || "[]") : [];
    const people = !scene ? "–" : scene.people_may_need_help === 1 ? "may need help" : scene.people_visible === 1 ? "visible" : scene.people_visible === 0 ? "none visible (not proof that none are there)" : "cannot tell from this photo";

    v.innerHTML = `
      <button class="back" id="back" type="button">‹ All findings</button>
      <h2>${esc(d.original_name)}</h2>
      <div class="toggle" role="group" aria-label="Photo view">
        <button type="button" data-view="overlay" aria-pressed="true">With SAM masks</button>
        <button type="button" data-view="photo" aria-pressed="false">Original</button>
      </div>
      <div class="photo-box"><img id="detail-img" src="/api/images/${d.id}/${d.segmentation_state === "pending" ? "photo" : "overlay"}" alt="Photo ${esc(d.original_name)}"></div>
      ${d.processing_state !== "done" ? `<p class="ai-note">Status: ${esc(d.processing_state)} ${esc(d.stage || "")} ${esc(d.last_error || "")}</p>` : ""}
      <div class="score">
        <span class="big">${d.priority ?? "not assessed"}</span>${d.priority ? "priority (1–5)" : ""}
        <ul>${(d.points_parts || []).map((p) => `<li>${esc(p)}</li>`).join("")}</ul>
      </div>
      <dl class="facts">
        <dt>Location</dt><dd>${esc(locText)}</dd>
        <dt>Photo taken</dt><dd>${d.captured_at ? esc(d.captured_at.replace("T", " ")) : "unknown"} (${esc(d.age)})</dd>
        <dt>Scene</dt><dd>${esc(sc.summary || "–")}</dd>
        <dt>Water</dt><dd>${esc(sc.water_depth || "–")}</dd>
        <dt>People</dt><dd>${esc(people)}</dd>
        <dt>Hazards</dt><dd>${hazards.length ? hazards.map((h) => `<b>${esc(h.type.replaceAll("_", " "))}</b>: ${esc(h.description)}`).join("<br>") : "none reported"}</dd>
      </dl>
      ${d.location_state === "needs_pin" ? `<button class="upload-btn" id="pin-this" type="button">Place on map</button>` : ""}
      <p class="ai-note">AI estimate by Meta SAM 3.1 + Muse Spark – verify on site. Confirm or reject each object; rejected findings stop counting.</p>
      <h3>Objects (${d.findings ? d.findings.filter((f) => f.object_id).length : 0})</h3>
      <ul class="findings">${(d.findings || []).filter((f) => f.object_id).map(findingRow).join("")}</ul>`;

    $("back").onclick = closeDetail;
    if ($("pin-this")) $("pin-this").onclick = () => startPin(d.id);
    for (const b of v.querySelectorAll(".toggle button")) {
      b.onclick = () => {
        $("detail-img").src = `/api/images/${d.id}/${b.dataset.view}`;
        for (const x of v.querySelectorAll(".toggle button")) x.setAttribute("aria-pressed", String(x === b));
      };
    }
    for (const b of v.querySelectorAll(".review button")) {
      b.onclick = async () => {
        await api(`/api/findings/${b.dataset.finding}/review`, { method: "POST", body: JSON.stringify({ action: b.dataset.action }) });
        openDetail(d.id);
        refresh();
      };
    }
    renderMap();
  }

  function findingRow(f) {
    const pass = f.passability && f.passability !== "not_applicable" ? `<span class="chip ${f.passability}">${f.passability}</span>` : "";
    const flood = f.flood_overlap ? ` · ${Math.round(f.flood_overlap * 100)}% under flood water (SAM)` : "";
    return `<li class="${f.rejected ? "rejected" : ""}">
      <span class="n">#${f.n}</span>
      <div><span class="lbl">${esc(f.concept)}</span> <span class="chip ${f.damage}">${esc((f.damage || "").replace("_", " "))}</span>${pass}
        <div class="small">${esc(f.evidence_text)}${flood}</div>
        <div class="small muted">model self-estimate ${f.self_confidence != null ? f.self_confidence.toFixed(2) : "–"}</div></div>
      <div class="review">
        <button type="button" data-finding="${f.id}" data-action="confirm" aria-pressed="${f.confirmed}" title="Confirm">Confirm</button>
        <button type="button" data-finding="${f.id}" data-action="reject" aria-pressed="${f.rejected}" title="Reject">Reject</button>
      </div></li>`;
  }

  function closeDetail() {
    state.selected = null;
    $("detail-view").hidden = true;
    $("list-view").hidden = false;
    renderMap();
  }

  // ------------------------------------------------------------------ coordinator (agent)
  function renderZones() {
    const zones = state.zones || [];
    if (!zones.length) { $("zones").innerHTML = ""; return; }
    $("zones").innerHTML = `<h3>Zones</h3>` + zones.map((z) => {
      const imgs = z.image_ids.map((id) => state.images.get(id)).filter(Boolean);
      const dmg = imgs.reduce((n, i) => n + (i.summary?.damage?.destroyed || 0) + (i.summary?.damage?.major || 0), 0);
      const delta = z.agent_delta ? `<div class="agent-delta">Coordinator ${z.agent_delta > 0 ? "raised" : "lowered"} by 1: ${esc(z.agent_reason)}</div>`
        : z.agent_delta_status ? `<div class="agent-delta expired">Coordinator correction ${esc(z.agent_delta_status)}</div>` : "";
      const opts = ["", 5, 4, 3, 2, 1].map((p) => `<option value="${p}" ${z.human_priority === p || (p === "" && !z.human_priority) ? "selected" : ""}>${p === "" ? "automatic" : "set " + p}</option>`).join("");
      return `<div class="zone ${z.status === "unassessed" ? "zone-unassessed" : ""}">
        <span class="prio ${z.priority ? "p" + z.priority : "unassessed"}" style="width:30px;height:30px;border-radius:6px 6px 6px 0;display:grid;place-items:center;color:#fff;font:700 17px var(--font-ui)">${z.priority ?? "?"}</span>
        <div><div class="title">${esc(z.label)}</div>
          <div class="why">${imgs.length} photo${imgs.length === 1 ? "" : "s"}, ${dmg} buildings with major damage or destroyed${z.confirmed_blockage ? ", confirmed road blockage" : ""}</div>
          <div class="why">from findings: ${z.base_priority ?? "not assessed"}${z.human_priority ? ` · set by you: ${z.human_priority} (locked)` : ""}</div>${delta}</div>
        <label class="small"><span class="muted">Priority</span><br><select data-zone="${z.id}" aria-label="Set priority for ${esc(z.label)}">${opts}</select></label>
      </div>`;
    }).join("");
    for (const sel of document.querySelectorAll("select[data-zone]")) {
      sel.onchange = async () => {
        await api(`/api/zones/${sel.dataset.zone}/priority`, { method: "POST", body: JSON.stringify({ priority: sel.value ? Number(sel.value) : null }) });
        refresh();
      };
    }
  }

  function mdLite(text) {
    const out = [];
    let list = false;
    for (const line of text.split("\n")) {
      if (line.startsWith("- ")) { if (!list) { out.push("<ul>"); list = true; } out.push(`<li>${esc(line.slice(2))}</li>`); continue; }
      if (list) { out.push("</ul>"); list = false; }
      if (line.startsWith("## ")) out.push(`<h4>${esc(line.slice(3))}</h4>`);
      else if (line.trim()) out.push(`<p>${esc(line)}</p>`);
    }
    if (list) out.push("</ul>");
    return out.join("");
  }

  let agentBusy = false;
  async function loadAgent() {
    if (!state.incident) return;
    const a = await api(`/api/incidents/${state.incident.id}/agent`);
    if (!a) return;
    agentBusy = a.run?.status === "running";
    $("run-agent").disabled = agentBusy;
    $("run-agent").textContent = agentBusy ? "Working…" : a.run ? "Analyse again" : "Analyse situation";
    if (a.run) {
      const st = { running: "is working", done: "finished", incomplete: "stopped at its step limit – partial result", failed: "failed: " + (a.run.error || "") }[a.run.status];
      $("agent-status").textContent = `Coordinator ${st} · ${a.run.steps} steps · ${a.run.started_at.replace("T", " ").slice(0, 16)} UTC`;
    }
    $("review-requests").innerHTML = a.review_requests.length ? `<h3>Please check (${a.review_requests.length})</h3>` +
      a.review_requests.map((r) => {
        const ids = JSON.parse(r.target_ids_json);
        const links = r.target_type === "image" ? ids.map((id) => `<a data-open="${id}">${esc(state.images.get(id)?.original_name || id)}</a>`).join(", ") : `${r.target_type} ${ids.join(", ")}`;
        return `<div class="req">${esc(r.question)}<div class="small">${links}</div><button class="ghost resolve-btn" type="button" data-resolve="${r.id}">Done</button></div>`;
      }).join("") : "";
    for (const el of document.querySelectorAll("[data-open]")) el.onclick = () => openDetail(el.dataset.open);
    for (const el of document.querySelectorAll("[data-resolve]")) el.onclick = async () => { await api(`/api/review-requests/${el.dataset.resolve}/resolve`, { method: "POST" }); loadAgent(); };

    const lang = state.briefLang || "en";
    const b = a.briefings.find((x) => x.language === lang) || a.briefings[0];
    $("briefing").innerHTML = b ? `<div class="briefing">
        <div class="toggle" role="group" aria-label="Briefing language">${a.briefings.map((x) => `<button type="button" data-lang="${x.language}" aria-pressed="${x.language === b.language}">${x.language === "bs" ? "Bosanski" : "English"}</button>`).join("")}</div>
        <h3>${esc(b.headline)}</h3>${b.stale ? `<div class="stale">The situation changed since this briefing – run the coordinator again.</div>` : ""}
        <div class="brief-body">${mdLite(b.body)}</div></div>` : "";
    for (const el of document.querySelectorAll("[data-lang]")) el.onclick = () => { state.briefLang = el.dataset.lang; loadAgent(); };

    $("agent-log-wrap").hidden = !a.actions.length;
    $("agent-log").innerHTML = a.actions.map((x) => {
      const args = JSON.parse(x.args_json || "{}");
      const what = { get_situation: "Read the situation", cluster_zones: `Grouped photos into zones (${args.radius_m} m)`,
        adjust_zone_priority: `Zone ${args.zone_id}: priority ${args.delta > 0 ? "+" : ""}${args.delta} – ${args.reason || ""}`,
        request_human_review: `Asked you to check: ${args.question || ""}`, flag_possible_duplicate: `Possible duplicate photos: ${args.reason || ""}`,
        write_briefing: `Wrote the ${args.language === "bs" ? "Bosnian" : "English"} briefing` }[x.tool] || x.tool;
      return `<li class="${x.result.startsWith("rejected") ? "rejected" : ""}">${esc(what)}${x.result.startsWith("rejected") ? ` – <b>refused by the server</b>: ${esc(x.result.slice(10))}` : ""}</li>`;
    }).join("");
  }

  $("run-agent").onclick = async () => {
    if (!state.incident || agentBusy) return;
    $("run-agent").disabled = true;
    const r = await api(`/api/incidents/${state.incident.id}/agent/run`, { method: "POST" });
    if (r) { agentBusy = true; $("run-agent").textContent = "Working…"; }
    else $("run-agent").disabled = false;
  };

  // ------------------------------------------------------------------ data
  async function api(url, opts = {}) {
    const res = await fetch(url, { headers: opts.body instanceof FormData ? {} : { "content-type": "application/json" }, credentials: "same-origin", ...opts });
    if (!res.ok) {
      const msg = (await res.json().catch(() => ({}))).detail || res.statusText;
      banner(`${msg}`, "error");
      return null;
    }
    return res.json();
  }

  async function refresh() {
    if (!state.incident) return;
    const snap = await api(`/api/incidents/${state.incident.id}/snapshot`);
    if (!snap) return;
    state.incident = snap.incident;
    state.images = new Map(snap.images.map((i) => [i.id, i]));
    state.zones = snap.zones || [];
    renderMap();
    renderZones();
    loadAgent();
    renderList();
    renderTray();
    if (state.selected && !$("detail-view").hidden) openDetail(state.selected);
  }
  const refreshSoon = () => { clearTimeout(state.refreshTimer); state.refreshTimer = setTimeout(refresh, 400); };

  function listen(after) {
    if (state.events) state.events.close();
    const es = new EventSource(`/api/incidents/${state.incident.id}/events?after=${after}`);
    for (const t of ["image_added", "image_updated", "finding_published", "finding_reviewed", "zones_updated",
      "agent_started", "agent_action", "agent_finished", "briefing_written", "review_requested", "review_resolved"]) es.addEventListener(t, refreshSoon);
    state.events = es; // EventSource reconnects by itself and sends Last-Event-ID
  }

  let bannerTimer = null;
  function banner(text, kind = "") {
    const b = $("banner");
    b.className = `banner ${kind}`;
    b.textContent = text;
    b.hidden = !text;
    clearTimeout(bannerTimer);
    if (text && !kind) bannerTimer = setTimeout(() => { if (b.textContent === text) b.hidden = true; }, 10000);
  }

  async function selectIncident(id) {
    const snap = await api(`/api/incidents/${id}/snapshot`);
    if (!snap) return;
    state.incident = snap.incident;
    state.userMoved = false;
    state.fittedCount = 0;
    document.body.classList.toggle("readonly", snap.incident.mode === "demo_readonly");
    closeDetail();
    history.replaceState(null, "", `?incident=${id}`);
    if (snap.incident.as_of) banner(`Historical scenario – situation as of ${snap.incident.as_of.replace("T", " ")}. Photo ages are measured from that time.`, "historic");
    else if (snap.incident.mode === "demo_readonly") banner("Read-only demo. Start a new incident to try your own photos.");
    else banner("");
    await refresh();
    listen(0);
  }

  async function loadIncidents(preferred) {
    const list = (await api("/api/incidents")) || [];
    const sel = $("incident-select");
    sel.innerHTML = list.map((i) => `<option value="${i.id}">${esc(i.name)}${i.mode === "demo_readonly" ? " (demo)" : ""}</option>`).join("");
    if (preferred && !list.some((i) => i.id === preferred)) sel.insertAdjacentHTML("afterbegin", `<option value="${preferred}">My sandbox</option>`);
    const id = preferred || list[0]?.id;
    if (id) { sel.value = id; selectIncident(id); }
  }
  $("incident-select").onchange = (e) => selectIncident(e.target.value);

  $("new-incident").onclick = async () => {
    const name = prompt("Name of the incident (e.g. “Jablanica floods”)");
    if (!name) return;
    const region = prompt("Affected region (optional, e.g. “Jablanica, Bosnia and Herzegovina”)") || null;
    let res = await fetch("/api/incidents", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name, region }) });
    if (res.status === 403) res = await fetch("/api/sandbox", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name, region }) });
    if (!res.ok) return banner("Could not create the incident.", "error");
    loadIncidents((await res.json()).id);
  };

  // ------------------------------------------------------------------ upload
  async function upload(files) {
    if (!state.incident) return banner("Create an incident first.");
    if (state.incident.mode === "demo_readonly") return banner("This demo is read-only. Click “New incident” to analyse your own photos.");
    const list = [...files].filter((f) => /^image\//.test(f.type));
    if (!list.length) return;
    banner(`Uploading ${list.length} photo${list.length > 1 ? "s" : ""}…`);
    const fd = new FormData();
    list.forEach((f) => fd.append("files", f));
    const res = await api(`/api/incidents/${state.incident.id}/images`, { method: "POST", body: fd });
    if (!res) return;
    const bad = res.results.filter((r) => r.status === "rejected");
    const dup = res.results.filter((r) => r.status === "duplicate").length;
    banner([`${res.results.length - bad.length - dup} added – assessment takes about a minute per photo.`,
      dup ? `${dup} already uploaded.` : "",
      bad.map((r) => `${r.name}: ${r.error}`).join(" ")].filter(Boolean).join(" "));
    refresh();
  }
  $("file-input").onchange = (e) => { upload(e.target.files); e.target.value = ""; };
  const dz = $("drop-zone");
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("dragging"); });
  dz.addEventListener("dragleave", (e) => { if (!dz.contains(e.relatedTarget)) dz.classList.remove("dragging"); });
  dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("dragging"); upload(e.dataTransfer.files); });

  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { if (state.pinTarget) stopPin(); else closeDetail(); } });

  loadIncidents(new URLSearchParams(location.search).get("incident"));
})();
