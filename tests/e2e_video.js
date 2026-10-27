// Drone clip end to end (real SAM 3.1 + Muse Spark): sandbox → upload a clip through "Add photos / drone clip"
// → tracking counts appear → keyframes appear as photos → overlay video plays.
// usage: node tests/e2e_video.js <dir with leaf/ (leaflet npm package)> <base url> <clip.mp4>
const { chromium } = require('playwright');
const [S, BASE, CLIP] = process.argv.slice(2);

(async () => {
  const b = await chromium.launch();
  const p = await (await b.newContext({ viewport: { width: 1440, height: 1000 } })).newPage();
  const errors = [];
  p.on('pageerror', (e) => errors.push(e.message));
  await p.route('**/*', (r) => {
    const u = r.request().url();
    if (u.includes('leaflet.min.js')) return r.fulfill({ path: S + '/leaf/package/dist/leaflet.js', contentType: 'text/javascript' });
    if (u.includes('leaflet.min.css')) return r.fulfill({ path: S + '/leaf/package/dist/leaflet.css', contentType: 'text/css' });
    return u.startsWith(BASE) ? r.continue() : r.abort();
  });
  const sb = await (await p.request.post(BASE + '/api/sandbox', { data: { name: 'Drone test', region: 'test' } })).json();
  await p.goto(`${BASE}/?incident=${sb.id}`, { waitUntil: 'networkidle' });
  const t0 = Date.now();
  await p.setInputFiles('#file-input', CLIP);
  await p.waitForSelector('.clip-counts', { timeout: 120000 });
  const tracked = (Date.now() - t0) / 1000;
  const counts = await p.locator('.clip-counts').innerText();
  await p.waitForSelector('.clip.done video', { timeout: 600000 });
  const rendered = (Date.now() - t0) / 1000;
  const keyframes = await p.locator('.clip [data-open]').count();
  const ready = await p.evaluate(async () => {
    const v = document.querySelector('.clip.done video');
    for (let i = 0; i < 50 && v.readyState < 2; i++) await new Promise((r) => setTimeout(r, 100));
    return v.readyState;
  });
  await p.screenshot({ path: S + '/e2e_video.png' });
  console.log(JSON.stringify({ tracked_after_s: tracked, overlay_after_s: rendered, counts, keyframes, ready, errors }, null, 1));
  const ok = /house/.test(counts) && keyframes > 0 && ready >= 2 && !errors.length;
  console.log(ok ? 'PASS drone clip' : 'FAIL drone clip');
  await b.close();
  process.exit(ok ? 0 : 1);
})();
