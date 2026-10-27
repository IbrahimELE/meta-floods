// End-to-end UI test against a running server (real Meta API for new uploads/agent).
const { chromium } = require('playwright');
const S = process.argv[2], BASE = process.argv[3], DATA = process.argv[4];
const findings = [];
const log = (ok, what, extra = '') => { findings.push({ ok, what, extra }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${what}${extra ? '  – ' + extra : ''}`); };
const shot = (p, name) => p.screenshot({ path: `${S}/e2e_${name}.png` });

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  p.on('pageerror', e => errors.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error' && !/ERR_FAILED|tile|fonts/.test(m.text())) errors.push(m.text()); });
  await p.route('**/*', r => {
    const u = r.request().url();
    if (u.includes('leaflet.min.js')) return r.fulfill({ path: S + '/leaf/package/dist/leaflet.js', contentType: 'text/javascript' });
    if (u.includes('leaflet.min.css')) return r.fulfill({ path: S + '/leaf/package/dist/leaflet.css', contentType: 'text/css' });
    if (u.startsWith(BASE)) return r.continue();
    return r.abort();
  });
  const dialogAnswers = [];
  p.on('dialog', d => d.accept(dialogAnswers.shift() ?? ''));

  // 1. demo loads
  await p.goto(BASE);
  await p.waitForTimeout(2500);
  const markers = await p.locator('.fh-marker').count();
  const first = (await (await p.request.get(BASE + '/api/incidents')).json())[0];
  const snap = await (await p.request.get(`${BASE}/api/incidents/${first.id}/snapshot`)).json();
  const expected = snap.images.filter((i) => i.published && i.location).length;
  log(markers === expected, `demo: ${expected} markers on the map`, `${markers}`);
  const zones = await p.locator('.zone').count();
  log(zones > 0, 'demo: zones listed', `${zones}`);
  log(await p.locator('.briefing').count() === 1, 'demo: briefing shown');
  const banner = await p.locator('#banner').innerText();
  log(/Historical scenario/.test(banner), 'demo: historical banner', banner.slice(0, 60));
  await p.click('[data-lang="bs"]'); await p.waitForTimeout(500);
  log(/Zone po prioritetu|Nije provjereno/.test(await p.locator('.briefing').innerText()), 'demo: Bosnian briefing toggle');
  await shot(p, '1_demo');

  // 2. detail panel
  await p.locator('.rank li').first().click(); await p.waitForTimeout(1200);
  log(!(await p.locator('#detail-view').isHidden()), 'detail: opens from list');
  const objs = await p.locator('.findings li').count();
  log(objs > 0, 'detail: objects listed', `${objs}`);
  const img = await p.locator('#detail-img').evaluate(i => i.complete && i.naturalWidth > 0);
  log(img, 'detail: overlay image loads');
  await p.click('.toggle button[data-view="photo"]'); await p.waitForTimeout(800);
  log(await p.locator('#detail-img').evaluate(i => i.src.endsWith('/photo')), 'detail: original toggle');
  await shot(p, '2_detail');
  log(!(await p.locator('.review button').first().isVisible()), 'demo is read-only: no confirm/reject buttons shown');
  await p.setInputFiles('#file-input', [`${DATA}/gps1.jpg`]); await p.waitForTimeout(600);
  log(/read-only/.test(await p.locator('#banner').innerText()), 'demo: upload explains read-only', await p.locator('#banner').innerText());
  await p.keyboard.press('Escape'); await p.waitForTimeout(300);

  // 3. new incident + upload (real API)
  dialogAnswers.push('UI test incident', 'Somewhere, USA');
  await p.click('#new-incident'); await p.waitForTimeout(1500);
  log(/UI test incident/.test(await p.locator('#incident-select option:checked').innerText()), 'new incident created and selected');
  await p.setInputFiles('#file-input', [`${DATA}/gps1.jpg`, `${DATA}/gps2.jpg`, `${DATA}/nogps.jpg`]);
  await p.waitForTimeout(1500);
  log(/added/.test(await p.locator('#banner').innerText()), 'upload: confirmation banner', await p.locator('#banner').innerText());
  const t0 = Date.now(); let onMap = 0, tray = 0;
  while (Date.now() - t0 < 240000) {
    await p.waitForTimeout(3000);
    onMap = await p.locator('.fh-marker').count();
    tray = await p.locator('.tray-item').count();
    const working = await p.locator('#counts').innerText();
    if (onMap >= 2 && /^0/.test(working.trim())) break;
  }
  log(onMap === 2, 'upload: 2 GPS photos appear live on the map (SSE)', `${onMap} after ${Math.round((Date.now() - t0) / 1000)} s`);
  log(tray === 1, 'upload: GPS-less photo waits in "Needs a location"', `${tray}`);
  await shot(p, '3_uploaded');

  // 4. pin
  if (tray) {
    await p.locator('.tray-item').first().click(); await p.waitForTimeout(300);
    log(!(await p.locator('#pin-hint').isHidden()), 'pin: hint shown');
    const box = await p.locator('#map').boundingBox();
    await p.mouse.click(box.x + box.width / 2, box.y + box.height / 2); await p.waitForTimeout(2500);
    log(await p.locator('.fh-marker').count() === 3, 'pin: photo appears on the map after one click', `${await p.locator('.fh-marker').count()}`);
    log(await p.locator('.tray-item').count() === 0, 'pin: tray empties');
  }

  // 5. reject changes summary
  await p.locator('#rank li').first().click(); await p.waitForTimeout(1200);
  const before = await p.locator('.findings li.rejected').count();
  if (await p.locator('.review button[data-action="reject"]').count()) {
    await p.locator('.review button[data-action="reject"]').first().click(); await p.waitForTimeout(1500);
    log(await p.locator('.findings li.rejected').count() === before + 1, 'review: rejected finding is struck through');
  } else log(false, 'review: no objects to reject on first photo');
  await p.keyboard.press('Escape'); await p.waitForTimeout(500);

  // 6. agent (real Muse Spark)
  await p.click('#run-agent');
  const t1 = Date.now(); let status = '';
  while (Date.now() - t1 < 240000) {
    await p.waitForTimeout(4000);
    status = await p.locator('#agent-status').innerText();
    if (/finished|failed|stopped/.test(status)) break;
  }
  log(/finished/.test(status), 'agent: run finishes', `${status} (${Math.round((Date.now() - t1) / 1000)} s)`);
  log(await p.locator('.zone').count() > 0, 'agent: zones appear without reload', `${await p.locator('.zone').count()}`);
  log(await p.locator('.briefing').count() === 1, 'agent: briefing appears');
  log(await p.locator('#agent-log li').count() > 0, 'agent: action log shown', `${await p.locator('#agent-log li').count()} actions`);
  await shot(p, '4_agent');

  // 7. zone lock
  await p.locator('select[data-zone]').first().selectOption('5'); await p.waitForTimeout(1500);
  log(/locked/.test(await p.locator('.zone').first().innerText() + await p.locator('#zones').innerText()), 'zone: responder priority shows as locked');

  // 8. mobile
  await p.setViewportSize({ width: 390, height: 844 }); await p.waitForTimeout(800);
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  log(!overflow, 'mobile: no horizontal scroll');
  await shot(p, '5_mobile');

  log(errors.length === 0, 'no JS errors in console', errors.slice(0, 3).join(' | '));
  require('fs').writeFileSync(`${S}/e2e_results.json`, JSON.stringify(findings, null, 2));
  await b.close();
})();
