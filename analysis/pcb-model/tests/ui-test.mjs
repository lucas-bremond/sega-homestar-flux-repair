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
check('photos decoded', counts.imgs.every(w => w === 1600), counts.imgs.join(','));
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

check('no JS errors', errors.length === 0, errors.join(' | '));
console.log(results.join('\n'));
await browser.close();
process.exit(results.some(r => r.startsWith('FAIL')) ? 1 : 0);
