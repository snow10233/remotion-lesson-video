"""在 Colab VM 上跑：Qwen3-ASR 辨識＋Qwen3-ForcedAligner 逐字對齊。由 asr.py 上傳並在背景啟動。
用法：python3 asr_job.py <工作資料夾> <語言 Chinese|English>
工作資料夾裡有 tts.txt（每行 `編號<TAB>要念的文字`）和 wav/<編號>.wav。
輸出 <工作資料夾>/out.json：{"segs": {編號: {"asr": 辨識文字, "align": [[字, 開始秒, 結束秒], ...]}}}
失敗時寫 <工作資料夾>/FAILED（內容是錯誤訊息）。
"""
import json, sys, time, traceback
from pathlib import Path

D = Path(sys.argv[1]); LANG = sys.argv[2]
try:
    import torch
    from qwen_asr import Qwen3ASRModel, Qwen3ForcedAligner
    segs = {}
    for l in open(D / "tts.txt", encoding="utf-8"):
        p = l.rstrip("\n").split("\t", 1)
        if len(p) == 2 and p[0].strip(): segs[p[0]] = p[1]
    ids = sorted(segs)
    paths = [str(D / "wav" / f"{i}.wav") for i in ids]
    out = {i: {} for i in ids}
    B = 16
    t = time.time()
    asr = Qwen3ASRModel.from_pretrained("Qwen/Qwen3-ASR-1.7B", dtype=torch.bfloat16, device_map="cuda:0",
                                        max_inference_batch_size=B, max_new_tokens=512)
    for k in range(0, len(ids), B):
        b = ids[k:k + B]
        for i, r in zip(b, asr.transcribe(audio=paths[k:k + B], language=[LANG] * len(b))):
            out[i]["asr"] = r.text
        print("asr", k + len(b), flush=True)
    del asr; torch.cuda.empty_cache()
    al = Qwen3ForcedAligner.from_pretrained("Qwen/Qwen3-ForcedAligner-0.6B", dtype=torch.bfloat16, device_map="cuda:0")
    for k in range(0, len(ids), B):
        b = ids[k:k + B]
        try:
            rs = al.align(audio=paths[k:k + B], text=[segs[i] for i in b], language=[LANG] * len(b))
        except Exception:
            rs = []
            for i in b:  # 整批失敗就一句一句來，失敗的那句留空
                try: rs.append(al.align(audio=str(D / "wav" / f"{i}.wav"), text=segs[i], language=LANG)[0])
                except Exception: rs.append(None)
        for i, r in zip(b, rs):
            out[i]["align"] = [[u.text, float(u.start_time), float(u.end_time)] for u in r] if r is not None else []
        print("align", k + len(b), flush=True)
    json.dump({"segs": out, "sec": time.time() - t}, open(D / "out.json.tmp", "w", encoding="utf-8"), ensure_ascii=False)
    (D / "out.json.tmp").rename(D / "out.json")
    print("DONE", flush=True)
except Exception:
    (D / "FAILED").write_text(traceback.format_exc())
    raise
