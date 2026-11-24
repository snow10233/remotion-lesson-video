"""配音：生成＋品質迴圈，一條指令跑到完（可以中斷後重跑）。
用法：python3 voice_qc.py <批次資料夾> --voice <聲音> [--lang zh|en] [--rounds 2] [--cands 3] [--budget 540]
  批次資料夾：export_tts.mjs 產生的 tts/<影片>/，裡面要有 tts.txt（已通過 check_tts_text.py）、map.json、narration.json。
  --budget：這次最多跑幾秒；時間到就結束並回傳 75，重跑同一條指令會從中斷的地方接續。

流程（每一步的結果都存在 <批次>/qc/，重跑會跳過做完的步驟）：
  1. 生成：scripts/tts/run.sh（IndexTTS2，Colab L4）→ <批次>/wav/
  2. 辨識＋逐字對齊：scripts/asr/asr.py（Qwen3-ASR＋ForcedAligner，Colab L4）
  3. 找問題：念出來跟稿子不同（同音字不算）、寫成拼音的破音字實際念成別的音（scripts/mfa/check_reading.py，本機 MFA）、
     數字或字母旁的逗號沒停、停頓太長
  4. 有問題的句子重新生成 --cands 個候選，再辨識，挑最好的；最多 --rounds 輪
  5. 剪短太長的停頓；數字或字母旁還是沒停的逗號補靜音 → <批次>/final/wav/
  6. final 再辨識一次：逐字時間 → final/align.json（給 audio_meta.py 對時）；
     補靜音後念法反而變差的句子退回不補。報告 → final/REPORT.md
結束碼：0 完成；75 時間到、重跑接續；1 失敗（訊息說明原因，例如 Colab 登入過期要請使用者處理）。
"""
import argparse, difflib, json, os, re, shutil, subprocess, sys, time, wave
from pathlib import Path

try:
    import numpy as np, opencc
    from pypinyin import pinyin, Style
except ImportError:
    os.execvp("uv", ["uv", "run", "-q", "--with", "numpy", "--with", "opencc", "--with", "pypinyin",
                     "python3", __file__, *sys.argv[1:]])

HERE = Path(__file__).resolve().parent
os.environ["PATH"] = os.path.expanduser("~/.local/bin") + ":" + os.environ["PATH"]
sys.path.insert(0, str(HERE))
from check_tts_text import PINYIN, PINYIN_EQUIV  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("batch"); ap.add_argument("--voice", required=True)
ap.add_argument("--lang", default="zh", choices=["zh", "en"])
ap.add_argument("--rounds", type=int, default=2); ap.add_argument("--cands", type=int, default=3)
ap.add_argument("--budget", type=float, default=0)
a = ap.parse_args()
B = Path(a.batch).resolve(); Q = B / "qc"; FINAL = B / "final"
T0 = time.time()
ASR_LANG = {"zh": "Chinese", "en": "English"}[a.lang]
T2S = opencc.OpenCC("t2s")


def left():
    return max(30.0, a.budget - (time.time() - T0)) if a.budget else None


def say(*x):
    print(time.strftime("%H:%M:%S"), *x, flush=True)


def run(cmd, what):
    try:
        r = subprocess.run(cmd, timeout=left())
    except subprocess.TimeoutExpired:
        say(f"時間到了（{what}還沒做完），重跑同一條指令會接續"); sys.exit(75)
    return r.returncode


# ---------- 文字 ----------
def read_tts(path):
    d = {}
    for l in open(path, encoding="utf-8"):
        if l.startswith("## "): break
        p = l.rstrip("\n").split("\t", 1)
        if len(p) == 2 and p[0].isdigit(): d[p[0]] = p[1]
    return d


def spoken(t):  # 拼音標記換回漢字（對齊和比對用）
    return PINYIN.sub(lambda m: PINYIN_EQUIV.get(m.group(), m.group()), t)


TOK = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?|[0-9]+|[㐀-鿿]")
NUMS = set("零〇一二兩三四五六七八九十百千")
DIG = "零一二三四五六七八九"


def zh_num(n):
    n = int(n)
    if n < 10: return DIG[n]
    if n < 20: return "十" + (DIG[n % 10] if n % 10 else "")
    if n < 100: return DIG[n // 10] + "十" + (DIG[n % 10] if n % 10 else "")
    return "".join(DIG[int(c)] for c in str(n))


def sounds(text, is_hyp):
    """每個字可能的讀音（集合）：中文取所有破音讀法、不帶聲調；稿子裡寫成拼音的字只有那一個讀音；英文轉小寫"""
    if a.lang == "en":
        return [({t.lower()}, t) for t in TOK.findall(text)]
    if is_hyp:
        text = re.sub(r"\d+", lambda m: zh_num(m.group()), text)
    toks = re.findall(PINYIN.pattern + "|" + TOK.pattern, T2S.convert(text))
    zh = [t for t in toks if not (PINYIN.fullmatch(t) or t.isascii())]
    ctx = iter(pinyin("".join(zh), style=Style.NORMAL))  # 依上下文判斷的讀音
    out = []
    for t in toks:
        if PINYIN.fullmatch(t): out.append(({t[:-1].lower()}, PINYIN_EQUIV.get(t, t)))
        elif t.isascii(): out.append(({t.lower()}, t))
        else:  # 上下文讀音＋最常見的兩個讀音（冷門古讀不算，例如「句」的 qu）
            out.append(({next(ctx)[0], *pinyin(t, heteronym=True, style=Style.NORMAL)[0][:2]}, t))
    return out


def reading_errors(res):
    return [(f"{x['char']}（{x['want']}）", f"念成 {x['got']}") for x in res.get("reading", []) if x["got"] != x["want"]]


def misreads(ref_text, asr_text):
    """稿子和辨識結果逐字對齊（讀音有交集就算一樣），回傳不一樣的片段 [(稿子, 聽到的)]"""
    rs, hs = sounds(ref_text, False), sounds(asr_text or "", True)
    r, h = [x[0] for x in rs], [x[0] for x in hs]
    n, m = len(r), len(h)
    D = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1): D[i][0] = i
    for j in range(m + 1): D[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i][j] = min(D[i - 1][j] + 1, D[i][j - 1] + 1, D[i - 1][j - 1] + (0 if r[i - 1] & h[j - 1] else 1))
    ops, i, j = [], n, m
    while i or j:
        if i and j and D[i][j] == D[i - 1][j - 1] + (0 if r[i - 1] & h[j - 1] else 1):
            ops.append(("=" if r[i - 1] & h[j - 1] else "x", i - 1, j - 1)); i, j = i - 1, j - 1
        elif i and D[i][j] == D[i - 1][j] + 1:
            ops.append(("-", i - 1, None)); i -= 1
        else:
            ops.append(("+", None, j - 1)); j -= 1
    ops.reverse()

    out, cur = [], None
    for op, ri, hi in ops:
        if op == "=":
            if cur: out.append(cur); cur = None
            continue
        cur = cur or ["", ""]
        if ri is not None: cur[0] += rs[ri][1]
        if hi is not None: cur[1] += hs[hi][1]
    if cur: out.append(cur)
    return [tuple(x) for x in out]


# ---------- 音檔與停頓 ----------
def load(path):
    with wave.open(str(path)) as w:
        sr = w.getframerate(); x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return x, sr


def save(path, y, sr):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())


def energy(x, sr):
    hop = int(sr * 0.01); n = len(x) // hop
    return 20 * np.log10(np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12))


def silences(x, sr, min_len=0.05):
    db = energy(x, sr); v = db > max(db.max() - 38, -55)
    idx = np.where(v)[0]
    if not len(idx): return []
    out, i, s1 = [], idx[0], idx[-1]
    while i <= s1:
        if not v[i]:
            j = i
            while j <= s1 and not v[j]: j += 1
            if (j - i) * 0.01 >= min_len: out.append((i * 0.01, j * 0.01))
            i = j
        else: i += 1
    return out


TRIM = {"": (0.40, 0.20), "，": (0.65, 0.55), "。": (0.95, 0.80), "？": (0.95, 0.80), "！": (0.95, 0.80)}  # 超過 → 剪成


def critical(pair):
    if a.lang == "en":
        return any(t.isdigit() or len(t) == 1 for t in pair)
    return any(t in NUMS or t.isascii() for t in pair)


def boundaries(text, align, x, sr):
    """每兩個字之間：後面接的標點、實際的靜音長度"""
    ms = list(TOK.finditer(text)); toks = [m.group() for m in ms]
    if len(toks) != len(align) or any(t.lower() != al[0].lower() for t, al in zip(toks, align)):
        return toks, None
    sil = silences(x, sr); gaps = []
    for k in range(len(ms) - 1):
        p = re.search(r"[，。？！,.?!]", text[ms[k].end():ms[k + 1].start()])
        gaps.append((k, p.group().translate(str.maketrans(",.?!", "，。？！")) if p else "", align[k][2], align[k + 1][1]))
    owner = {}  # 每段靜音只歸給離它最近的字間
    for j, (s0, s1) in enumerate(sil):
        best = None
        for k, _, e, s in gaps:
            if s0 < max(e, s) + 0.12 and s1 > min(e, s) - 0.12:
                d = abs((s0 + s1) / 2 - (e + s) / 2)
                if best is None or d < best[0]: best = (d, k)
        if best: owner.setdefault(best[1], []).append((best[0], j))
    out = []
    for k, p, e, s in gaps:
        j = min(owner[k])[1] if k in owner else None
        out.append({"k": k, "p": p, "sil": sil[j] if j is not None else None,
                    "L": sil[j][1] - sil[j][0] if j is not None else 0.0, "e": e, "s": s})
    for b in out:  # 對齊器把停頓放錯位置：沒標點的長停頓旁邊兩個字內有標點卻沒停 → 當成那個標點的停頓
        if b["p"] == "" and b["L"] > 0.3:
            near = [c for c in out if c["p"] and abs(c["k"] - b["k"]) <= 2 and c["L"] < 0.1]
            if near: b["p"] = near[0]["p"]; near[0]["covered"] = True
    return toks, out


def plan(text, align, x, sr, inserts=True):
    toks, bnd = boundaries(text, align, x, sr)
    if bnd is None: return None, 0
    edits, crit = [], 0
    ctx = lambda k: "".join(toks[max(0, k - 4):k + 1]) + "▌" + "".join(toks[k + 1:k + 4])
    for b in bnd:
        lim, to = TRIM[b["p"]]
        if b["sil"] and b["L"] > lim:
            edits.append({"type": "trim", "at": list(b["sil"]), "to": to, "from": round(b["L"], 2), "ctx": ctx(b["k"])})
        elif b["p"] == "，" and not b.get("covered") and b["L"] < 0.10 and critical(toks[b["k"]:b["k"] + 2]):
            crit += 1
            if inserts:
                both_num = all(t in NUMS or t.isdigit() for t in toks[b["k"]:b["k"] + 2])
                edits.append({"type": "insert", "e": b["e"], "s": b["s"], "to": 0.15 if both_num else 0.22,
                              "from": round(b["L"], 2), "ctx": ctx(b["k"])})
        elif b["p"] in "。？！" and b["p"] and not b.get("covered") and b["L"] < 0.15:
            if inserts:
                edits.append({"type": "insert", "e": b["e"], "s": b["s"], "to": 0.40, "from": round(b["L"], 2), "ctx": ctx(b["k"])})
    return edits, crit


def apply(x, sr, edits):
    db = energy(x, sr); ops = []
    for ed in edits:
        if ed["type"] == "trim":
            s0, s1 = ed["at"]; keep = ed["to"]
            c0, c1 = int((s0 + keep / 2) * sr), int((s1 - keep / 2) * sr)
            ops.append((c0, c1 - c0, 0))
        else:  # 在兩個字之間音量最低的地方插入靜音，前後各 8 毫秒淡出淡入
            lo = int(max(0, min(ed["e"], ed["s"]) - 0.06) * 100); hi = max(int((max(ed["e"], ed["s"]) + 0.06) * 100), lo + 1)
            f = lo + int(np.argmin(db[lo:hi])); pos = int((f + 0.5) * 0.01 * sr)
            ops.append((pos, 0, int((ed["to"] - ed["from"]) * sr)))
    ops.sort(); fade = int(0.008 * sr); pieces, cur = [], 0
    for pos, dele, ins in ops:
        seg = x[cur:pos].copy()
        if ins and len(seg) > fade: seg[-fade:] *= np.linspace(1, 0, fade)
        pieces.append(seg)
        if ins: pieces.append(np.zeros(ins, dtype=np.float32))
        cur = pos + dele
        if ins and cur + fade < len(x):
            pieces.append(x[cur:cur + fade] * np.linspace(0, 1, fade)); cur += fade
    pieces.append(x[cur:])
    return np.concatenate(pieces)


def analyze(text, wav, res):
    x, sr = load(wav)
    sp = spoken(text)
    edits, crit = plan(sp, res.get("align") or [], x, sr)
    mr = misreads(text, res.get("asr")) + reading_errors(res)
    r = {"wav": str(wav), "dur": len(x) / sr, "asr": res.get("asr"), "misreads": mr, "crit": crit,
         "aligned": edits is not None, "ins": sum(e["type"] == "insert" for e in edits or []),
         "trim": sum(e["type"] == "trim" for e in edits or [])}
    return r


def score(r, dur0, original):
    return (len(r["misreads"]) * 10 + r["ins"] * 2 + r["trim"] * 0.5
            + (5 if abs(r["dur"] / dur0 - 1) > 0.25 else 0) + (5 if not r["aligned"] else 0) - (0.1 if original else 0))


def asr_input(d, items):
    """items: {編號: (wav 路徑, 文字)} → 給 asr.py 的資料夾"""
    if (d / "tts.txt").exists():
        if not (d / "tts_raw.txt").exists():
            (d / "tts_raw.txt").write_text("".join(f"{i}\t{t}\n" for i, (w, t) in sorted(items.items())), encoding="utf-8")
        return
    (d / "wav").mkdir(parents=True, exist_ok=True)
    for i, (w, t) in items.items(): shutil.copyfile(w, d / "wav" / f"{i}.wav")
    (d / "tts.txt").write_text("".join(f"{i}\t{spoken(t)}\n" for i, (w, t) in sorted(items.items())), encoding="utf-8")
    (d / "tts_raw.txt").write_text("".join(f"{i}\t{t}\n" for i, (w, t) in sorted(items.items())), encoding="utf-8")


def asr(d, out):
    if out.exists(): return with_reading(d, out)
    for _ in range(4):
        rc = run([sys.executable, str(HERE / "asr" / "asr.py"), str(d), str(out), "--lang", ASR_LANG, "--keep",
                  *(["--budget", str(left())] if a.budget else [])], "辨識")
        if rc == 75: sys.exit(75)
        if rc != 2: break
        say("開不到 VM，一分鐘後重試"); time.sleep(60)
    if rc: say("辨識失敗"); sys.exit(1)
    return with_reading(d, out)


def with_reading(d, out):
    """辨識結果加上讀音檢查（MFA，只檢查稿子裡寫成拼音的字）"""
    segs = json.load(open(out, encoding="utf-8"))["segs"]
    if a.lang != "zh": return segs
    rout = out.with_name(out.stem + "_reading.json")
    if not rout.exists():
        r = subprocess.run([sys.executable, str(HERE / "mfa" / "check_reading.py"), str(d / "wav"), str(d / "tts_raw.txt"), str(rout)])
        if r.returncode:
            say("讀音檢查失敗，這一批跳過讀音檢查"); json.dump({"_error": True}, open(rout, "w"))
    rd = json.load(open(rout, encoding="utf-8"))
    for i, xs in rd.items():
        if i in segs: segs[i]["reading"] = xs
    return segs


def tts(script, wav_dir):
    for _ in range(5):
        rc = run(["bash", str(HERE / "tts" / "run.sh"), str(script), str(wav_dir), a.voice], "生成")
        if rc == 0: return
        if rc in (1, 64): say("生成失敗，見上面的訊息"); sys.exit(1)
        if rc == 2: say("開不到 VM，一分鐘後重試"); time.sleep(60)
    say("生成重試五次仍未完成"); sys.exit(1)


def stop_asr():
    subprocess.run(["colab", "stop", "-s", "lessonasr"], capture_output=True, timeout=120)


# ---------- 主流程 ----------
if (FINAL / ".done").exists():
    say("已經完成：", FINAL / "REPORT.md"); sys.exit(0)
texts = read_tts(B / "tts.txt")
mp = json.load(open(B / "map.json", encoding="utf-8"))
Q.mkdir(exist_ok=True)

say(f"1. 生成 {len(texts)} 句"); tts(B / "tts.txt", B / "wav")
say("2. 辨識＋對齊")
asr_input(Q / "r0", {s: (B / "wav" / f"{s}.wav", t) for s, t in texts.items()})
R0 = asr(Q / "r0", Q / "r0.json")
best = {s: analyze(t, B / "wav" / f"{s}.wav", R0[s]) for s, t in texts.items()}
orig_dur = {s: best[s]["dur"] for s in texts}
for s in best: best[s]["src"] = "orig"
bad = lambda r: r["misreads"] or r["crit"] > 0
say(f"   念法不同 {sum(bool(r['misreads']) for r in best.values())} 句，數字或字母旁的逗號沒停 {sum(r['crit'] > 0 for r in best.values())} 句")

for rnd in range(1, a.rounds + 1):
    rd = Q / f"r{rnd}"
    if (rd / "cand_map.json").exists():
        cmap = json.load(open(rd / "cand_map.json"))
    else:
        flagged = sorted(s for s, r in best.items() if bad(r))
        if not flagged: break
        rd.mkdir(exist_ok=True); cmap = {}; n = 1
        lines = []
        for s in flagged:
            for _ in range(a.cands):
                c = f"{n:03d}"; cmap[c] = s; lines.append(f"{c}\t{texts[s]}"); n += 1
        (rd / "tts.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        json.dump(cmap, open(rd / "cand_map.json", "w"), indent=1)
    if not cmap: break
    say(f"3. 第 {rnd} 輪：{len(set(cmap.values()))} 句各重新生成 {a.cands} 個候選")
    tts(rd / "tts.txt", rd / "wav")
    asr_input(rd / "in", {c: (rd / "wav" / f"{c}.wav", texts[s]) for c, s in cmap.items()})
    Rr = asr(rd / "in", rd / "asr.json")
    for c, s in cmap.items():
        r = analyze(texts[s], rd / "wav" / f"{c}.wav", Rr[c]); r["src"] = f"r{rnd}/{c}"
        if score(r, orig_dur[s], False) < score(best[s], orig_dur[s], best[s]["src"] == "orig"):
            best[s] = r

say("4. 修停頓，寫出 final/")
changes, items = {}, {}
def build(s, inserts=True):
    r = best[s]; x, sr = load(r["wav"])
    res = R0[s] if r["src"] == "orig" else json.load(open(Q / r["src"].split("/")[0] / "asr.json", encoding="utf-8"))["segs"][r["src"].split("/")[1]]
    edits, _ = plan(spoken(texts[s]), res.get("align") or [], x, sr, inserts)
    edits = edits or []
    save(FINAL / "wav" / f"{s}.wav", apply(x, sr, edits) if edits else x, sr)
    return edits
for s in texts:
    edits = build(s)
    if edits or best[s]["src"] != "orig":
        changes[s] = {"id": mp[s]["id"], "src": best[s]["src"], "edits": [{k: e[k] for k in ("type", "from", "to", "ctx")} for e in edits]}
    items[s] = (FINAL / "wav" / f"{s}.wav", texts[s])
shutil.rmtree(Q / "final_in", ignore_errors=True)
asr_input(Q / "final_in", items)
RF = asr(Q / "final_in", Q / "final.json")

# 補靜音之後念法反而變差 → 這句不補，只剪
redo = [s for s, c in changes.items() if any(e["type"] == "insert" for e in c["edits"])
        and len(misreads(texts[s], RF[s].get("asr")) + reading_errors(RF[s])) > len(best[s]["misreads"])]
if redo:
    say(f"   {len(redo)} 句補靜音後念法變差，改成不補：{' '.join(redo)}")
    for s in redo:
        edits = build(s, inserts=False)
        changes[s]["edits"] = [{k: e[k] for k in ("type", "from", "to", "ctx")} for e in edits]
        changes[s]["note"] = "補靜音後辨識變差，已退回不補"
    asr_input(Q / "redo_in", {s: items[s] for s in redo})
    RF.update(asr(Q / "redo_in", Q / "redo.json"))
stop_asr()

align = {}
for s, t in texts.items():
    al = RF[s].get("align") or []
    if [w.lower() for w in TOK.findall(spoken(t))] == [x[0].lower() for x in al]: align[s] = al
json.dump(align, open(FINAL / "align.json", "w", encoding="utf-8"), ensure_ascii=False)
for f in ("map.json", "narration.json", "src.txt", "tts.txt"):
    if (B / f).exists(): shutil.copyfile(B / f, FINAL / f)
shutil.copyfile(B / "wav" / "voice.txt", FINAL / "wav" / "voice.txt")
json.dump(changes, open(FINAL / "changes.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------- 報告 ----------
final_bad = {s: misreads(t, RF[s].get("asr")) + reading_errors(RF[s]) for s, t in texts.items()}
final_bad = {s: m for s, m in final_bad.items() if m}
L = [f"# 配音報告（{time.strftime('%Y-%m-%d %H:%M')}）", "",
     f"- 共 {len(texts)} 句；改過 {len(changes)} 句，其中換成重新生成的 {sum(c['src'] != 'orig' for c in changes.values())} 句",
     f"- 剪停頓 {sum(e['type'] == 'trim' for c in changes.values() for e in c['edits'])} 處，補停頓 {sum(e['type'] == 'insert' for c in changes.values() for e in c['edits'])} 處",
     f"- 逐字對齊成功 {len(align)}/{len(texts)} 句（失敗的句子對時會退回停頓猜測）", "",
     "## 要請人聽的句子", "",
     "### 念法跟稿子不同（辨識：同音字已排除，可能是念錯也可能是辨識模型聽錯；讀音檢查：寫成拼音的字實際念成別的音）", ""]
def pair(r, h): return (r or "∅") + "→" + (h or "∅")
L += [f"- {s}（{mp[s]['id']}）：{'、'.join(pair(r, h) for r, h in m)}｜{texts[s]}" for s, m in sorted(final_bad.items())] or ["- 無"]
L += ["", "### 補了靜音的地方（硬插的，可能聽得出切口）", ""]
L += [f"- {s}（{c['id']}）：{e['ctx']} {e['from']}→{e['to']} 秒" for s, c in sorted(changes.items()) for e in c["edits"] if e["type"] == "insert"] or ["- 無"]
L += ["", "### 換成重新生成的句子（語氣可能跟前後句不同）", ""]
L += [f"- {s}（{c['id']}）" for s, c in sorted(changes.items()) if c["src"] != "orig"] or ["- 無"]
(FINAL / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
(FINAL / ".done").write_text("ok")
say("完成：", FINAL / "REPORT.md")
