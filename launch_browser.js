const { chromium } = require('/Users/xx/.nvm/versions/node/v24.11.0/lib/node_modules/patchright');

async function main() {
  console.log("启动 Patchright 有头浏览器...");
  const ctx = await chromium.launchPersistentContext('/tmp/chrome-debug-profile', {
    headless: false,
    channel: 'chrome',
    args: [
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-blink-features=AutomationControlled',
    ]
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  await page.goto('https://www.zhipin.com/web/user/', { waitUntil: 'load', timeout: 60000 });
  console.log("✅ BOSS直聘登录页已打开，请完成登录");
  console.log("浏览器会保持打开，登录后按 Ctrl+C 关闭此脚本");
}

main().catch(e => {
  console.error("错误:", e.message);
  process.exit(1);
});
