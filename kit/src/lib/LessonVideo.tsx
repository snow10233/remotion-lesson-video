import React, { createContext, useContext } from "react";
import { AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame } from "remotion";
import { FontGate } from "./FontGate";
import { prog, s } from "./anim";
import type { Beat, SceneTiming } from "./timeline";

export type SceneDef = {
  id: string;
  beats: Beat[];
  Component: React.FC;
};

export type VideoDef = {
  id: string; // 也是音檔資料夾名稱：public/audio/<id>/<beat id>.wav
  scenes: SceneDef[];
  Background: React.FC;
  Subtitle: React.FC<{ text: string; opacity: number }>;
};

// ---- 場景內取得提示點時間（相對場景開頭的格數）----

type SceneCtx = { timing: SceneTiming };
const Ctx = createContext<SceneCtx | null>(null);

export const useCues = () => {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useCues 只能在場景裡用");
  const { timing } = ctx;
  const get = (key: string) => {
    const b = timing.beats.find((x) => x.key === key);
    if (!b) throw new Error(`場景 ${timing.id} 沒有旁白 ${key}`);
    return b;
  };
  const rel = (f: number) => f - timing.start;
  const cue = (key: string, k = 0) => {
    const b = get(key);
    if (k >= b.cues.length) throw new Error(`旁白 ${b.id} 只有 ${b.cues.length - 1} 個提示點，要第 ${k} 個`);
    return rel(b.cues[k]);
  };
  return {
    cue,
    start: (key: string) => rel(get(key).start),
    end: (key: string) => rel(get(key).end),
    sceneEnd: timing.end - timing.start,
    beatKeys: timing.beats.map((b) => b.key),
  };
};

// ---- 整支影片 ----

export const LessonVideo: React.FC<{ video: VideoDef; scenes: SceneTiming[] }> = ({ video, scenes }) => {
  const frame = useCurrentFrame();
  const { Background, Subtitle } = video;
  const allBeats = scenes.flatMap((sc) => sc.beats);
  // 字幕：配音在念的時候顯示
  const cur = allBeats.find((b) => frame >= b.start && frame < b.end);
  let sub: React.ReactNode = null;
  if (cur) {
    const showEnd = Math.min(cur.end, cur.start + cur.audioFrames + s(0.25));
    const op = Math.min(prog(frame, cur.start, s(0.15)), 1 - prog(frame, showEnd - s(0.15), s(0.15)));
    if (op > 0) sub = <Subtitle text={cur.text} opacity={op} />;
  }
  return (
    <FontGate>
      <AbsoluteFill>
        <Background />
        {scenes.map((sc) => {
          const def = video.scenes.find((d) => d.id === sc.id);
          if (!def) throw new Error(`找不到場景 ${sc.id}`);
          const { Component } = def;
          return (
            <Sequence key={sc.id} from={sc.start} durationInFrames={sc.end - sc.start} name={sc.id}>
              <SceneFade length={sc.end - sc.start}>
                <Ctx.Provider value={{ timing: sc }}>
                  <Component />
                </Ctx.Provider>
              </SceneFade>
            </Sequence>
          );
        })}
        {allBeats
          .filter((b) => b.hasAudio)
          .map((b) => (
            <Sequence key={b.id} from={b.start} durationInFrames={b.audioFrames + s(0.2)} name={`voice ${b.id}`}>
              <Audio src={staticFile(`audio/${video.id}/${b.id}.wav`)} />
            </Sequence>
          ))}
        {sub}
      </AbsoluteFill>
    </FontGate>
  );
};

const SceneFade: React.FC<{ length: number; children: React.ReactNode }> = ({ length, children }) => {
  const f = useCurrentFrame();
  const op = Math.min(prog(f, 0, s(0.35)), 1 - prog(f, length - s(0.35), s(0.35)));
  return <AbsoluteFill style={{ opacity: op }}>{children}</AbsoluteFill>;
};
