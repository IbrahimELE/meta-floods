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
  const layer = L.layerGroup().addTo(map);

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
    if (pts.length && !state.fitted) {
      map.fitBounds(pts, { padding: [60, 60], maxZoom: 14 });
      state.fitted = true;
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
    renderMap();
    renderList();
    renderTray();
    if (state.selected && !$("detail-view").hidden) openDetail(state.selected);
  }
  const refreshSoon = () => { clearTimeout(state.refreshTimer); state.refreshTimer = setTimeout(refresh, 400); };

  function listen(after) {
    if (state.events) state.events.close();
    const es = new EventSource(`/api/incidents/${state.incident.id}/events?after=${after}`);
    for (const t of ["image_added", "image_updated", "finding_published", "finding_reviewed"]) es.addEventListener(t, refreshSoon);
    state.events = es; // EventSource reconnects by itself and sends Last-Event-ID
  }

  function banner(text, kind = "") {
    const b = $("banner");
    b.className = `banner ${kind}`;
    b.textContent = text;
    b.hidden = !text;
  }

  async function selectIncident(id) {
    const snap = await api(`/api/incidents/${id}/snapshot`);
    if (!snap) return;
    state.incident = snap.incident;
    state.fitted = false;
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
