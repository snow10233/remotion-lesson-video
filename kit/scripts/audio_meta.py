"""把配音接回影片：
1. 依 map.json 把 wav/<段號>.wav 複製成 public/audio/<影片>/<旁白 id>.wav
2. 讀每句的實際長度，並找出音檔裡的停頓，把旁白裡的提示點（｜）對到停頓上
3. 寫出 src/videos/<影片>/audio.json，時間軸會自動重排

批次資料夾裡有 align.json（每句逐字的時間，來自 Qwen3-ForcedAligner）時，提示點直接用
「｜後面那個字開始的時間」，附近有靜音就貼齊靜音結束；沒有 align.json 才用停頓猜測。

用法：uv run -q --with numpy python3 scripts/audio_meta.py <影片 id> <批次資料夾> [<批次資料夾> ...]
  批次資料夾通常是 voice_qc.py 的輸出 tts/<影片>/final（有 align.json）；之後補做的句子是另一個批次的 final，放在後面。
後面的批次會覆蓋前面的同一句。旁白文字跟 map.json 對不上的句子會停下來報錯。
"""
import json
import re
import shutil
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
MARK = "｜"
CUE_LATE = 0.35


def units(s):
    return len(re.findall(r"[A-Za-z]+|[0-9]+|[㐀-鿿]", s.replace(MARK, "")))


DIG = "零一二三四五六七八九"


def zh_num(n):
    n = int(n)
    if n < 10: return DIG[n]
    if n < 20: return "十" + (DIG[n % 10] if n % 10 else "")
    if n < 100: return DIG[n // 10] + "十" + (DIG[n % 10] if n % 10 else "")
    return "".join(DIG[int(c)] for c in str(n))


def spoken_tokens(s):
    """旁白念出來的字（數字先換成中文，跟 TTS 稿的字一一對應）"""
    s = re.sub(r"(\d+)\.(\d+)", lambda m: zh_num(m.group(1)) + "點" + "".join(DIG[int(c)] for c in m.group(2)), s)
    s = re.sub(r"\d+", lambda m: zh_num(m.group()), s)
    return re.findall(r"[A-Za-z]+|[㐀-鿿]", s)


def align_by_words(marked, words, x, sr, dur):
    """用逐字時間放提示點：｜後面那個字開始的時間；前後 0.15 秒內有靜音就貼齊靜音結束"""
    parts = marked.split(MARK)
    if len(parts) == 1:
        return []
    total = len(spoken_tokens(marked.replace(MARK, "")))
    if total != len(words):
        raise ValueError(f"字數對不上：旁白 {total}、對齊 {len(words)}")
    _, _, ps = pauses(x, sr, min_len=0.08)
    cues, acc = [], 0
    for k in range(1, len(parts)):
        acc += len(spoken_tokens(parts[k - 1]))
        t = words[min(acc, len(words) - 1)][1]
        near = [b for a, b in ps if abs(b - t) <= 0.15]
        c = (min(near, key=lambda b: abs(b - t)) - 0.05) if near else t
        if cues:
            c = max(c, cues[-1] + 0.1)
        cues.append(round(min(c, dur - 0.2), 3))
    return cues


def load(path):
    with wave.open(str(path)) as w:
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
        ch = w.getnchannels()
        width = w.getsampwidth()
    dt = {2: np.int16, 4: np.int32}[width]
    x = np.frombuffer(raw, dtype=dt).astype(np.float32)
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x / np.iinfo(dt).max, sr


def pauses(x, sr, min_len=0.12):
    hop = int(sr * 0.01)
    frames = len(x) // hop
    rms = np.sqrt(np.mean(x[: frames * hop].reshape(frames, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    thr = max(db.max() - 38, -55)
    voiced = db > thr
    idx = np.where(voiced)[0]
    if len(idx) == 0:
        return 0, len(x) / sr, []
    s0, s1 = idx[0], idx[-1]
    out = []
    i = s0
    while i <= s1:
        if not voiced[i]:
            j = i
            while j <= s1 and not voiced[j]:
                j += 1
            if (j - i) * 0.01 >= min_len:
                out.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    return s0 * 0.01, (s1 + 1) * 0.01, out


def align(marked, x, sr, dur):
    """把提示點對到音檔的停頓。所有提示點一起考慮：順序遞增、總誤差最小；
    標點後面的提示點才能對到停頓，對不到的退回用字數比例估（往後挪一點）。"""
    parts = marked.split(MARK)
    if len(parts) == 1:
        return []
    total = max(1, units(marked))
    t0, t1, ps = pauses(x, sr)
    ests, punct = [], []
    acc = 0
    for k in range(1, len(parts)):
        acc += units(parts[k - 1])
        ests.append(t0 + (acc / total) * (t1 - t0))
        punct.append(bool(re.search(r"[，。：；、？！,.]\s*$", parts[k - 1])))
    SKIP = 1.3  # 提示點不對到停頓的代價（秒），要比可接受的估計誤差（1.2）大
    n, m = len(ests), len(ps)
    INF = float("inf")

    def cost(i, j):  # 第 i 個提示點對到第 j 個停頓
        a, b = ps[j]
        d = abs((a + b) / 2 - ests[i])
        return d if punct[i] and d < 1.2 else INF

    # f[i][j]：前 i 個提示點只用前 j 個停頓的最小代價（標準序列對齊）
    f = [[0.0] * (m + 1)] + [[INF] * (m + 1) for _ in range(n)]
    for i in range(1, n + 1):
        f[i][0] = f[i - 1][0] + SKIP
        for j in range(1, m + 1):
            f[i][j] = min(f[i][j - 1], f[i - 1][j] + SKIP, f[i - 1][j - 1] + cost(i - 1, j - 1))
    picks = [None] * n
    i, j = n, m
    while i > 0:
        if j > 0 and f[i][j] == f[i][j - 1]:
            j -= 1
        elif j > 0 and f[i][j] == f[i - 1][j - 1] + cost(i - 1, j - 1):
            picks[i - 1] = j - 1
            i, j = i - 1, j - 1
        else:
            i -= 1
    cues = []
    for k in range(n):
        if picks[k] is not None:
            c = ps[picks[k]][1] - 0.05
        else:
            c = min(ests[k] + CUE_LATE, dur - 0.2)
        if cues:
            c = max(c, cues[-1] + 0.1)
        cues.append(round(c, 3))
    return cues


def main():
    vid = sys.argv[1]
    batches = [Path(p) for p in sys.argv[2:]]
    narr = {}
    # 目前影片裡的旁白（含提示點），從主批次的 narration.json 讀（匯出時產生）
    for b in batches:
        nf = b / "narration.json"
        if nf.exists():
            for item in json.load(open(nf, encoding="utf-8")):
                narr[item["id"]] = item["marked"]
    dest = ROOT / "public" / "audio" / vid
    dest.mkdir(parents=True, exist_ok=True)
    meta_path = ROOT / "src" / "videos" / vid / "audio.json"
    meta = {}
    problems = []
    for b in batches:
        m = json.load(open(b / "map.json", encoding="utf-8"))
        af = b / "align.json"
        words_by_seg = json.load(open(af, encoding="utf-8")) if af.exists() else None
        for seg, info in m.items():
            wav = b / "wav" / f"{seg}.wav"
            if not wav.exists():
                problems.append(f"缺檔 {wav}")
                continue
            bid = info["id"]
            if bid not in narr:
                problems.append(f"{bid} 不在目前的旁白裡")
                continue
            cur = narr[bid].replace(MARK, "")
            if cur != info["text"]:
                problems.append(f"{bid} 旁白改過了，要重配：\n  配音時：{info['text']}\n  現在：  {cur}")
                continue
            shutil.copyfile(wav, dest / f"{bid}.wav")
            x, sr = load(wav)
            dur = len(x) / sr
            cues = None
            if words_by_seg is not None and words_by_seg.get(seg):
                try:
                    cues = align_by_words(narr[bid], words_by_seg[seg], x, sr, dur)
                except ValueError as e:  # 這句的逐字時間對不上旁白：退回停頓猜測
                    print(f"{bid}：{e}，改用停頓猜測")
            if cues is None:
                cues = align(narr[bid], x, sr, dur)
            meta[bid] = {"dur": round(dur, 3), "cues": cues}
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    json.dump(meta, open(meta_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"寫入 {len(meta)} 句到 {meta_path}")


if __name__ == "__main__":
    main()
