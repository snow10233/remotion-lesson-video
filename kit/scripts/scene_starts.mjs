// 印出每個場景開始的秒數（不含第一個），給 add_music.py 的 --chimes 用
import { bundle } from "@remotion/bundler";
import { selectComposition } from "@remotion/renderer";
import path from "node:path";
const root = path.resolve(import.meta.dirname, "..");
const serveUrl = await bundle({ entryPoint: path.join(root, "src/index.ts") });
const comp = await selectComposition({ serveUrl, id: process.argv[2], inputProps: {} });
console.log(comp.props.scenes.slice(1).map((sc) => (sc.start / comp.fps).toFixed(2)).join(","));
