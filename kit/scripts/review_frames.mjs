// 截出給審核子代理看的圖：每個動作點（｜）之後 0.5 秒一張、每句結尾一張，並寫出每張圖當下「念到哪」。
// 用法：node scripts/review_frames.mjs <composition> [--scene a,b] [--cues-only] [--moved <舊的 audio.json>] [--out 資料夾]
//   --cues-only：只截動作點，不截句尾（第一次接上配音後用：句尾的版面做畫面時已經審過）
//   --moved：只截跟舊時間相比移動超過 0.3 秒的動作點（重配或改對時之後用）
// 輸出：<out，預設 out/review/<composition>>/<格數>.jpg 和 review.json
//   review.json 每筆：{ image, frame, beat, kind: "cue"|"end", said, next, sentence }
//   said＝截圖時已經念完的部分，next＝接著要念的部分（kind=end 時 next 為空）
import { bundle } from "@remotion/bundler";
import { openBrowser, renderStill, selectComposition } from "@remotion/renderer";
import fs from "node:fs";
import path from "node:path";

const args = process.argv.slice(2);
const compId = args[0];
const opt = (name, def) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : def;
};
const sceneFilter = opt("scene", "").split(",").filter(Boolean);
const movedFrom = opt("moved", "");
const cuesOnly = args.includes("--cues-only");
const root = path.resolve(import.meta.dirname, "..");
const outDir = path.resolve(opt("out", path.join(root, "out", "review", compId)));
fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });
const old = movedFrom ? JSON.parse(fs.readFileSync(movedFrom, "utf-8")) : null;

const serveUrl = await bundle({ entryPoint: path.join(root, "src/index.ts") });
const browser = await openBrowser("chrome");
const comp = await selectComposition({ serveUrl, id: compId, inputProps: {}, puppeteerInstance: browser });
const fps = comp.fps;
const jobs = [];
for (const sc of comp.props.scenes) {
  if (sceneFilter.length && !sceneFilter.includes(sc.id)) continue;
  for (const b of sc.beats) {
    const parts = b.marked.split("｜");
    b.cues.forEach((f, k) => {
      if (k === 0 && !old) return; // 句子開頭由前一句的結尾那張涵蓋
      if (old) {
        const prev = old[b.id]?.cues?.[k - 1];
        if (k === 0 || prev === undefined || Math.abs(prev - (f - b.start) / fps) <= 0.3) return;
      }
      jobs.push({ frame: Math.min(f + Math.round(0.5 * fps), b.end - 3), beat: b.id, kind: "cue",
        said: parts.slice(0, k).join(""), next: parts.slice(k).join(""), sentence: b.text });
    });
    if (!old && !cuesOnly) jobs.push({ frame: b.end - 3, beat: b.id, kind: "end", said: b.text, next: "", sentence: b.text });
  }
}

let done = 0;
const queue = [...jobs];
await Promise.all(
  Array.from({ length: 4 }, async () => {
    while (queue.length) {
      const j = queue.shift();
      j.image = path.join(outDir, `${String(j.frame).padStart(6, "0")}.jpg`);
      await renderStill({ composition: comp, serveUrl, output: j.image, frame: j.frame, imageFormat: "jpeg",
        jpegQuality: 88, puppeteerInstance: browser, inputProps: {} });
      if (++done % 20 === 0) console.log(`  ${done}/${jobs.length}`);
    }
  }),
);
await browser.close({ silent: true });
jobs.sort((a, b) => a.frame - b.frame);
fs.writeFileSync(path.join(outDir, "review.json"), JSON.stringify(jobs, null, 1));
console.log(`截了 ${jobs.length} 張，清單在 ${path.join(outDir, "review.json")}`);
