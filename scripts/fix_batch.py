"""建一個「補做批次」：只放要重配的那幾句，之後照常跑 TTS 改寫和 voice_qc.py。
用法：python3 fix_batch.py <剛匯出的資料夾> <新批次資料夾> <旁白 id> [<旁白 id> ...]
  剛匯出的資料夾：用 export_tts.mjs 把目前的旁白匯出到一個暫存資料夾（例如 tts/<影片>/export-now）
  新批次資料夾：例如 tts/<影片>/fix1（不要跟舊批次同一個資料夾）
輸出：新批次裡的 src.txt、map.json、narration.json（段號從 001 重新編）。
接回影片時，audio_meta.py 依序給「主批次的 final」和「補做批次的 final」，後面的會覆蓋前面同一句。
"""
import json, sys
from pathlib import Path

src, out, ids = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
if not ids:
    print(__doc__); sys.exit(64)
if out.exists() and any(out.iterdir()):
    print(f"{out} 已經有東西，換一個新的資料夾名稱"); sys.exit(1)
mp = json.load(open(src / "map.json", encoding="utf-8"))
narr = {x["id"]: x for x in json.load(open(src / "narration.json", encoding="utf-8"))}
by_id = {v["id"]: v for v in mp.values()}
missing = [i for i in ids if i not in by_id]
if missing:
    print("找不到這些旁白 id：", " ".join(missing)); sys.exit(1)
out.mkdir(parents=True, exist_ok=True)
new_map = {f"{k:03d}": by_id[i] for k, i in enumerate(ids, 1)}
(out / "src.txt").write_text("\n\n".join([out.name] + [by_id[i]["text"] for i in ids]) + "\n", encoding="utf-8")
json.dump(new_map, open(out / "map.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump([narr[i] for i in ids], open(out / "narration.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"補做批次 {out}：{len(ids)} 句")
