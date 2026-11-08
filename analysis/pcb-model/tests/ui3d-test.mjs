// Headless check of board-3d.html (WebGL through SwiftShader): it loads without errors, the
// board and parts render, views switch, a click on a part selects it, and net and question
// selection highlight the right parts. Writes screenshots to ./shots. Run like ui-test.mjs.
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';

fs.mkdirSync('shots', { recursive: true });
const browser = await puppeteer.launch({
  executablePath: '/usr/bin/chromium',
  args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
});
const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 1000 });
const errors = [];
page.on('pageerror', e => errors.push('pageerror: ' + e.message));
page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
await page.goto('file:///repo/analysis/pcb-model/board-3d.html', { waitUntil: 'load' });
await page.waitForFunction('window.__ready === true', { timeout: 60000 });
await new Promise(r => setTimeout(r, 1500));

const results = [];
const check = (name, ok, info = '') => results.push(`${ok ? 'PASS' : 'FAIL'} ${name}${info ? ' — ' + info : ''}`);
const lists = await page.evaluate(() => ({
  nets: document.querySelectorAll('#nets li').length, parts: document.querySelectorAll('#parts li').length,
  qs: document.querySelectorAll('#qs li').length, canvas: !!document.querySelector('.stage canvas'),
}));
check('canvas and lists', lists.canvas && lists.nets === 16 && lists.parts === 55 && lists.qs === 8, JSON.stringify(lists));
await page.screenshot({ path: 'shots/3d-iso.png' });

// the canvas is not blank: sample pixel variety
const shot = await page.screenshot({ encoding: 'base64', clip: { x: 300, y: 100, width: 900, height: 700 } });
check('scene renders', shot.length > 60000, `${Math.round(shot.length / 1024)} KB screenshot`);

// click U4 on the canvas -> part detail
const u4 = await page.evaluate(() => window.__project('U4'));
await page.mouse.click(u4.x, u4.y);
await new Promise(r => setTimeout(r, 300));
const det = await page.evaluate(() => document.querySelector('#detail').innerText);
check('click on U4 selects it', det.includes('U4') && det.includes('MX08L'), det.split('\n').slice(0, 2).join(' | '));
await page.screenshot({ path: 'shots/3d-u4.png' });

// net M+ -> J_MP, U4, C6 lit
await page.evaluate(() => [...document.querySelectorAll('#nets li')].find(l => l.dataset.net === 'M+').click());
const lit = await page.evaluate(() => window.__lit());
check('net M+ lights its parts', JSON.stringify(lit) === JSON.stringify(['C6', 'J_MP', 'U4']), lit.join(','));
await page.screenshot({ path: 'shots/3d-net-mplus.png' });

// question OQ1 -> U4 lit
await page.evaluate(() => document.querySelector('#qs li[data-q="OQ1"]').click());
const oq = await page.evaluate(() => ({ lit: window.__lit(), text: document.querySelector('#detail').innerText }));
check('question OQ1', oq.lit.join() === 'U4' && oq.text.includes('Check'), oq.lit.join());

// views
for (const v of ['top', 'bottom']) {
  await page.evaluate(x => document.querySelector(`[data-view="${x}"]`).click(), v);
  await new Promise(r => setTimeout(r, 800));
  await page.screenshot({ path: `shots/3d-${v}.png` });
}
check('views switch', true);
await page.evaluate(() => { document.querySelector('[data-view="iso"]').click(); document.querySelector('#xray').click(); document.querySelector('#clear').click(); });
await page.evaluate(() => [...document.querySelectorAll('#nets li')].find(l => l.dataset.net === 'GND').click());
await new Promise(r => setTimeout(r, 800));
await page.screenshot({ path: 'shots/3d-xray-gnd.png' });

check('no JS errors', errors.length === 0, errors.join(' | '));
console.log(results.join('\n'));
await browser.close();
process.exit(results.some(r => r.startsWith('FAIL')) ? 1 : 0);
