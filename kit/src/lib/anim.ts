import { Easing, interpolate } from "remotion";

export const FPS = 60;
// 秒 → 格數。程式裡的時間都用秒來想。
export const s = (sec: number) => Math.round(sec * FPS);

const easeOut = Easing.bezier(0.22, 1, 0.36, 1);
const easeInOut = Easing.bezier(0.45, 0, 0.25, 1);

// 從 at 開始、持續 dur 格，回傳 0→1
export const prog = (frame: number, at: number, dur = s(0.45), ease: "out" | "inOut" = "out") =>
  interpolate(frame, [at, at + Math.max(1, dur)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: ease === "out" ? easeOut : easeInOut,
  });

// 在 [from, to) 之間顯示，前後淡入淡出
export const window = (frame: number, from: number, to: number, fade = s(0.3)) => {
  if (to <= from) return 0;
  return Math.min(prog(frame, from, fade), 1 - prog(frame, to - fade, fade));
};

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
