// Voice report end to end: sandbox → "Voice report" tool → click the map → upload audio
// (converted to 24 kHz mono WAV in the browser) → real Muse Voice Transcribe + extraction
// → report marker on the map and entry in the panel.
// usage: node tests/e2e_voice.js <dir with leaf/ (leaflet npm package)> <base url> <audio file>
const { chromium } = require('playwright');
const [S, BASE, AUDIO] = process.argv.slice(2);

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const errors = [];
  p.on('pageerror', (e) => errors.push(e.message));
  await p.route('**/*', (r) => {
    const u = r.request().url();
    if (u.includes('leaflet.min.js')) return r.fulfill({ path: S + '/leaf/package/dist/leaflet.js', contentType: 'text/javascript' });
    if (u.includes('leaflet.min.css')) return r.fulfill({ path: S + '/leaf/package/dist/leaflet.css', contentType: 'text/css' });
    return u.startsWith(BASE) ? r.continue() : r.abort();
  });
  const sb = await (await p.request.post(BASE + '/api/sandbox', { data: { name: 'Voice test', region: 'Doboj' } })).json();
  await p.goto(`${BASE}/?incident=${sb.id}`, { waitUntil: 'networkidle' });
  await p.click('#tool-voice');
  const box = await p.locator('#map').boundingBox();
  await p.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await p.waitForSelector('#rec-file', { state: 'attached' });
  const t0 = Date.now();
  await p.setInputFiles('#rec-file', AUDIO);
  await p.waitForSelector('.report.done, .report.failed', { timeout: 90000 });
  const text = await p.locator('#reports').innerText();
  const pins = await p.locator('.voice-pin').count();
  await p.screenshot({ path: S + '/e2e_voice.png' });
  console.log(JSON.stringify({ seconds: (Date.now() - t0) / 1000, pins, errors, text }, null, 1));
  const ok = /done/.test(await p.locator('.report').first().getAttribute('class')) && pins === 1 && !errors.length;
  console.log(ok ? 'PASS voice report' : 'FAIL voice report');
  await b.close();
  process.exit(ok ? 0 : 1);
})();
