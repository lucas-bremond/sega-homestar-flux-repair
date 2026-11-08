// Headless check of index.html: no JS errors, every tab renders, net and part
// selection highlight the right boxes, the confidence filter and search work.
// Writes screenshots to ./shots. Run from the repo root (needs Docker):
//   docker run --rm -v "$PWD":/repo:ro -v "$PWD/analysis/pcb-model/tests":/t -w /t node:22-bookworm-slim sh -c \
//     "apt-get update -qq && apt-get install -y -qq chromium >/dev/null && npm i -s puppeteer-core@23 && node ui-test.mjs"
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';

const page_url = 'file:///repo/analysis/pcb-model/index.html';
fs.mkdirSync('shots', { recursive: true });
const browser = await puppeteer.launch({
  executablePath: '/usr/bin/chromium',
  args: ['--no-sandbox', '--disable-gpu'],
});
const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 1100 });
const errors = [];
page.on('pageerror', e => errors.push('pageerror: ' + e.message));
page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
await page.goto(page_url, { waitUntil: 'load' });

const results = [];
const check = (name, ok, info = '') => results.push(`${ok ? 'PASS' : 'FAIL'} ${name}${info ? ' — ' + info : ''}`);

const counts = await page.evaluate(() => ({
  nets: document.querySelectorAll('#nets li').length,
  parts: document.querySelectorAll('#parts li').length,
  boxes: document.querySelectorAll('.box').length,
  questions: document.querySelectorAll('.q').length,
  imgs: [...document.querySelectorAll('.stage img')].map(i => i.naturalWidth),
}));
check('net list', counts.nets === 16, `${counts.nets} nets`);
check('part list', counts.parts === 55, `${counts.parts} parts`);
check('photo boxes', counts.boxes > 60, `${counts.boxes} boxes`);
check('photos decoded', counts.imgs.every(w => w === 2400), counts.imgs.join(','));
check('open questions', counts.questions === 8, `${counts.questions}`);

// select net M+ : expect J_MP, U4, C6 highlighted
await page.evaluate(() => [...document.querySelectorAll('#nets li')].find(l => l.dataset.net === 'M+').click());
const hitNet = await page.evaluate(() => [...new Set([...document.querySelectorAll('.box.hit')].map(b => b.dataset.ref))].sort());
check('net M+ highlights its parts', JSON.stringify(hitNet) === JSON.stringify(['C6', 'J_MP', 'U4']), hitNet.join(','));
await page.screenshot({ path: 'shots/net-mplus.png', fullPage: false });

// click U4's box: detail shows 8 pins, VDD on U4_VDD
await page.evaluate(() => document.querySelector('.box[data-ref="U4"]').dispatchEvent(new MouseEvent('click', { bubbles: true })));
const u4 = await page.evaluate(() => ({ rows: document.querySelectorAll('#detail table tr').length - 1, text: document.querySelector('#detail').innerText }));
check('part U4 detail', u4.rows === 8 && u4.text.includes('U4_VDD') && u4.text.includes('OQ1'), `${u4.rows} pins`);
await page.evaluate(() => window.scrollTo(0, 0));
await page.screenshot({ path: 'shots/part-u4.png' });

// filter: untick 'assumed' -> GND loses assumed nodes
await page.evaluate(() => { const c = document.querySelector('input[data-c="assumed"]'); c.click(); });
await page.evaluate(() => [...document.querySelectorAll('#nets li')].find(l => l.dataset.net === 'GND').click());
const gnd = await page.evaluate(() => document.querySelectorAll('#detail table tr').length - 1);
check('confidence filter hides assumed', gnd === 4, `${gnd} GND pins shown`);
await page.evaluate(() => document.querySelector('input[data-c="assumed"]').click());

// search
await page.type('#search', 'shoot');
const filtered = await page.evaluate(() => document.querySelectorAll('#nets li').length + document.querySelectorAll('#parts li').length);
check('search filters', filtered > 0 && filtered < 20, `${filtered} items`);

// tabs
for (const tab of ['diagram', 'schematic', 'questions']) {
  await page.evaluate(t => document.querySelector(`nav button[data-tab="${t}"]`).click(), tab);
  const vis = await page.evaluate(t => {
    const el = document.querySelector('#tab-' + t);
    const svg = el.querySelector('svg');
    return { shown: getComputedStyle(el).display !== 'none', svgH: svg ? svg.getBoundingClientRect().height : -1 };
  }, tab);
  check(`tab ${tab}`, vis.shown && (tab === 'questions' || vis.svgH > 100), `svg height ${Math.round(vis.svgH)}`);
  await page.screenshot({ path: `shots/tab-${tab}.png` });
}
// block click -> back to board with highlights
await page.evaluate(() => document.querySelector('nav button[data-tab="diagram"]').click());
await page.evaluate(() => document.querySelector('.diagram .block[data-block="motor"]').dispatchEvent(new MouseEvent('click', { bubbles: true })));
const blockHits = await page.evaluate(() => new Set([...document.querySelectorAll('.box.hit')].map(b => b.dataset.ref)).size);
check('block click highlights parts', blockHits >= 7, `${blockHits} parts`);

// ---------------------------------------------------------------- editor
await page.evaluate(() => { document.querySelector('nav button[data-tab="board"]').click(); localStorage.clear(); });
await page.reload({ waitUntil: 'load' });
const E = (fn, ...a) => page.evaluate(fn, ...a);
await E(() => document.querySelector('#edit').click());
check('edit mode opens', await E(() => !document.querySelector('#editbar').hidden));

// draw a 3-point trace on the top photo, finish with a double-click
const tracesBefore = await E(() => window.__editor.state().traces.length);
await E(() => document.querySelector('[data-tool="draw"]').click());
for (const [x, y] of [[1500, 2300], [1600, 2350], [1700, 2320]]) {
  const p = await E((x, y) => window.__editor.toScreen('top', x, y), x, y);
  await page.mouse.click(p.x, p.y);
}
const last = await E(() => window.__editor.toScreen('top', 1700, 2320));
await page.mouse.click(last.x, last.y, { clickCount: 2 });
const drawn = await E(() => window.__editor.state().traces.at(-1));
check('draw a trace', (await E(() => window.__editor.state().traces.length)) === tracesBefore + 1 && drawn.points.length === 3 && drawn.side === 'top',
  `${drawn.id}: ${drawn.points.length} points`);
await page.select('#tnet', 'M-');
await E(() => { const i = document.querySelector('#tev'); i.value = 'test trace'; i.dispatchEvent(new Event('change')); });
const named = await E(id => window.__editor.state().traces.find(t => t.id === id), drawn.id);
check('set trace net and evidence', named.net === 'M-' && named.evidence === 'test trace');
check('no text selection after drawing', await E(() => String(window.getSelection()) === '' && window.getSelection().type !== 'Range'));
await page.screenshot({ path: 'shots/edit-trace.png' });

// drag the first point of trace t1 by 40 screen px
await E(() => document.querySelector('#traces li[data-trace="t1"]').click());
const p0 = await E(() => window.__editor.state().traces.find(t => t.id === 't1').points[0]);
const h = await E((x, y) => window.__editor.toScreen('top', x, y), ...p0);
await page.mouse.move(h.x, h.y); await page.mouse.down(); await page.mouse.move(h.x + 20, h.y, { steps: 4 }); await page.mouse.move(h.x + 40, h.y, { steps: 4 }); await page.mouse.up();
const p1 = await E(() => window.__editor.state().traces.find(t => t.id === 't1').points[0]);
check('drag a trace point', p1[0] > p0[0] + 50 && Math.abs(p1[1] - p0[1]) < 10, `${p0} -> ${p1}`);

// move U4's box
await E(() => [...document.querySelectorAll('#parts li')].find(l => l.textContent.startsWith('U4')).click());
const b0 = await E(() => window.__editor.state().boxes.U4);
const u4box = await E(() => { const r = document.querySelector('#stage-top .editbox').getBoundingClientRect(); return {x: r.x + r.width / 2, y: r.y + r.height / 2}; });
await page.mouse.move(u4box.x, u4box.y); await page.mouse.down(); await page.mouse.move(u4box.x + 15, u4box.y + 10, { steps: 5 }); await page.mouse.up();
const b1 = await E(() => window.__editor.state().boxes.U4);
check('move a part box', !b0 && b1 && b1.top && b1.top[0] !== 938, JSON.stringify(b1));

// connection: U4 pin 4 onto DC+ as measured
await page.select('#detail tr[data-pin="4"] .pnet', 'DC+');
await page.select('#detail tr[data-pin="4"] .pconf', 'measured');
await E(() => { const i = document.querySelector('#detail tr[data-pin="4"] .pev'); i.value = 'test: continuity to DC+'; i.dispatchEvent(new Event('change')); });
const nets1 = await E(() => window.__editor.nets());
check('edit a connection', nets1['DC+'].some(n => n[0] === 'U4' && n[1] === '4' && n[2] === 'measured') && !nets1['U4_VDD'].some(n => n[0] === 'U4' && n[1] === '4'));
await page.screenshot({ path: 'shots/edit-part.png' });
for (let i = 0; i < 3; i++) await E(() => document.querySelector('#undo').click());   // net, confidence, evidence: three edits
const nets2 = await E(() => window.__editor.nets());
check('undo three edits', nets2['U4_VDD'].some(n => n[0] === 'U4' && n[1] === '4' && n[2] === 'datasheet'));
await page.select('#detail tr[data-pin="4"] .pnet', 'DC+');
await page.select('#detail tr[data-pin="4"] .pconf', 'measured');

// export: the build must produce the same nets from this file (checked outside, see edit-*.json)
const exported = await E(() => window.__editor.exportText());
fs.writeFileSync('shots/edit-annotations.json', exported);
fs.writeFileSync('shots/edit-nets.json', JSON.stringify(await E(() => window.__editor.nets())));
check('export', JSON.parse(exported).traces.length === tracesBefore + 1 && JSON.parse(exported).connections.length === 1);

// edits survive a reload; discard restores the build
await page.reload({ waitUntil: 'load' });
const banner = await E(() => !document.querySelector('#banner').hidden && document.querySelector('#banner').textContent);
check('edits restored after reload', !!banner && banner.includes('Restored'), banner || '');
await E(() => document.querySelector('#b-discard').click());
const afterDiscard = await E(() => window.__editor.state());
check('discard', afterDiscard.traces.length === tracesBefore && (afterDiscard.connections || []).length === 0);

// import the exported file back
await E(text => window.__editor.importAnnotations(text), exported);
check('import', (await E(() => window.__editor.state().traces.length)) === tracesBefore + 1);
await E(() => localStorage.clear());

check('no JS errors', errors.length === 0, errors.join(' | '));
console.log(results.join('\n'));
await browser.close();
process.exit(results.some(r => r.startsWith('FAIL')) ? 1 : 0);
