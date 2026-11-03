// Playwright verification for the election dashboard (standalone mode).
const http = require('http');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = '/home/claude/election-dashboard/app';
const SHOTS = path.join(ROOT, 'screenshots');
const MIME = { '.html': 'text/html', '.json': 'application/json', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png' };

function serve() {
  return new Promise(resolve => {
    const srv = http.createServer((req, res) => {
      const u = decodeURIComponent(req.url.split('?')[0]);
      let fp = path.join(ROOT, u === '/' ? 'index.html' : u);
      if (!fp.startsWith(ROOT)) { res.writeHead(403); return res.end(); }
      fs.readFile(fp, (err, data) => {
        if (err) { res.writeHead(404); return res.end('not found'); }
        res.writeHead(200, { 'Content-Type': MIME[path.extname(fp)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
        res.end(data);
      });
    });
    srv.listen(0, '127.0.0.1', () => resolve(srv));
  });
}

async function clickData(page, selector, id) {
  const h = await page.evaluateHandle(({ selector, id }) => document.querySelector(`${selector}[data-id="${id}"]`), { selector, id });
  const el = h.asElement();
  if (!el) throw new Error('no element ' + selector + ' ' + id);
  await el.scrollIntoViewIfNeeded();
  const box = await el.boundingBox();
  // click the centroid of the shape (from the page's own path geometry), not the bbox centre
  const pt = await page.evaluate(({ selector, id }) => {
    const el = document.querySelector(`${selector}[data-id="${id}"]`);
    const svg = el.ownerSVGElement; const ctm = el.getScreenCTM();
    const bb = el.getBBox();
    // sample a few points inside the bbox and pick the first that hits this element
    const cands = [[.5,.5],[.4,.5],[.6,.5],[.5,.4],[.5,.6],[.3,.3],[.7,.7],[.3,.7],[.7,.3]];
    for (const [fx, fy] of cands) {
      const p = svg.createSVGPoint(); p.x = bb.x + bb.width * fx; p.y = bb.y + bb.height * fy;
      const s = p.matrixTransform(ctm);
      const hit = document.elementFromPoint(s.x, s.y);
      if (hit === el) return { x: s.x, y: s.y };
    }
    return null;
  }, { selector, id });
  if (!pt) throw new Error('could not find a hit point for ' + id);
  await page.mouse.click(pt.x, pt.y);
}

(async () => {
  const srv = await serve();
  const port = srv.address().port;
  const base = `http://127.0.0.1:${port}/`;
  const browser = await chromium.launch();
  const results = { consoleErrors: [], pageErrors: [], perf: {} };
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await ctx.newPage();
  page.on('console', m => { const t = m.text(); if (m.type() === 'error') results.consoleErrors.push(t); if (t.startsWith('[perf]') || t.startsWith('[mode]')) console.log('  console:', t); });
  page.on('pageerror', e => results.pageErrors.push(String(e)));
  page.on('requestfailed', r => { const u = r.url(); if (!/youtube|googlevideo|fonts/.test(u)) results.consoleErrors.push('requestfailed ' + u + ' ' + r.failure().errorText); });

  const t0 = Date.now();
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => window.__firstMapRender != null, null, { timeout: 15000 });
  results.perf.firstMapRender_ms = await page.evaluate(() => window.__firstMapRender);
  results.perf.wallToFirstMap_ms = Date.now() - t0;
  results.perf.navTiming = await page.evaluate(() => { const n = performance.getEntriesByType('navigation')[0]; return n ? { domContentLoaded: n.domContentLoadedEventEnd, loadEvent: n.loadEventEnd } : null; });
  results.perf.paint = await page.evaluate(() => performance.getEntriesByType('paint').map(p => [p.name, Math.round(p.startTime)]));

  // wait for dataset + start overlay
  await page.waitForFunction(() => document.querySelector('#stamp').textContent.includes('Updated'), null, { timeout: 15000 });
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(SHOTS, '01-national-overlay-1920.png') });
  await page.click('#start-skip');
  await page.waitForTimeout(600);
  results.header = await page.evaluate(() => ({ headline: document.querySelector('#headline').textContent, stamp: document.querySelector('#stamp').textContent, tallies: document.querySelectorAll('.tally').length, agents: document.querySelector('#agents').textContent, panels: document.querySelectorAll('.vpanel').length, panelIds: [...document.querySelectorAll('.vpanel')].map(e => e.dataset.id) }));
  results.stateFills = await page.evaluate(() => { const o = {}; for (const id of ['42', '39', '26', '37', '48', '06']) { const p = document.querySelector(`path.region.state[data-id="${id}"]`); o[id] = { fill: p.getAttribute('fill'), called: p.classList.contains('called') }; } return { fills: o, hatched: document.querySelectorAll('.g-tex path').length }; });
  await page.screenshot({ path: path.join(SHOTS, '02-national-1920.png') });

  // hover a state for the tooltip/elevation
  await page.hover('path.region.state[data-id="13"]');
  await page.waitForTimeout(300);
  results.tooltip = await page.evaluate(() => document.querySelector('#tooltip').textContent);

  // drill into Pennsylvania
  await clickData(page, 'path.region.state', '42');
  await page.waitForFunction(() => document.querySelectorAll('path.region.county').length > 0 && document.querySelector('#stage-body').classList.contains('open'), null, { timeout: 15000 });
  await page.waitForTimeout(1100);
  results.state = await page.evaluate(() => ({ counties: document.querySelectorAll('path.region.county').length, crumbs: document.querySelector('#crumbs').textContent, detailTitle: document.querySelector('#detail h2').textContent, badges: [...document.querySelectorAll('#detail .badge')].map(b => b.textContent.trim()), cands: [...document.querySelectorAll('#detail .cand .nm')].map(e => e.textContent.trim()), panelIds: [...document.querySelectorAll('.vpanel')].map(e => e.dataset.id), hatched: document.querySelectorAll('.g-tex path').length, countyFill42101: document.querySelector('path.region.county[data-id="42101"]').getAttribute('fill'), countyFill42129: document.querySelector('path.region.county[data-id="42129"]').getAttribute('fill') }));
  await page.screenshot({ path: path.join(SHOTS, '03-state-pa-1920.png') });

  // switch to Governor layer and Swing layer
  await page.click('#layers button[data-layer="GOV"]');
  await page.waitForTimeout(600);
  results.govFill42 = await page.evaluate(() => ({ s42: document.querySelector('path.region.state[data-id="42"]').getAttribute('fill'), called: document.querySelector('path.region.state[data-id="42"]').classList.contains('called'), c42101: document.querySelector('path.region.county[data-id="42101"]').getAttribute('fill'), legend: document.querySelector('#legend .lt').textContent }));
  await page.screenshot({ path: path.join(SHOTS, '04-state-pa-governor-1920.png') });
  await page.click('#layers button[data-layer="SWING"]');
  await page.waitForTimeout(600);
  results.swing = await page.evaluate(() => ({ legend: document.querySelector('#legend .lt').textContent, c42101: document.querySelector('path.region.county[data-id="42101"]').getAttribute('fill'), optsVisible: !document.querySelector('#swing-opts').classList.contains('hidden') }));
  await page.screenshot({ path: path.join(SHOTS, '05-state-pa-swing-1920.png') });
  await page.click('#layers button[data-layer="SEN"]');
  await page.waitForTimeout(300);

  // drill into Philadelphia County
  await clickData(page, 'path.region.county', '42101');
  await page.waitForFunction(() => document.querySelectorAll('circle.city').length > 0, null, { timeout: 15000 });
  await page.waitForTimeout(1100);
  results.county = await page.evaluate(() => ({ cities: [...document.querySelectorAll('circle.city')].map(c => c.dataset.id), crumbs: document.querySelector('#crumbs').textContent, detailTitle: document.querySelector('#detail h2').textContent, panelIds: [...document.querySelectorAll('.vpanel')].map(e => e.dataset.id) }));
  await page.screenshot({ path: path.join(SHOTS, '06-county-philadelphia-1920.png') });

  // click the city marker
  await clickData(page, 'circle.city', '42101:philadelphia');
  await page.waitForTimeout(1000);
  results.city = await page.evaluate(() => ({ crumbs: document.querySelector('#crumbs').textContent, detailTitle: document.querySelector('#detail h2').textContent, badges: [...document.querySelectorAll('#detail .badge')].map(b => b.textContent.trim()), panelIds: [...document.querySelectorAll('.vpanel')].map(e => e.dataset.id) }));
  await page.screenshot({ path: path.join(SHOTS, '07-city-philadelphia-1920.png') });

  // Pittsburgh via search (inherited city row)
  await page.fill('#search-in', 'Pittsburgh');
  await page.waitForTimeout(400);
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelector('#detail h2') && document.querySelector('#detail h2').textContent === 'Pittsburgh', null, { timeout: 15000 });
  await page.waitForTimeout(900);
  results.pittsburgh = await page.evaluate(() => ({ badges: [...document.querySelectorAll('#detail .badge')].map(b => b.textContent.trim()), crumbs: document.querySelector('#crumbs').textContent, panelIds: [...document.querySelectorAll('.vpanel')].map(e => e.dataset.id) }));
  await page.screenshot({ path: path.join(SHOTS, '08-city-pittsburgh-inherited-1920.png') });

  // ask a question
  await page.fill('#ask-in', "what's Michigan");
  await page.press('#ask-in', 'Enter');
  await page.waitForTimeout(1500);
  results.answer = await page.evaluate(() => document.querySelector('#transcript-txt').textContent);
  await page.fill('#ask-in', 'senate');
  await page.press('#ask-in', 'Enter');
  await page.waitForTimeout(300);
  results.answerSenate = await page.evaluate(() => document.querySelector('#transcript-txt').textContent);
  await page.screenshot({ path: path.join(SHOTS, '09-question-michigan-1920.png') });

  // escape back up to national
  await page.keyboard.press('Escape'); await page.waitForTimeout(800);
  await page.keyboard.press('Escape'); await page.waitForTimeout(800);
  results.afterEsc = await page.evaluate(() => document.querySelector('#crumbs').textContent);

  // tilt off
  await page.click('#tilt'); await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(SHOTS, '10-national-tilt-off-1920.png') });

  // mobile
  const mctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
  const mp = await mctx.newPage();
  mp.on('console', m => { if (m.type() === 'error') results.consoleErrors.push('[mobile] ' + m.text()); });
  mp.on('pageerror', e => results.pageErrors.push('[mobile] ' + String(e)));
  const mt0 = Date.now();
  await mp.goto(base, { waitUntil: 'domcontentloaded' });
  await mp.waitForFunction(() => window.__firstMapRender != null, null, { timeout: 15000 });
  results.perf.mobileFirstMapRender_ms = await mp.evaluate(() => window.__firstMapRender);
  results.perf.mobileWall_ms = Date.now() - mt0;
  await mp.waitForFunction(() => document.querySelector('#stamp').textContent.includes('Updated'), null, { timeout: 15000 });
  await mp.waitForTimeout(500);
  await mp.click('#start-skip');
  await mp.waitForTimeout(500);
  await mp.screenshot({ path: path.join(SHOTS, '11-mobile-national-390.png'), fullPage: true });
  await clickData(mp, 'path.region.state', '48');
  await mp.waitForFunction(() => document.querySelectorAll('path.region.county').length > 0, null, { timeout: 15000 });
  await mp.waitForTimeout(1100);
  results.mobile = await mp.evaluate(() => ({ counties: document.querySelectorAll('path.region.county').length, panels: document.querySelectorAll('.vpanel').length, detail: document.querySelector('#detail h2') && document.querySelector('#detail h2').textContent, bodyScrollW: document.documentElement.scrollWidth, vw: innerWidth }));
  await mp.screenshot({ path: path.join(SHOTS, '12-mobile-state-tx-390.png'), fullPage: true });


  // ---- artifact-mode simulation: fake window.claude.use('db') serving a chunked dataset document
  const sample = fs.readFileSync(path.join(ROOT, 'data/dataset.sample.json'), 'utf8');
  const actx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  await actx.addInitScript((sampleStr) => {
    const parts = []; for (let i = 0; i < sampleStr.length; i += 40000) parts.push(sampleStr.slice(i, i + 40000));
    const docs = { 'dataset/current': { refresh_id: 'r-0007', generated_at: '2026-11-04T02:35:00Z', parts: parts.length } };
    parts.forEach((c, i) => docs['dataset/current-p' + i] = { i, json: c });
    window.__dbGets = [];
    window.claude = { use: async (name) => { await new Promise(r => setTimeout(r, 400)); if (name !== 'db') return null;
      return { doc: (p) => ({ path: p, get: async () => { window.__dbGets.push(p); const d = docs[p]; return { id: p.split('/').pop(), exists: !!d, data: () => d, metadata: { fromCache: false, hasPendingWrites: false } }; } }) }; } };
  }, sample);
  const ap = await actx.newPage();
  ap.on('console', m => { const t = m.text(); if (m.type() === 'error') results.consoleErrors.push('[artifact] ' + t); if (t.startsWith('[mode]')) console.log('  console:', t); });
  ap.on('pageerror', e => results.pageErrors.push('[artifact] ' + String(e)));
  await ap.goto(base, { waitUntil: 'domcontentloaded' });
  await ap.waitForFunction(() => document.querySelector('#stamp').textContent.includes('Updated'), null, { timeout: 15000 });
  await ap.waitForTimeout(500);
  await ap.click('#start-skip');
  await ap.waitForTimeout(400);
  results.artifact = await ap.evaluate(() => ({ stamp: document.querySelector('#stamp').textContent, dbGets: window.__dbGets.length, iframes: document.querySelectorAll('iframe').length, cards: document.querySelectorAll('.vpanel .card a').length, cardLink: document.querySelector('.vpanel .card a') && document.querySelector('.vpanel .card a').getAttribute('href'), foot: document.querySelector('#rail-l .foot').textContent, mic: document.querySelector('#mic').classList.contains('hidden'), headline: document.querySelector('#headline').textContent.slice(0, 40) }));
  await ap.screenshot({ path: path.join(SHOTS, '13-artifact-mode-1920.png') });
  // warm start from localStorage: header must be populated at DOMContentLoaded, before any fetch resolves
  const warm = await ap.evaluate(() => new Promise(res => { const w = window.open ? null : null; res(null); }));
  await ap.reload({ waitUntil: 'commit' });
  const early = await ap.evaluate(() => new Promise(res => { const check = () => { const st = document.querySelector('#stamp'); if (st && st.textContent.length) return res({ stamp: st.textContent, tallies: document.querySelectorAll('.tally').length }); requestAnimationFrame(check); }; check(); }));
  results.warmStart = early;
  await actx.close();

  // ---- artifact mode with db unavailable (use resolves null)
  const nctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await nctx.addInitScript(() => { window.claude = { use: async () => { await new Promise(r => setTimeout(r, 200)); return null; } }; });
  const np = await nctx.newPage();
  np.on('pageerror', e => results.pageErrors.push('[artifact-null] ' + String(e)));
  await np.goto(base, { waitUntil: 'domcontentloaded' });
  await np.waitForFunction(() => /failed|unavailable/i.test(document.querySelector('#stamp').textContent), null, { timeout: 15000 });
  results.artifactNoDb = await np.evaluate(() => ({ stamp: document.querySelector('#stamp').textContent, mapPaths: document.querySelectorAll('path.region.state').length }));
  await nctx.close();

  await browser.close(); srv.close();
  console.log(JSON.stringify(results, null, 2));
})().catch(e => { console.error('VERIFY FAILED', e); process.exit(1); });
