"""把 TTS 稿轉成簡體（OpenCC t2s：只轉字形、不改用詞）。
用法：uv run --with opencc python3 to_simplified.py <TTS稿.txt>  → 產生 <檔名>_簡.txt
"""
import sys
from pathlib import Path
import opencc

try:
    cc = opencc.OpenCC("t2s")
except Exception:
    cc = opencc.OpenCC("t2s.json")
src = Path(sys.argv[1])
dst = src.with_name(src.stem + "_簡" + src.suffix)
dst.write_text(cc.convert(src.read_text(encoding="utf-8")), encoding="utf-8")
print(dst)
