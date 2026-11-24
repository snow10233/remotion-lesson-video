// 共用時間軸：旁白是整支影片的時間軸。
// 每句旁白（beat）有固定 id，音檔用這個 id 命名。
// 句子裡可以放「｜」當作動作的提示點（cue），字幕和配音都看不到它。

export const CUE_MARK = "｜";
export const GAP_SEC = 0.45; // 句子之間的空檔
export const SPEECH_RATE = 4; // 沒有音檔時估的語速：每秒 4 個單位
export const SCENE_LEAD_SEC = 0.6; // 場景開始到第一句之前
export const SCENE_TAIL_SEC = 0.9; // 最後一句之後到場景結束
export const CUE_LATE_SEC = 0.35; // 用比例估提示點時，實測普遍偏早，往後挪一點

export type Beat = {
  key: string; // 場景內的短名，完整 id 是 `${scene.id}.${key}`
  text: string; // 旁白（可含 ｜）
  after?: number; // 最後一個提示點之後至少要留幾秒給動畫
  min?: number; // 這句最少要幾秒
};

export type AudioMeta = Record<string, { dur: number; cues?: number[] }>;

export type BeatTiming = {
  id: string;
  key: string;
  text: string; // 不含 ｜
  marked: string;
  start: number; // 相對整支影片的格數
  end: number;
  audioFrames: number;
  hasAudio: boolean;
  cues: number[]; // 相對整支影片的格數；cues[0] = start
};

export type SceneTiming = {
  id: string;
  start: number;
  end: number;
  beats: BeatTiming[];
};

export const stripMarks = (s: string) => s.split(CUE_MARK).join("");

// 中文字、英文單字、數字各算一個單位
export const countUnits = (s: string) => {
  const t = stripMarks(s);
  const words = t.match(/[A-Za-z]+|[0-9]+|[㐀-鿿]/g);
  return words ? words.length : 0;
};

export const estimateSec = (s: string) => countUnits(s) / SPEECH_RATE + 0.25;

export type SceneInput = { id: string; beats: Beat[] };

export function computeTimeline(
  scenes: SceneInput[],
  audio: AudioMeta,
  fps: number,
): { scenes: SceneTiming[]; total: number } {
  const sec = (s: number) => Math.round(s * fps);
  let cursor = 0;
  const out: SceneTiming[] = [];
  for (const sc of scenes) {
    const sceneStart = cursor;
    cursor += sec(SCENE_LEAD_SEC);
    const beats: BeatTiming[] = [];
    for (const b of sc.beats) {
      const id = `${sc.id}.${b.key}`;
      const meta = audio[id];
      const dur = meta ? meta.dur : estimateSec(b.text);
      const parts = b.text.split(CUE_MARK);
      const total = Math.max(1, countUnits(b.text));
      const cueSecs: number[] = [0];
      let acc = 0;
      for (let i = 1; i < parts.length; i++) {
        acc += countUnits(parts[i - 1]);
        const aligned = meta?.cues?.[i - 1];
        if (aligned !== undefined && aligned !== null) {
          cueSecs.push(aligned);
        } else {
          const est = (acc / total) * dur + (meta ? CUE_LATE_SEC : 0);
          cueSecs.push(Math.min(est, Math.max(0, dur - 0.2)));
        }
      }
      const lastCue = cueSecs[cueSecs.length - 1];
      const lenSec = Math.max(dur + GAP_SEC, lastCue + (b.after ?? 1.0), b.min ?? 0);
      const start = cursor;
      const end = start + sec(lenSec);
      beats.push({
        id,
        key: b.key,
        text: stripMarks(b.text),
        marked: b.text,
        start,
        end,
        audioFrames: sec(dur),
        hasAudio: !!meta,
        cues: cueSecs.map((c) => start + sec(c)),
      });
      cursor = end;
    }
    cursor += sec(SCENE_TAIL_SEC);
    out.push({ id: sc.id, start: sceneStart, end: cursor, beats });
  }
  return { scenes: out, total: cursor };
}
