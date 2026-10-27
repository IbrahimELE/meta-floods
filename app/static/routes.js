/* Roads: mark responder-confirmed blockages and suggest a route that avoids them.
   The road graph comes from OpenStreetMap (Overpass API) and is built in the browser.
   Only blockages a responder confirmed change the route (PLAN 5.3); AI "impassable"
   findings are shown as warnings next to the route but never close a road. */
(() => {
  "use strict";
  const OVERPASS = "https://overpass-api.de/api/interpreter";
  const HIGHWAYS = "motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|road|track|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link";

  const R = 6371000;
  const rad = (d) => (d * Math.PI) / 180;
  function dist(a, b) {
    const h = Math.sin(rad(b[0] - a[0]) / 2) ** 2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(rad(b[1] - a[1]) / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  // ---------------------------------------------------------------- graph
  const cache = new Map();
  async function fetchRoads(bbox) {           // bbox = [south, west, north, east]
    const key = bbox.map((v) => v.toFixed(3)).join(",");
    if (cache.has(key)) return cache.get(key);
    const q = `[out:json][timeout:25];way["highway"~"^(${HIGHWAYS})$"](${bbox.join(",")});out geom;`;
    const res = await fetch(OVERPASS, { method: "POST", body: "data=" + encodeURIComponent(q) });
    if (!res.ok) throw new Error(`OpenStreetMap road data unavailable (${res.status})`);
    const data = await res.json();
    cache.set(key, data);
    return data;
  }

  function buildGraph(osm) {
    const nodes = new Map();                  // id -> [lat, lon]
    const adj = new Map();                    // id -> [{to, w, way, a, b}]
    const segments = [];                      // for snapping: {way, a, b, A, B}
    const add = (u, v, w, way) => { if (!adj.has(u)) adj.set(u, []); adj.get(u).push({ to: v, w, way }); };
    for (const el of osm.elements || []) {
      if (el.type !== "way" || !el.geometry || !el.nodes) continue;
      const oneway = el.tags && (el.tags.oneway === "yes" || el.tags.highway === "motorway" || el.tags.junction === "roundabout");
      const reverse = el.tags && el.tags.oneway === "-1";
      for (let i = 0; i < el.nodes.length; i++) nodes.set(el.nodes[i], [el.geometry[i].lat, el.geometry[i].lon]);
      for (let i = 0; i + 1 < el.nodes.length; i++) {
        const a = el.nodes[i], b = el.nodes[i + 1];
        const w = dist(nodes.get(a), nodes.get(b));
        if (!reverse) add(a, b, w, el.id);
        if (!oneway || reverse) add(b, a, w, el.id);
        segments.push({ way: el.id, a, b, A: nodes.get(a), B: nodes.get(b), name: el.tags && (el.tags.name || el.tags.ref) });
      }
    }
    return { nodes, adj, segments };
  }

  // nearest point on segment AB to P (equirectangular, fine at city scale)
  function project(P, A, B) {
    const k = Math.cos(rad(P[0]));
    const ax = A[1] * k, ay = A[0], bx = B[1] * k, by = B[0], px = P[1] * k, py = P[0];
    const dx = bx - ax, dy = by - ay;
    const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy || 1)));
    const Q = [ay + t * dy, (ax + t * dx) / k];
    return { Q, t, d: dist(P, Q) };
  }

  function nearestSegment(g, P) {
    let best = null;
    for (const s of g.segments) {
      const p = project(P, s.A, s.B);
      if (!best || p.d < best.d) best = { ...s, ...p };
    }
    return best;
  }

  function nearestNode(g, P) {
    let best = null, bd = Infinity;
    for (const [id, ll] of g.nodes) {
      if (!g.adj.has(id)) continue;
      const d = dist(P, ll);
      if (d < bd) { bd = d; best = id; }
    }
    return { id: best, d: bd };
  }

  function dijkstra(g, src, dst, blocked) {
    // blocked: Set of "a>b" directed edge keys
    const D = new Map([[src, 0]]), prev = new Map(), heap = [[0, src]];
    const push = (x) => { heap.push(x); let i = heap.length - 1; while (i > 0) { const p = (i - 1) >> 1; if (heap[p][0] <= heap[i][0]) break; [heap[p], heap[i]] = [heap[i], heap[p]]; i = p; } };
    const pop = () => { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i; if (l < heap.length && heap[l][0] < heap[m][0]) m = l; if (r < heap.length && heap[r][0] < heap[m][0]) m = r; if (m === i) break; [heap[m], heap[i]] = [heap[i], heap[m]]; i = m; } } return top; };
    while (heap.length) {
      const [d, u] = pop();
      if (u === dst) break;
      if (d > (D.get(u) ?? Infinity)) continue;
      for (const e of g.adj.get(u) || []) {
        if (blocked.has(`${u}>${e.to}`)) continue;
        const nd = d + e.w;
        if (nd < (D.get(e.to) ?? Infinity)) { D.set(e.to, nd); prev.set(e.to, u); push([nd, e.to]); }
      }
    }
    if (!D.has(dst)) return null;
    const path = [dst];
    while (path[path.length - 1] !== src) path.push(prev.get(path[path.length - 1]));
    path.reverse();
    return { length: D.get(dst), coords: path.map((id) => g.nodes.get(id)) };
  }

  function blockedKeys(blockages) {
    const keys = new Set();
    for (const b of blockages) {
      if (b.a_node == null || b.b_node == null) continue;
      if (b.direction !== "b_to_a") keys.add(`${b.a_node}>${b.b_node}`);
      if (b.direction !== "a_to_b") keys.add(`${b.b_node}>${b.a_node}`);
    }
    return keys;
  }

  function bboxAround(points, marginDeg = 0.02) {
    const lats = points.map((p) => p[0]), lons = points.map((p) => p[1]);
    return [Math.min(...lats) - marginDeg, Math.min(...lons) - marginDeg, Math.max(...lats) + marginDeg, Math.max(...lons) + marginDeg];
  }

  window.FHRoutes = { fetchRoads, buildGraph, nearestSegment, nearestNode, dijkstra, blockedKeys, bboxAround, dist };
})();
