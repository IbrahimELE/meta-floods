const { chromium } = require('playwright');
const S = process.argv[2], BASE = process.argv[3];
// synthetic OSM grid inside the requested bbox: 9x9 nodes, ways along rows and columns
function grid(q) {
  const m = q.match(/\(([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)\)/); const [s, w, n, e] = m.slice(1).map(Number);
  const N = 61, els = []; let wid = 1;
  const id = (i, j) => 1000 + i * N + j, ll = (i, j) => ({ lat: s + (n - s) * (i + .5) / N, lon: w + (e - w) * (j + .5) / N });
  for (let i = 0; i < N; i++) { const nodes = [], geom = []; for (let j = 0; j < N; j++) { nodes.push(id(i, j)); geom.push(ll(i, j)); } els.push({ type: 'way', id: wid++, nodes, geometry: geom, tags: { highway: 'residential', name: 'Row ' + i } }); }
  for (let j = 0; j < N; j++) { const nodes = [], geom = []; for (let i = 0; i < N; i++) { nodes.push(id(i, j)); geom.push(ll(i, j)); } els.push({ type: 'way', id: wid++, nodes, geometry: geom, tags: { highway: 'residential', name: 'Col ' + j } }); }
  return { elements: els };
}
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1400, height: 900 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  let overpassCalls = 0;
  await p.route('**/*', async r => {
    const u = r.request().url();
    if (u.includes('leaflet.min.js')) return r.fulfill({ path: S + '/leaf/package/dist/leaflet.js', contentType: 'text/javascript' });
    if (u.includes('leaflet.min.css')) return r.fulfill({ path: S + '/leaf/package/dist/leaflet.css', contentType: 'text/css' });
    if (u.includes('overpass-api.de')) { overpassCalls++; const body = decodeURIComponent((r.request().postData() || '').slice(5)); return r.fulfill({ contentType: 'application/json', body: JSON.stringify(grid(body)) }); }
    if (u.startsWith(BASE)) return r.continue(); return r.abort();
  });
  const inc = (await (await p.request.get(BASE + '/api/incidents')).json()).find(i => i.mode === 'dev');
  await p.goto(`${BASE}/?incident=${inc.id}`); await p.waitForTimeout(2000);
  await p.evaluate(() => { const m = document.querySelector('#map'); });
  const box = await p.locator('#map').boundingBox(); const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
  // zoom in strongly around centre so bbox is small
  for (let i = 0; i < 6; i++) { await p.mouse.move(cx, cy); await p.mouse.wheel(0, -500); await p.waitForTimeout(250); }
  await p.click('#tool-route'); await p.waitForTimeout(200);
  await p.mouse.click(cx - 150, cy - 100); await p.waitForTimeout(300);
  await p.mouse.click(cx + 150, cy + 100); await p.waitForTimeout(1500);
  const t1 = await p.locator('#route-box').innerText(); console.log('ROUTE1:', t1.split('\n')[0]);
  const km1 = parseFloat(t1.match(/([\d.]+) km/)?.[1] || 'NaN');
  await p.screenshot({ path: S + '/route1.png' });
  await p.click('#tool-block'); await p.waitForTimeout(200);
  // click on the route's middle: find route path midpoint in screen space
  const mid = await p.evaluate(() => { const ps = [...document.querySelectorAll('path.leaflet-interactive')].filter(x => x.getAttribute('stroke') === '#0b5cad'); return null; });
  await p.mouse.click(cx, cy); await p.waitForTimeout(1200);
  const t2 = await p.locator('#route-box').innerText(); console.log('BLOCK:', t2.split('\n')[0]);
  if (await p.locator('#block-ok').count()) { await p.click('#block-ok'); await p.waitForTimeout(1500); }
  const snap = await (await p.request.get(`${BASE}/api/incidents/${inc.id}/snapshot`)).json();
  console.log('blockages', snap.blockages.length);
  await p.click('#tool-route'); await p.waitForTimeout(200);
  await p.mouse.click(cx - 150, cy - 100); await p.waitForTimeout(300);
  await p.mouse.click(cx + 150, cy + 100); await p.waitForTimeout(1500);
  const t3 = await p.locator('#route-box').innerText(); console.log('ROUTE2:', t3.split('\n')[0], '|', t3.split('\n')[1]);
  await p.screenshot({ path: S + '/route2.png' });
  console.log('overpass calls', overpassCalls, 'errors', errs);
  await b.close();
})();
