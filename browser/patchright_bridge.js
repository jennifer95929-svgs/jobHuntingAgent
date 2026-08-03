const { chromium } = require('/Users/xx/.nvm/versions/node/v24.11.0/lib/node_modules/patchright');
const readline = require('readline');
const { writeFileSync } = require('fs');

let browser, page, _browserInstance;

async function connect() {
  const userDataDir = '/tmp/chrome-debug-profile';
  const ctx = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    channel: 'chrome',
    args: [
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-blink-features=AutomationControlled',
    ]
  });
  browser = ctx;
  _browserInstance = ctx._browser || ctx.browser();
  page = ctx.pages()[0] || await ctx.newPage();
  return { ok: true, launched: true, chrome: true };
}

async function navigate(url) {
  if (!page) await connect();
  await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
  return { ok: true, url: page.url(), title: await page.title() };
}

async function click(selector) {
  if (!page) await connect();
  const el = await page.$(selector);
  if (!el) return { ok: false, error: 'element not found: ' + selector };
  await el.scrollIntoViewIfNeeded();
  await el.click({ timeout: 10000 });
  return { ok: true, selector };
}

async function findElements(selector) {
  if (!page) await connect();
  return { ok: true, count: await page.$$eval(selector, els => els.length) };
}

async function evaluate(js) {
  if (!page) await connect();
  const result = await page.evaluate(js);
  return { ok: true, result };
}

async function getAttribute(selector, attr) {
  if (!page) await connect();
  const val = await page.$eval(selector, (el, a) => el.getAttribute(a), attr);
  return { ok: true, value: val };
}

async function screenshot(path) {
  if (!page) await connect();
  const p = path || '/tmp/boss_ss.png';
  await page.screenshot({ path: p, fullPage: false });
  return { ok: true, path: p };
}

async function getJobCards() {
  if (!page) await connect();
  const cards = await page.evaluate(() => {
    return JSON.stringify(Array.from(document.querySelectorAll('.job-card-box')).slice(0, 30).map(c => {
      const link = c.querySelector('a[href*="/job_detail/"]');
      const titleEl = c.querySelector('.job-name');
      const salaryEl = c.querySelector('.job-salary');
      const href = link ? link.getAttribute('href') : '';
      const match = href ? href.match(/\/job_detail\/([^\/]+?)\.html/) : null;
      return {
        id: match ? match[1] : '',
        title: titleEl ? titleEl.textContent.trim() : '',
        salary: salaryEl ? salaryEl.textContent.trim() : '',
        href: href ? 'https://www.zhipin.com' + href : ''
      };
    }).filter(c => c.id));
  });
  return { ok: true, cards };
}

const rl = readline.createInterface({ input: process.stdin, terminal: false });

rl.on('line', async (line) => {
  let cmdId = -1;
  try {
    const cmd = JSON.parse(line.trim());
    cmdId = cmd.id || -1;
    const { id, method, args } = cmd;
    let result;
    switch (method) {
      case 'connect': result = await connect(); break;
      case 'navigate': result = await navigate(args?.url); break;
      case 'click': result = await click(args?.selector); break;
      case 'findElements': result = await findElements(args?.selector); break;
      case 'getAttribute': result = await getAttribute(args?.selector, args?.attr); break;
      case 'evaluate': result = await evaluate(args?.js); break;
      case 'screenshot': result = await screenshot(args?.path); break;
      case 'getJobCards': result = await getJobCards(); break;
      case 'close': await browser?.close(); if (_browserInstance) await _browserInstance.close(); result = { ok: true }; break;
      default: result = { ok: false, error: 'unknown: ' + method };
    }
    process.stdout.write(JSON.stringify({ id, result }) + '\n');
  } catch (e) {
    process.stdout.write(JSON.stringify({ id: cmdId, error: e.message }) + '\n');
  }
});
