import fs from "node:fs/promises";
import Module, { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
if (process.env.STARBRIDGE_NODE_MODULES) {
  process.env.NODE_PATH = [process.env.STARBRIDGE_NODE_MODULES, process.env.NODE_PATH]
    .filter(Boolean)
    .join(path.delimiter);
  Module._initPaths();
}

let sharp;
try {
  sharp = require("sharp");
} catch (error) {
  throw new Error(
    "Brand export requires the root dev dependency 'sharp'. Run npm install, then npm.cmd run brand:build.",
    { cause: error },
  );
}

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..", "..");
const brandDir = path.join(repoRoot, "brand");
const symbolPath = path.join(brandDir, "starbridge-symbol.svg");
const exportDir = path.join(brandDir, "exports");
const iconDir = path.join(exportDir, "icons");
const tauriIconDir = path.join(repoRoot, "apps", "starbridge-desktop", "src-tauri", "icons");
const desktopAssetDir = path.join(repoRoot, "apps", "starbridge-desktop", "src", "assets");
const sizes = [16, 24, 32, 48, 64, 128, 256, 512];

const symbol = await fs.readFile(symbolPath, "utf8");
const symbolBody = symbol
  .replace(/^.*?<svg[^>]*>/s, "")
  .replace(/<\/svg>\s*$/s, "")
  .replace(/\s*<title[\s\S]*?<\/title>/, "")
  .replace(/\s*<desc[\s\S]*?<\/desc>/, "")
  .trim();

const xml = (viewBox, title, body) => `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" role="img" aria-label="${title}">
  <title>${title}</title>
  ${body}
</svg>
`;

const escapedWordmark = `
  <text x="4" y="34" fill="#101828" font-family="Segoe UI Variable, Segoe UI, Arial, sans-serif" font-size="31" font-weight="720" letter-spacing="-0.7">StarBridge</text>
  <text x="5" y="51" fill="#667085" font-family="Microsoft YaHei UI, PingFang SC, sans-serif" font-size="10.5" font-weight="600" letter-spacing="1.4">本地创意工作台</text>`;

const embedSymbol = (x, y, scale = 1) =>
  `<g transform="translate(${x} ${y}) scale(${scale})">${symbolBody}</g>`;

const wordmark = xml("0 0 220 58", "StarBridge 本地创意工作台", escapedWordmark);
const horizontal = xml(
  "0 0 360 80",
  "StarBridge 本地创意工作台",
  `${embedSymbol(4, 8, 1)}
  <text x="84" y="39" fill="#101828" font-family="Segoe UI Variable, Segoe UI, Arial, sans-serif" font-size="31" font-weight="720" letter-spacing="-0.7">StarBridge</text>
  <text x="85" y="58" fill="#667085" font-family="Microsoft YaHei UI, PingFang SC, sans-serif" font-size="11" font-weight="600" letter-spacing="1.5">本地创意工作台</text>`,
);
const compact = xml(
  "0 0 120 108",
  "StarBridge",
  `${embedSymbol(28, 0, 1)}
  <text x="60" y="88" text-anchor="middle" fill="#101828" font-family="Segoe UI Variable, Segoe UI, Arial, sans-serif" font-size="19" font-weight="720" letter-spacing="-0.4">StarBridge</text>
  <text x="60" y="103" text-anchor="middle" fill="#667085" font-family="Microsoft YaHei UI, PingFang SC, sans-serif" font-size="8.5" font-weight="600">本地创意工作台</text>`,
);
const grid = xml(
  "0 0 640 320",
  "StarBridge icon grid",
  `<rect width="640" height="320" fill="#F6F8FC"/>
  <text x="32" y="38" fill="#101828" font-family="Segoe UI, sans-serif" font-size="20" font-weight="700">StarBridge icon grid</text>
  <text x="32" y="62" fill="#667085" font-family="Segoe UI, sans-serif" font-size="12">single source: starbridge-symbol.svg</text>
  <rect x="32" y="88" width="248" height="184" rx="14" fill="#FFFFFF" stroke="#DDE3EC"/>
  <rect x="304" y="88" width="304" height="184" rx="14" fill="#0B1220"/>
  ${embedSymbol(64, 116, 2)}
  ${embedSymbol(336, 116, 2)}
  <g opacity="0.25" stroke="#2563EB" stroke-width="1">
    <path d="M64 116H192M64 148H192M64 180H192M64 212H192M64 244H192"/>
    <path d="M64 116V244M96 116V244M128 116V244M160 116V244M192 116V244"/>
  </g>
  <text x="208" y="260" fill="#667085" font-family="Segoe UI, sans-serif" font-size="11" text-anchor="end">light</text>
  <text x="576" y="260" fill="#A8B4C5" font-family="Segoe UI, sans-serif" font-size="11" text-anchor="end">dark</text>`,
);

await fs.mkdir(iconDir, { recursive: true });
await fs.mkdir(tauriIconDir, { recursive: true });
await fs.mkdir(desktopAssetDir, { recursive: true });
await fs.writeFile(path.join(brandDir, "starbridge-wordmark.svg"), wordmark);
await fs.writeFile(path.join(brandDir, "starbridge-lockup-horizontal.svg"), horizontal);
await fs.writeFile(path.join(brandDir, "starbridge-lockup-compact.svg"), compact);
await fs.writeFile(path.join(brandDir, "starbridge-icon-grid.svg"), grid);
await fs.writeFile(path.join(brandDir, "starbridge-readme.svg"), horizontal);
await fs.writeFile(path.join(desktopAssetDir, "starbridge-symbol.svg"), symbol);

const pngs = new Map();
for (const size of sizes) {
  const png = await sharp(Buffer.from(symbol))
    .resize(size, size)
    .png({ compressionLevel: 9, adaptiveFiltering: false, palette: false })
    .toBuffer();
  pngs.set(size, png);
  await fs.writeFile(path.join(iconDir, `starbridge-${size}.png`), png);
}

function makeIco(entries) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(entries.length, 4);
  const directory = Buffer.alloc(entries.length * 16);
  let offset = 6 + directory.length;
  entries.forEach(({ size, png }, index) => {
    const base = index * 16;
    directory.writeUInt8(size === 256 ? 0 : size, base);
    directory.writeUInt8(size === 256 ? 0 : size, base + 1);
    directory.writeUInt8(0, base + 2);
    directory.writeUInt8(0, base + 3);
    directory.writeUInt16LE(1, base + 4);
    directory.writeUInt16LE(32, base + 6);
    directory.writeUInt32LE(png.length, base + 8);
    directory.writeUInt32LE(offset, base + 12);
    offset += png.length;
  });
  return Buffer.concat([header, directory, ...entries.map(({ png }) => png)]);
}

const icoSizes = [16, 24, 32, 48, 64, 128, 256];
const ico = makeIco(icoSizes.map((size) => ({ size, png: pngs.get(size) })));
await fs.writeFile(path.join(exportDir, "starbridge-icon.ico"), ico);
await fs.writeFile(path.join(exportDir, "favicon-32.png"), pngs.get(32));
await fs.writeFile(path.join(tauriIconDir, "icon.ico"), ico);
await fs.writeFile(path.join(tauriIconDir, "icon.png"), pngs.get(512));
await fs.writeFile(path.join(tauriIconDir, "32x32.png"), pngs.get(32));
await fs.writeFile(path.join(tauriIconDir, "128x128.png"), pngs.get(128));
await fs.writeFile(path.join(tauriIconDir, "128x128@2x.png"), pngs.get(256));

console.log(
  JSON.stringify(
    {
      source: path.relative(repoRoot, symbolPath),
      pngSizes: sizes,
      icoSizes,
      output: path.relative(repoRoot, exportDir),
      tauriIcons: path.relative(repoRoot, tauriIconDir),
    },
    null,
    2,
  ),
);
