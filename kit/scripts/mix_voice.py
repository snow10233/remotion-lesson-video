"""依計畫把配音片段放到正確時間，輸出一條單聲道 wav（取樣率跟配音一樣，22050 Hz）。用法：mix_voice.py <plan.json> <out.wav>"""
import json, sys, wave
import numpy as np

plan = json.load(open(sys.argv[1]))
SR = 22050
track = np.zeros(int(plan["total"] * SR) + SR, dtype=np.float32)
for c in plan["clips"]:
    with wave.open(c["file"]) as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    # 取樣率不同才內插（IndexTTS2 的輸出都是 22050，通常不會用到）
    if sr == SR:
        y = x
    else:
        t = np.arange(int(len(x) * SR / sr)) * sr / SR
        y = np.interp(t, np.arange(len(x)), x).astype(np.float32)
    i = int(round(c["start"] * SR))
    track[i : i + len(y)] += y
track = track[: int(plan["total"] * SR)]
peak = np.abs(track).max()
if peak > 0.99:
    track *= 0.99 / peak
with wave.open(sys.argv[2], "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((track * 32767).astype(np.int16).tobytes())
print(f"配音音軌 {len(plan['clips'])} 句，{len(track)/SR:.2f} 秒 → {sys.argv[2]}")
