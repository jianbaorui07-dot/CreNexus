import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { navigation, pages } from "../src/site-content.mjs";

const siteRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(siteRoot, "../..");
const dist = resolve(siteRoot, "dist");
const tokens = JSON.parse(await readFile(resolve(repoRoot, "brand/brand-tokens.json"), "utf8"));
const sourceCss = await readFile(resolve(siteRoot, "src/styles.css"), "utf8");
const cssVariables = `:root {\n  --font-sans: ${tokens.fontFamily.ui};\n  --color-background: ${tokens.color.background};\n  --color-surface: ${tokens.color.surface};\n  --color-text: ${tokens.color.text};\n  --color-muted: ${tokens.color.textMuted};\n  --color-primary: ${tokens.color.primary};\n  --color-primary-soft: ${tokens.color.primarySoft};\n  --color-navy: ${tokens.color.navy};\n  --color-accent: ${tokens.color.cyan};\n  --color-border: ${tokens.color.border};\n}\n`;
const escapeHtml = (value) => value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");

function renderPage(route, page) {
  const nav = navigation.map(([href, label]) => `<a href="${href}"${href === route ? ' aria-current="page"' : ""}>${label}</a>`).join("");
  const actions = (page.actions ?? []).map(([href, label]) => `<a class="button" href="${href}">${escapeHtml(label)}</a>`).join("");
  const sections = page.sections.map(([title, body], index) => `<article class="section-card"><span>0${index + 1}</span><h2>${escapeHtml(title)}</h2><p>${escapeHtml(body)}</p></article>`).join("");
  return `<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><meta name="description" content="${escapeHtml(page.intro)}"><title>${escapeHtml(page.title)} · StarBridge</title><link rel="icon" href="/assets/favicon-32.png" type="image/png"><link rel="stylesheet" href="/assets/site.css"></head><body><a class="skip-link" href="#main">跳到主要内容</a><header class="site-header"><div class="header-inner"><a class="brand" href="/"><img src="/assets/starbridge-symbol.svg" alt=""><span>StarBridge<small>本地创意工作台</small></span></a><nav aria-label="主要导航">${nav}<a class="download-link" href="/download">下载</a></nav></div></header><main id="main"><section class="hero"><div class="hero-content"><p class="eyebrow">${escapeHtml(page.eyebrow)}</p><h1>${escapeHtml(page.title)}</h1><p class="intro">${escapeHtml(page.intro)}</p>${actions ? `<div class="actions">${actions}</div>` : ""}</div></section><section class="section-grid" aria-label="页面要点">${sections}</section></main><footer><div class="footer-inner"><span>StarBridge · 本地创意工作台</span><span>未发布官网候选 · 不上传用户素材</span></div></footer><script src="/assets/site.js"></script></body></html>`;
}

await rm(dist, { recursive: true, force: true });
await mkdir(resolve(dist, "assets"), { recursive: true });
await writeFile(resolve(dist, "assets/site.css"), cssVariables + sourceCss, "utf8");
await cp(resolve(siteRoot, "src/app.js"), resolve(dist, "assets/site.js"));
await cp(resolve(repoRoot, "brand/starbridge-symbol.svg"), resolve(dist, "assets/starbridge-symbol.svg"));
await cp(resolve(repoRoot, "brand/exports/favicon-32.png"), resolve(dist, "assets/favicon-32.png"));
for (const [route, page] of Object.entries(pages)) {
  const target = route === "/" ? resolve(dist, "index.html") : resolve(dist, route.slice(1), "index.html");
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, renderPage(route, page), "utf8");
}
console.log(`Built ${Object.keys(pages).length} StarBridge site routes.`);
