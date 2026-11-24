import React from "react";
import { Composition } from "remotion";
import { FPS } from "./lib/anim";
import type { SceneTiming } from "./lib/timeline";

// 每支影片一個 composition。props.scenes 就是時間軸（calculateMetadata 從旁白和 audio.json 算出來），
// 截圖、匯出旁白、拼配音的腳本都從這裡讀。新增影片時照這個樣子加一個：
//
// import { MyVideo, myVideoTimeline } from "./videos/my-video";
// <Composition id="my-video" component={MyVideo} fps={FPS} width={1920} height={1080} durationInFrames={1}
//   defaultProps={{ scenes: [] as SceneTiming[] }}
//   calculateMetadata={() => { const tl = myVideoTimeline(); return { durationInFrames: tl.total, props: { scenes: tl.scenes } }; }} />
export const RemotionRoot: React.FC = () => <></>;
