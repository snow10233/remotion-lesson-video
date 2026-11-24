// 匯出逐字稿：tts/<composition>/src.txt、map.json（段號 → 旁白 id 和文字）、narration.json（含提示點）
// 用法：node scripts/export_tts.mjs <composition> [輸出資料夾，預設 tts/<composition>]
// src.txt 第一段是標題（不會念），用 composition id。
import { bundle } from "@remotion/bundler";
import { selectComposition } from "@remotion/renderer";
import fs from "node:fs";
import path from "node:path";

const compId = process.argv[2];
const root = path.resolve(import.meta.dirname, "..");
const outDir = path.resolve(process.argv[3] ?? path.join(root, "tts", compId));
fs.mkdirSync(outDir, { recursive: true });
const serveUrl = await bundle({ entryPoint: path.join(root, "src/index.ts") });
const comp = await selectComposition({ serveUrl, id: compId, inputProps: {} });
const beats = comp.props.scenes.flatMap((sc) => sc.beats);
fs.writeFileSync(path.join(outDir, "src.txt"), [compId, ...beats.map((b) => b.text)].join("\n\n") + "\n");
const map = {};
beats.forEach((b, i) => (map[String(i + 1).padStart(3, "0")] = { id: b.id, text: b.text }));
fs.writeFileSync(path.join(outDir, "map.json"), JSON.stringify(map, null, 2));
fs.writeFileSync(
  path.join(outDir, "narration.json"),
  JSON.stringify(beats.map((b) => ({ id: b.id, marked: b.marked })), null, 2),
);
console.log(`匯出 ${beats.length} 句到 ${outDir}`);
