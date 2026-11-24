// 一支影片的進入點範例（新影片複製這個資料夾改名，再到 Root.tsx 加 composition）。
// 場景 = { id, beats, Component }；beats 是旁白，一句一個 { key, text, after?, min? }，text 裡用「｜」標動作點。
// 場景元件裡用 useCues() 取得時間：cue("句子 key", 第幾個｜) 回傳格數（相對場景開頭），start/end 是那句的頭尾。
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { LessonVideo, useCues, type VideoDef } from "../../lib/LessonVideo";
import { computeTimeline, type AudioMeta, type SceneTiming } from "../../lib/timeline";
import { FPS, prog } from "../../lib/anim";
import audio from "./audio.json"; // 還沒配音時內容是 {}

const Hello: React.FC = () => {
  const frame = useCurrentFrame();
  const { cue } = useCues();
  return <AbsoluteFill style={{ color: "white", fontSize: 80, opacity: prog(frame, cue("hi", 1)) }}>Hello</AbsoluteFill>;
};

export const example: VideoDef = {
  id: "_example",
  scenes: [{ id: "intro", beats: [{ key: "hi", text: "大家好，｜這是一個範例。" }], Component: Hello }],
  Background: () => <AbsoluteFill style={{ background: "#111" }} />,
  Subtitle: ({ text, opacity }) => (
    <div style={{ position: "absolute", bottom: 40, width: "100%", textAlign: "center", color: "white", fontSize: 40, opacity }}>
      {text}
    </div>
  ),
};
export const exampleTimeline = () => computeTimeline(example.scenes, audio as AudioMeta, FPS);
export const Example: React.FC<{ scenes: SceneTiming[] }> = ({ scenes }) => <LessonVideo video={example} scenes={scenes} />;
