// Copies the report page (report/) into dist/ under the path it is served from
// on justinalick.com, and writes the security headers. Refuses a page that
// would load anything from another origin: the site's privacy policy promises
// no third-party requests, so fonts and favicons come from justinalick.com.
// Run: node scripts/build.mjs
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";

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

rmSync("dist", { recursive: true, force: true });
mkdirSync(out, { recursive: true });
cpSync("report/index.html", `${out}/index.html`);
cpSync("report/og-xyz-sp500.png", `${out}/og-xyz-sp500.png`);
cpSync("LICENSE", `${out}/LICENSE`);

// The page has no scripts. Styles are inline (one <style> block plus style
// attributes); charts are inline data: images.
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

${BASE}/
  Cache-Control: public, max-age=0, must-revalidate, no-transform

${BASE}/og-xyz-sp500.png
  Cache-Control: public, max-age=3600
`);
console.log(`built ${out} (${(html.length / 1e6).toFixed(1)} MB page)`);
