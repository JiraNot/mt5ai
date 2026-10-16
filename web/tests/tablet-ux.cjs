const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const out = process.env.TABLET_TEST_OUTPUT || require('node:path').join(require('node:os').tmpdir(), 'mt5ai-tablet-verification');
const previewURL = process.env.TABLET_TEST_URL || 'http://127.0.0.1:3017';
if (!['localhost', '127.0.0.1', '[::1]'].includes(new URL(previewURL).hostname)) throw new Error('ใช้ได้เฉพาะ preview ภายในเครื่อง');
fs.mkdirSync(out, { recursive: true });
const candles = Array.from({ length: 250 }, (_, i) => ({ time: 1700000000 + i * 300, open: 60000 + i * 2, close: 60003 + i * 2, high: 60008 + i * 2, low: 59995 + i * 2, volume: 50 + i }));
const position = { ticket: 101, symbol: 'BTCUSDT', direction: 'BUY', volume: 0.1, open_price: 60000, current_price: 60500, sl: 59000, tp: 62000, profit: 50, pnl_pct: 0.83 };
const report = { transport: 'local Playwright Chromium, emulated touch, mocked HTTP/WebSocket', checks: [], views: [] };
function check(view, name, passed, evidence) { report.checks.push({ view, name, passed, evidence }); }
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    for (const [width, height] of [[768, 1024], [820, 1180], [1024, 768], [1366, 1024], [1440, 900]]) {
      const view = `${width}x${height}`;
      const context = await browser.newContext({ viewport: { width, height }, hasTouch: true, deviceScaleFactor: 1 });
      const page = await context.newPage();
      const errors = [], requests = [], writes = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
      page.on('request', req => { if (req.url().includes('/api/')) requests.push(req.url()); });
      await page.routeWebSocket('**/ws', ws => ws.onMessage(() => ws.send(JSON.stringify({ type: 'tick', symbol: 'BTCUSDT', bid: 60500, ask: 60501, last: 60500, timestamp: 1700074700 }))));
      await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
      await page.route('https://fonts.gstatic.com/**', route => route.fulfill({ body: '' }));
      await page.route('**/api/**', async route => {
        const req = route.request();
        const path = new URL(req.url()).pathname;
        if (req.method() !== 'GET') { writes.push(path); return route.fulfill({ status: 403, json: { ok: false } }); }
        let data = { ok: true };
        if (path === '/api/status') data = { ok: true, mode: 'PAPER', account: { balance: 100000, equity: 100050 }, binance_connected: true };
        if (path === '/api/watchlist') data = { ok: true, data: { btc_report: { regime: 'TRENDING', trend_direction: 'BUY', recommendation_th: 'ข้อมูลจำลองสำหรับตรวจหน้าจอ' }, candidates: [{ symbol: 'ETHUSDT', price: 3000, price_change_pct: 1.5, score: 80 }] } };
        if (path === '/api/readiness') data = { ok: true, readiness_score: 25 };
        if (path === '/api/positions') data = { ok: true, positions: [position] };
        if (path === '/api/council/latest') data = { ok: true, latest: null, history: [] };
        if (path === '/api/history') data = { ok: true, trades: [{ id: 1, symbol: 'BTCUSDT', direction: 'BUY', volume: 0.1, entry_price: 60000, exit_price: 61000, profit: 100, r_multiple: 2, exit_reason: 'TAKE_PROFIT', exit_time: '2026-10-15T10:00:00Z' }] };
        if (path.startsWith('/api/candles/')) data = { ok: true, candles };
        await route.fulfill({ json: data });
      });
      await page.goto(previewURL, { waitUntil: 'networkidle' });
      await page.getByText('Loading Binance OHLCV...').waitFor({ state: 'hidden' });
      await page.screenshot({ path: `${out}/${view}-initial.png` });
      const layout = await page.evaluate(() => {
        const rect = e => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, right: r.right, bottom: r.bottom }; };
        const header = document.querySelector('header');
        return {
          header: rect(header),
          groups: Array.from(header.children).filter(e => getComputedStyle(e).display !== 'none').map(rect),
          controls: Array.from(document.querySelectorAll('button, a[href="/terminal"]')).filter(e => { const r = e.getBoundingClientRect(); return r.width && r.height && r.x >= 0 && r.right <= innerWidth; }).map(e => ({ label: e.textContent.trim() || e.title, ...rect(e) })),
          canvas: rect(document.querySelector('canvas')),
          documentWidth: document.documentElement.scrollWidth
        };
      });
      report.views.push({ view, layout });
      check(view, 'header groups do not overlap', layout.groups.every((r, i, list) => i === 0 || r.x >= list[i - 1].right), layout.groups);
      check(view, 'header controls fit viewport', await page.locator('header button, header a').evaluateAll(els => els.filter(e => getComputedStyle(e).display !== 'none').every(e => { const r = e.getBoundingClientRect(); return r.x >= 0 && r.right <= innerWidth; })), layout.groups);
      check(view, 'touch controls are at least 44px', layout.controls.every(r => r.height >= 44 && r.width >= 44), layout.controls.filter(r => r.height < 44 || r.width < 44));
      check(view, 'chart has usable height', layout.canvas.height >= 240, layout.canvas);
      const tf = page.getByRole('button', { name: '15m', exact: true });
      await Promise.all([page.waitForResponse(r => r.url().includes('timeframe=15m'), { timeout: 5000 }), tf.tap()]);
      check(view, 'timeframe requests selected data', requests.some(u => u.includes('timeframe=15m')), requests.filter(u => u.includes('/candles/')));
      const panel = page.locator('[class*="fixed lg:static"]');
      if (width >= 1200) await page.getByTitle('ซ่อนแถบข้าง (Full Chart)').tap();
      await page.getByTitle('แสดง AI Watchlist & Council').tap();
      await page.waitForTimeout(250);
      await page.screenshot({ path: `${out}/${view}-drawer.png` });
      const panelRect = await panel.boundingBox();
      check(view, 'sidebar opens inside viewport', panelRect.x >= 0 && panelRect.x + panelRect.width <= width, panelRect);
      await panel.getByRole('button', { name: 'AI Council', exact: true }).tap();
      check(view, 'council tab opens', !(await panel.getByRole('button', { name: 'Scan Now' }).count()), null);
      await panel.getByRole('button', { name: /Watchlist/ }).tap();
      await panel.getByText('ETHUSDT', { exact: true }).tap();
      await page.waitForTimeout(150);
      check(view, 'watchlist changes chart symbol', requests.some(u => u.includes('/candles/ETHUSDT')), requests.filter(u => u.includes('/candles/ETHUSDT')));
      if (width < 1024) await panel.getByTitle('ปิดแถบข้าง').tap();
      else await page.getByTitle('ซ่อนแถบข้าง (Full Chart)').tap();
      await page.waitForTimeout(250);
      const before = await page.locator('canvas').first().boundingBox();
      await page.getByTitle('ย่อตารางเพื่อดูกราฟเต็มจอ').tap();
      await page.waitForTimeout(300);
      const after = await page.locator('canvas').first().boundingBox();
      check(view, 'collapse increases chart height', after.height > before.height + 100, { before, after });
      await page.getByRole('button', { name: /Closed History/ }).tap();
      check(view, 'history tab expands table', await page.getByText('TAKE_PROFIT', { exact: true }).isVisible(), null);
      await page.getByRole('button', { name: /Active Positions/ }).tap();
      const scroller = page.locator('table').first().locator('..');
      const scrollState = await scroller.evaluate(el => { el.scrollLeft = el.scrollWidth; return { left: el.scrollLeft, width: el.clientWidth, scrollWidth: el.scrollWidth }; });
      check(view, 'position table overflow is locally scrollable', scrollState.scrollWidth <= scrollState.width || scrollState.left > 0, scrollState);
      await page.screenshot({ path: `${out}/${view}-positions.png` });
      check(view, 'no console or runtime errors', errors.length === 0, errors);
      check(view, 'no trading mutations sent', writes.length === 0, writes);
      await context.close();
    }
  } finally { await browser.close(); }
  report.passed = report.checks.filter(c => c.passed).length;
  report.failed = report.checks.filter(c => !c.passed).length;
  fs.writeFileSync(`${out}/report.json`, JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ passed: report.passed, failed: report.failed, failures: report.checks.filter(c => !c.passed).map(({ view, name }) => ({ view, name })), output: out }, null, 2));
  process.exitCode = report.failed ? 1 : 0;
})().catch(err => { console.error(err); process.exitCode = 2; });
