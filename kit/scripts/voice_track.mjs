// 把每句配音照時間軸拼成一條音軌（不靠 Remotion 混音：它會把每個音檔補成整支影片長，196 句會塞爆 /tmp）
// 用法：node scripts/voice_track.mjs <composition> <輸出.wav>
import { bundle } from "@remotion/bundler";
import { selectComposition } from "@remotion/renderer";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const [compId, out] = process.argv.slice(2);
const root = path.resolve(import.meta.dirname, "..");
const serveUrl = await bundle({ entryPoint: path.join(root, "src/index.ts") });
const comp = await selectComposition({ serveUrl, id: compId, inputProps: {} });
const beats = comp.props.scenes.flatMap((sc) => sc.beats).filter((b) => b.hasAudio);
const plan = {
  total: comp.durationInFrames / comp.fps,
  clips: beats.map((b) => ({ file: path.join(root, "public/audio", compId, `${b.id}.wav`), start: b.start / comp.fps })),
};
const planFile = path.join(root, "out", `${compId}-voice-plan.json`);
fs.writeFileSync(planFile, JSON.stringify(plan));
execFileSync("uv", ["run", "-q", "--with", "numpy", "python3", path.join(root, "scripts/mix_voice.py"), planFile, out], { stdio: "inherit" });
