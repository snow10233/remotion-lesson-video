"""比對 checkpoints 資料夾裡的大檔與 HuggingFace 上的 sha256；不符就刪掉並以結束碼 1 離開（讓外層重新下載）。
用法：uv run python verify_ckpt.py <local_dir> [repo]"""
import hashlib, os, sys
from huggingface_hub import HfApi

d = sys.argv[1]
repo = sys.argv[2] if len(sys.argv) > 2 else "IndexTeam/IndexTTS-2"
bad = 0
for s in HfApi().model_info(repo, files_metadata=True).siblings:
    if not s.lfs:
        continue
    p = os.path.join(d, s.rfilename)
    if not os.path.exists(p):
        print("MISSING", s.rfilename); bad += 1; continue
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    ok = h.hexdigest() == s.lfs.sha256
    print("OK " if ok else "BAD", s.rfilename)
    if not ok:
        os.remove(p); bad += 1
sys.exit(1 if bad else 0)
