// 截靜態圖檢查畫面。預設在每句旁白結尾（畫面已經停好）各截一張，並做成縮圖總表。
// 用法：
//   node scripts/stills.mjs <composition> [--scene a,b] [--mode end|mid|both] [--frames 120,300] [--sheet-cols 4]
// 輸出：out/stills/<composition>/*.jpg、out/stills/<composition>/sheet-<scene>.jpg
import { bundle } from "@remotion/bundler";
import { openBrowser, renderStill, selectComposition } from "@remotion/renderer";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const args = process.argv.slice(2);
const compId = args[0];
const opt = (name, def) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : def;
};
const sceneFilter = opt("scene", "")?.split(",").filter(Boolean);
const mode = opt("mode", "end");
const explicit = opt("frames", "")?.split(",").filter(Boolean).map(Number);
const cols = Number(opt("sheet-cols", "4"));

const root = path.resolve(import.meta.dirname, "..");
const outDir = path.join(root, "out", "stills", compId);
fs.mkdirSync(outDir, { recursive: true });

const serveUrl = await bundle({ entryPoint: path.join(root, "src/index.ts") });
const browser = await openBrowser("chrome");
const comp = await selectComposition({ serveUrl, id: compId, inputProps: {}, puppeteerInstance: browser });
const scenes = comp.props.scenes;

const jobs = [];
if (explicit?.length) {
  for (const fr of explicit) jobs.push({ frame: fr, name: `f${String(fr).padStart(6, "0")}`, scene: "frames" });
} else {
  for (const sc of scenes) {
    if (sceneFilter?.length && !sceneFilter.includes(sc.id)) continue;
    for (const b of sc.beats) {
      const safe = b.id.replace(/[^a-zA-Z0-9_.-]/g, "_");
      if (mode === "end" || mode === "both") jobs.push({ frame: b.end - 3, name: `${safe}__end`, scene: sc.id });
      if (mode === "mid" || mode === "both")
        jobs.push({ frame: Math.round((b.start + b.end) / 2), name: `${safe}__mid`, scene: sc.id });
    }
  }
}

let done = 0;
const pool = 4;
const queue = [...jobs];
await Promise.all(
  Array.from({ length: pool }, async () => {
    while (queue.length) {
      const j = queue.shift();
      const output = path.join(outDir, `${j.name}.jpg`);
      await renderStill({
        composition: comp,
        serveUrl,
        output,
        frame: j.frame,
        imageFormat: "jpeg",
        jpegQuality: 88,
        puppeteerInstance: browser,
        inputProps: {},
      });
      j.output = output;
      done++;
      if (done % 10 === 0) console.log(`  ${done}/${jobs.length}`);
    }
  }),
);
await browser.close({ silent: true });

// 縮圖總表（每個場景一張）
const byScene = new Map();
for (const j of jobs) {
  if (!byScene.has(j.scene)) byScene.set(j.scene, []);
  byScene.get(j.scene).push(j);
}
for (const [scene, js] of byScene) {
  const list = js.map((j) => `${j.output}\t${j.name} @${j.frame}`).join("\n");
  const listFile = path.join(outDir, `.list-${scene}.txt`);
  fs.writeFileSync(listFile, list);
  execFileSync("uv", ["run", "-q", "--with", "pillow", "python3", path.join(root, "scripts/contact_sheet.py"), listFile,
    path.join(outDir, `sheet-${scene}.jpg`), String(cols)], { stdio: "inherit" });
}
console.log(`截了 ${jobs.length} 張，在 ${outDir}`);
console.log(`總長 ${comp.durationInFrames} 格 = ${(comp.durationInFrames / comp.fps / 60).toFixed(2)} 分鐘`);
