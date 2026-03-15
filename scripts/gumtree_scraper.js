#!/usr/bin/env node
// =============================================================
// gumtree_scraper.js — Gumtree Wanted ads scraper
// Uses curl-impersonate (Docker) to bypass TLS fingerprint detection
// =============================================================
// Usage:
//   node scripts/gumtree_scraper.js
//   node scripts/gumtree_scraper.js --max 20 --out /tmp/gumtree.json
//
// Requires: docker pull ghcr.io/lwthiker/curl-impersonate:0.6-chrome-slim-buster
//
// Output JSON per lead: { title, description, phone, location, price, adid, url, scraped_at }
// =============================================================

const { execSync } = require('child_process');
const fs            = require('fs');
const path          = require('path');

// ── CLI args ──────────────────────────────────────────────────
const args    = process.argv.slice(2);
const maxIdx  = args.indexOf('--max');
const outIdx  = args.indexOf('--out');
const maxAds  = maxIdx !== -1 ? parseInt(args[maxIdx + 1], 10) : 15;
const today   = new Date().toISOString().slice(0, 10);
const outPath = outIdx !== -1 ? args[outIdx + 1]
              : path.join(__dirname, '..', 'memory', `gumtree-leads-${today}.json`);

// ── curl-impersonate fetch ────────────────────────────────────
const DOCKER_IMAGE = 'lwthiker/curl-impersonate:0.6-chrome';

function curlFetch(url) {
  try {
    const cmd = [
      'docker run --rm',
      DOCKER_IMAGE,
      'curl_chrome110',
      '-s',
      '--max-time 20',
      '-H "Accept-Language: en-ZA,en;q=0.9"',
      '-H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"',
      `"${url}"`,
    ].join(' ');
    return execSync(cmd, { timeout: 30000 }).toString();
  } catch (err) {
    console.error(`[gumtree] fetch failed for ${url}: ${err.message}`);
    return null;
  }
}

// ── Parsers ───────────────────────────────────────────────────
function extractPhone(text) {
  if (!text) return null;
  const re = /(?:\+27|27|0)[6-8]\d[\s\-]?\d{3}[\s\-]?\d{4}/g;
  const match = text.match(re);
  return match ? match[0].replace(/[\s\-]/g, '') : null;
}

function extractAdLinks(html) {
  // Gumtree listing URLs: /a-{category}/{location}/{title}/{id}
  // Also match /s-user/ seller pages (skip) — only keep /a- pattern
  const re = /href="(https?:\/\/www\.gumtree\.co\.za\/a-[^"]+)"/g;
  const links = new Set();
  let m;
  while ((m = re.exec(html)) !== null) {
    const url = m[1].split('?')[0]; // strip query params
    if (!url.includes('/s-user/') && !url.includes('/s-my-gumtree/')) {
      links.add(url);
    }
  }
  return [...links];
}

function extractAdId(html, url) {
  // Try data-adid attribute first
  const adidMatch = html.match(/data-adid="(\d+)"/);
  if (adidMatch) return adidMatch[1];
  // Fall back to last segment of URL (usually the numeric ID)
  const parts = url.split('/').filter(Boolean);
  const last = parts[parts.length - 1];
  return /^\d+$/.test(last) ? last : null;
}

function extractField(html, patterns) {
  for (const re of patterns) {
    const m = html.match(re);
    if (m && m[1]) return m[1].trim();
  }
  return null;
}

function parseAdPage(html, url) {
  if (!html) return null;

  // Block check
  if (html.includes('The request is blocked') || html.includes('Access Denied')) {
    console.error(`[gumtree] block page detected: ${url}`);
    return null;
  }

  const title = extractField(html, [
    /<h1[^>]*>([^<]+)<\/h1>/,
    /<title>([^|<]+)/,
  ]);

  const description = extractField(html, [
    /data-q="ad-description"[^>]*>\s*<[^>]+>([^<]{20,})/,
    /class="[^"]*description[^"]*"[^>]*>([^<]{20,})/,
  ]);

  const location = extractField(html, [
    /data-q="ad-location"[^>]*>([^<]+)</,
    /class="[^"]*location[^"]*"[^>]*>([^<]+)</,
  ]);

  const price = extractField(html, [
    /data-q="ad-price"[^>]*>([^<]+)</,
    /class="[^"]*price[^"]*"[^>]*>(R[\d\s,]+)</,
  ]);

  // Phone: check tel: links, data-phone, then regex on full text
  const telMatch   = html.match(/href="tel:([^"]+)"/);
  const dataPhone  = html.match(/data-phone="([^"]+)"/);
  const phone      = (telMatch && telMatch[1]) ||
                     (dataPhone && dataPhone[1]) ||
                     extractPhone(description) ||
                     extractPhone(html.slice(0, 5000)); // scan top of page only

  const adid = extractAdId(html, url);

  return { title, description, phone, location, price, adid, url, scraped_at: new Date().toISOString() };
}

// ── Search URLs ───────────────────────────────────────────────
const SEARCH_URLS = [
  'https://www.gumtree.co.za/s-wanted-ads/car-tracker/v1c9110l0p1',
  'https://www.gumtree.co.za/s-wanted-ads/vehicle-tracker/v1c9110l0p1',
  'https://www.gumtree.co.za/s-wanted-ads/gps-tracker/v1c9110l0p1',
];

// ── Main ──────────────────────────────────────────────────────
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  console.error(`[gumtree] Starting — max ${maxAds} ads → ${outPath}`);

  const results  = [];
  const seenUrls = new Set();
  const seenAdIds = new Set();

  for (const searchUrl of SEARCH_URLS) {
    if (results.length >= maxAds) break;

    console.error(`[gumtree] Fetching listing: ${searchUrl}`);
    const listHtml = curlFetch(searchUrl);
    if (!listHtml) continue;

    if (listHtml.includes('The request is blocked')) {
      console.error(`[gumtree] BLOCKED on listing page — curl-impersonate may need refresh`);
      continue;
    }

    const adLinks = extractAdLinks(listHtml);
    console.error(`[gumtree] Found ${adLinks.length} ad links`);

    for (const adUrl of adLinks) {
      if (results.length >= maxAds) break;
      if (seenUrls.has(adUrl)) continue;
      seenUrls.add(adUrl);

      await sleep(800 + Math.random() * 1200);

      console.error(`[gumtree] Fetching ad: ${adUrl}`);
      const adHtml = curlFetch(adUrl);
      const ad = parseAdPage(adHtml, adUrl);

      if (!ad) continue;
      if (ad.adid && seenAdIds.has(ad.adid)) continue;
      if (ad.adid) seenAdIds.add(ad.adid);

      results.push(ad);
      console.error(`[gumtree] ✓ "${ad.title}" | phone: ${ad.phone || 'none'} | loc: ${ad.location || '?'}`);
    }
  }

  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2));
  console.error(`[gumtree] Done — ${results.length} ads → ${outPath}`);
  console.log(JSON.stringify({ ok: true, count: results.length, out: outPath, leads: results }));
}

main().catch(err => {
  console.error(`[gumtree] Fatal: ${err.message}`);
  console.log(JSON.stringify({ ok: false, error: err.message }));
  process.exit(1);
});
