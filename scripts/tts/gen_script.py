"""在 Colab VM 上用 IndexTTS2 把 TTS 稿逐段生成語音。由 launch.py 啟動，不用自己執行。
用法（在 /content/index-tts 底下）：uv run python gen_script.py <TTS稿> <輸出資料夾>
- TTS 稿格式：每行 `段號<TAB>內容`（段號三位數），遇到 `## ` 開頭的行就停。
- 輸出 <輸出資料夾>/<段號>.wav（22050 Hz）。已經有的 wav 會跳過，所以中斷後可以接續。
- fp32、取樣參數用官方預設；一段一次生成，不拆句（拆句生成語氣會變差）。
"""
import os, re, sys, time

script, out = sys.argv[1:3]
REF_WAV = "/content/ref15.wav"   # 參考聲音（IndexTTS2 只用前 15 秒）

segs = []
for line in open(script, encoding="utf-8"):
    if line.startswith("## "):
        break
    m = re.match(r"^(\d{3})\t(.+)$", line.rstrip("\n"))
    if m:
        segs.append(m.groups())

t0 = time.time()
from indextts.infer_v2 import IndexTTS2
tts = IndexTTS2(cfg_path="checkpoints_2/config.yaml", model_dir="checkpoints_2",
                use_fp16=False, use_cuda_kernel=False, use_deepspeed=False)
print(f"[tts] load {time.time() - t0:.1f}s, {len(segs)} segments", flush=True)

os.makedirs(out, exist_ok=True)
for no, text in segs:
    path = os.path.join(out, f"{no}.wav")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        continue
    t = time.time()
    tmp = path + ".part.wav"
    tts.infer(spk_audio_prompt=REF_WAV, text=text, output_path=tmp, verbose=False)
    os.replace(tmp, path)   # 寫完才改名，下載端不會拿到寫到一半的檔案
    print(f"[tts][{no}] {time.time() - t:.1f}s  {text[:20]}", flush=True)
print("[tts] ALL_SEGMENTS_DONE", flush=True)
