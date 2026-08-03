import { chromium } from 'patchright';
import { readFileSync, writeFileSync } from 'fs';

let browser, page;

async function connect() {
  browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const pages = browser.contexts()[0]?.pages() || [];
  page = pages[0] || await browser.newPage();
  return { ok: true, pages: pages.length };
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
  return { ok: true };
}

async function clickByText(text) {
  if (!page) await connect();
  const el = await page.locator(`text="${text}"`).first();
  if (!el) return { ok: false, error: 'text not found: ' + text };
  await el.scrollIntoViewIfNeeded();
  await el.click({ timeout: 10000 });
  return { ok: true };
}

async function evaluate(js) {
  if (!page) await connect();
  const result = await page.evaluate(js);
  return { ok: true, result };
}

async function screenshot(path) {
  if (!page) await connect();
  await page.screenshot({ path: path || '/tmp/boss_ss.png', fullPage: false });
  return { ok: true, path: path || '/tmp/boss_ss.png' };
}

async function getJobCards() {
  const cards = await page.evaluate(() => {
    const cards = document.querySelectorAll('.job-card-box');
    return JSON.stringify(Array.from(cards).slice(0, 30).map(c => {
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

async function typeAndSend(text) {
  const input = await page.$('div[contenteditable="true"], textarea');
  if (!input) return { ok: false, error: 'no input found' };
  await input.fill(text);
  await page.waitForTimeout(500);
  const sendBtn = await page.locator('text=发送').first();
  if (sendBtn) await sendBtn.click();
  return { ok: true };
}

async function close() {
  if (browser) await browser.close();
}

// Read commands from stdin (JSON per line)
const readline = require('readline');
const rl = readline.createInterface({ input: process.stdin, terminal: false });

rl.on('line', async (line) => {
  try {
    const cmd = JSON.parse(line);
    const { id, method, args } = cmd;
    let result;
    switch (method) {
      case 'connect': result = await connect(); break;
      case 'navigate': result = await navigate(args.url); break;
      case 'click': result = await click(args.selector); break;
      case 'clickByText': result = await clickByText(args.text); break;
      case 'evaluate': result = await evaluate(args.js); break;
      case 'screenshot': result = await screenshot(args.path); break;
      case 'getJobCards': result = await getJobCards(); break;
      case 'typeAndSend': result = await typeAndSend(args.text); break;
      case 'close': result = { ok: true }; await close(); break;
      default: result = { ok: false, error: 'unknown method: ' + method };
    }
    process.stdout.write(JSON.stringify({ id, result }) + '\n');
  } catch (e) {
    process.stdout.write(JSON.stringify({ id: -1, error: e.message }) + '\n');
  }
});
