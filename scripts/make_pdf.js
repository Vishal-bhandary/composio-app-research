/**
 * Render the case study to a flat PDF.
 *
 * Google Drive and most form uploads will not preview an HTML file, so a PDF
 * is the better thing to attach to a submission. The live page stays the real
 * artifact - this is a readable fallback.
 *
 * Two things differ from the on-screen page:
 *   - the table filter UI is removed and every row is unhidden, because a PDF
 *     cannot be filtered
 *   - a banner is prepended with both URLs as plain text, because a reviewer
 *     reading on paper or in a preview pane cannot click a hyperlink
 *
 *   npm install playwright && npx playwright install chromium
 *   node scripts/make_pdf.js [github-username]
 */
const path = require('path');
const { chromium } = require('playwright');

const OWNER = process.argv[2] || 'Vishal-bhandary';
const REPO = 'composio-app-research';
const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, 'case-study.pdf');

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ colorScheme: 'light' });
  const page = await ctx.newPage();
  await page.goto('file://' + path.join(ROOT, 'index.html'), { waitUntil: 'networkidle' });

  await page.evaluate(({ owner, repo }) => {
    document.querySelectorAll('#tb tr').forEach((r) => { r.hidden = false; });
    const controls = document.querySelector('.controls');
    if (controls) controls.remove();
    const count = document.getElementById('count');
    if (count) count.textContent = 'all 100 shown';
    document.querySelectorAll('.scroll').forEach((s) => { s.style.overflow = 'visible'; });
    document.querySelectorAll('table.d').forEach((t) => { t.style.minWidth = '0'; });

    const bar = document.createElement('div');
    bar.setAttribute('style', [
      'background:#0D9488', 'color:#fff', 'padding:10px 16px',
      'font:13px ui-monospace,SFMono-Regular,Menlo,monospace',
      'display:flex', 'flex-wrap:wrap', 'gap:4px 28px', 'line-height:1.6',
    ].join(';'));
    bar.innerHTML =
      `<span><b>Live page</b> &nbsp;https://${owner.toLowerCase()}.github.io/${repo}/</span>` +
      `<span><b>Source repo</b> &nbsp;https://github.com/${owner}/${repo}</span>`;
    document.body.insertBefore(bar, document.body.firstChild);
  }, { owner: OWNER, repo: REPO });

  await page.emulateMedia({ media: 'screen', colorScheme: 'light' });
  await page.pdf({
    path: OUT, format: 'A3', printBackground: true,
    margin: { top: '10mm', bottom: '12mm', left: '10mm', right: '10mm' },
  });
  await browser.close();
  console.log('wrote ' + OUT);
})();
