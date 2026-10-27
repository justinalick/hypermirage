// Copies the report page (report/) into dist/ under the path it is served from
// on justinalick.com, and writes the security headers. Refuses a page that
// would load anything from another origin: the site's privacy policy promises
// no third-party requests, so fonts and favicons come from justinalick.com.
// Run: node scripts/build.mjs
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";

const BASE = "/projects/hypermirage";
const out = `dist${BASE}`;

const html = readFileSync("report/index.html", "utf8");
const page = html.replace(/<!--[\s\S]*?-->/g, "").replace(/data:[^"')\s]+/g, "data:");
const fail = msg => { console.error(`build: ${msg}`); process.exit(1); };
if (/<script\b/i.test(page)) fail("the page must not contain scripts");
// Every URL the browser would fetch on its own: src/srcset, <link href> other
// than rel=canonical, and CSS url(). Plain <a href> links and meta tags are not fetches.
const fetched = [
  ...[...page.matchAll(/<link\b[^>]*>/gi)].map(m => m[0]).filter(t => !/rel=["']?canonical/i.test(t))
    .map(t => (t.match(/href=["']?([^"'\s>]+)/i) || [])[1]),
  ...[...page.matchAll(/\b(?:src|srcset)\s*=\s*["']?([^"'\s>]+)/gi)].map(m => m[1]),
  ...[...page.matchAll(/url\(\s*["']?([^"')]+)/gi)].map(m => m[1]),
].filter(Boolean);
const offsite = fetched.filter(u => /^(https?:)?\/\//i.test(u) && !/^https:\/\/justinalick\.com\//i.test(u));
if (offsite.length) fail(`third-party request in the page: ${[...new Set(offsite)].join(", ")}`);
for (const f of ["/favicon-48.png", "/favicon-96.png", "/apple-touch-icon.png"])
  if (!page.includes(`href="${f}"`)) fail(`missing favicon link ${f}`);
if (/claude\.ai/i.test(page)) fail("the page links claude.ai");
// Charts are files next to the page (charts/<name>-<content hash>.webp); every one the page uses must exist,
// and only those are copied.
const charts = [...new Set([...page.matchAll(/\bsrc="(charts\/[A-Za-z0-9_.-]+\.webp)"/g)].map(m => m[1]))];
if (!charts.length) fail("the page references no chart files");
const missing = charts.filter(c => !existsSync(`report/${c}`));
if (missing.length) fail(`chart files missing: ${missing.join(", ")}`);
const local = fetched.filter(u => !/^(data:|https?:|\/\/|#)/i.test(u) && !/^\//.test(u));
const unknown = local.filter(u => !charts.includes(u));
if (unknown.length) fail(`relative fetches that are not chart files: ${[...new Set(unknown)].join(", ")}`);

rmSync("dist", { recursive: true, force: true });
mkdirSync(out, { recursive: true });
cpSync("report/index.html", `${out}/index.html`);
mkdirSync(`${out}/charts`, { recursive: true });
for (const c of charts) cpSync(`report/${c}`, `${out}/${c}`);
cpSync("report/og-xyz-sp500-v7.png", `${out}/og-xyz-sp500-v7.png`);
cpSync("report/og-xyz-sp500-v6.png", `${out}/og-xyz-sp500-v6.png`);   // kept for previews already shared
cpSync("report/og-xyz-sp500-v5.png", `${out}/og-xyz-sp500-v5.png`);   // kept for previews already shared
cpSync("report/og-xyz-sp500-v4.png", `${out}/og-xyz-sp500-v4.png`);   // kept for previews already shared
cpSync("report/og-xyz-sp500-v3.png", `${out}/og-xyz-sp500-v3.png`);   // kept for previews already shared
cpSync("report/og-xyz-sp500-v2.png", `${out}/og-xyz-sp500-v2.png`);   // kept for previews already shared
cpSync("LICENSE", `${out}/LICENSE`);

// The page has no scripts. Styles are inline (one <style> block plus style
// attributes); charts are same-origin WebP files, small icons inline data: images.
const csp = [
  "default-src 'none'",
  "script-src 'none'",
  "style-src 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'none'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join("; ");

// no-transform on the page stops Cloudflare injecting its Web Analytics
// beacon into the HTML, whatever the dashboard setting is.
writeFileSync("dist/_headers", `${BASE}/*
  Content-Security-Policy: ${csp}
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  X-Frame-Options: DENY
  X-Robots-Tag: noindex
  Strict-Transport-Security: max-age=31536000

${BASE}/
  Cache-Control: public, max-age=0, must-revalidate, no-transform

${BASE}/charts/*
  Cache-Control: public, max-age=31536000, immutable

${BASE}/og-xyz-sp500-v7.png
  Cache-Control: public, max-age=3600

${BASE}/og-xyz-sp500-v6.png
  Cache-Control: public, max-age=3600

${BASE}/og-xyz-sp500-v5.png
  Cache-Control: public, max-age=3600

${BASE}/og-xyz-sp500-v4.png
  Cache-Control: public, max-age=3600

${BASE}/og-xyz-sp500-v3.png
  Cache-Control: public, max-age=3600

${BASE}/og-xyz-sp500-v2.png
  Cache-Control: public, max-age=3600
`);
console.log(`built ${out} (${(html.length / 1e6).toFixed(2)} MB page, ${charts.length} chart files)`);
