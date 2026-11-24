"""讀音檢查：稿子裡寫成拼音的字（念法表的破音字，例如 第三HANG2），音檔實際念的是不是那個讀音。
用法：python3 check_reading.py <wav 資料夾> <TTS 稿> <輸出.json>
  TTS 稿：每行 `編號<TAB>內容`，保留拼音標記；wav 資料夾裡是 <編號>.wav
輸出：{編號: [{"char", "want", "got", "start", "end", "ctx"}]}，只列有拼音標記的句子；got 和 want 不同就是念錯。
做法：用 Montreal Forced Aligner 對齊，字典裡這個字放最常見的兩個讀音加上稿子指定的讀音、機率相同，看它選哪一個。
  2026-11-23 實測：「行」háng／xíng 跟母音共振峰的量測 18/18 一致，使用者試聽確認。
  拼音音節 → MFA 音標的對照表，從 MFA 字典裡只有一種讀音的單字學出來（快取在 MFA 資料夾的 syllables.json）。
第一次用會自動跑 setup.sh 安裝 MFA（約 2.5 GB、幾分鐘）。
"""
import json, os, re, shutil, subprocess, sys, difflib
from collections import Counter, defaultdict
from pathlib import Path

try:
    import opencc
    from pypinyin import pinyin, Style
except ImportError:
    os.execvp("uv", ["uv", "run", "-q", "--with", "opencc", "--with", "pypinyin", "python3", __file__, *sys.argv[1:]])

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from check_tts_text import PINYIN, PINYIN_EQUIV  # noqa: E402

R = Path(os.environ.get("LESSON_MFA_HOME", Path.home() / ".local/share/lesson-video/mfa"))
DICT = R / "root/pretrained_models/dictionary/mandarin_mfa.dict"
T2S = opencc.OpenCC("t2s")
TOK = re.compile(PINYIN.pattern + r"|[A-Za-z]+|[㐀-鿿]")


def ensure_mfa():
    if not (R / "env/bin/mfa").exists() or not DICT.exists():
        r = subprocess.run(["bash", str(HERE / "setup.sh")], capture_output=True, text=True)
        if "MFA_READY" not in r.stdout:
            sys.exit("MFA 安裝失敗：" + (r.stdout + r.stderr)[-1500:])


def syllable_map():
    cache = R / "syllables.json"
    if cache.exists():
        return json.load(open(cache, encoding="utf-8"))
    prons = defaultdict(set)
    for l in open(DICT, encoding="utf-8"):
        p = l.rstrip("\n").split("\t")
        if len(p[0]) == 1 and "㐀" <= p[0] <= "鿿":
            prons[p[0]].add(p[-1])
    votes = defaultdict(Counter)
    for ch, ps in prons.items():
        py = set(pinyin(ch, heteronym=True, style=Style.TONE3, neutral_tone_with_five=True)[0])
        if len(py) == 1 and len(ps) == 1:
            votes[py.pop()][ps.pop()] += 1
    m = {s: c.most_common(1)[0][0] for s, c in votes.items()}
    json.dump(m, open(cache, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return m


def tiers(path):
    txt = path.read_text(encoding="utf-8"); out = {}
    for name, body in re.findall(r'name = "(\w+)"(.*?)(?=item \[|\Z)', txt, re.S):
        out[name] = [(float(a), float(b), t) for a, b, t in re.findall(r'xmin = ([\d.]+)\s+xmax = ([\d.]+)\s+text = "(.*?)"', body)]
    return out


def main():
    wavs, script, out = (Path(p).resolve() for p in sys.argv[1:4])  # MFA 給相對路徑會找不到自己的資料庫
    items = {}
    for l in open(script, encoding="utf-8"):
        if l.startswith("## "): break
        p = l.rstrip("\n").split("\t", 1)
        if len(p) == 2 and PINYIN.search(p[1]) and (wavs / f"{p[0]}.wav").exists():
            items[p[0]] = p[1]
    if not items:
        json.dump({}, open(out, "w")); print("沒有拼音標記的句子，不用檢查"); return
    ensure_mfa()
    syl = syllable_map(); inv = defaultdict(list)
    for s, ipa in syl.items(): inv[ipa].append(s)
    work = out.parent / f".{out.stem}_mfa"; shutil.rmtree(work, ignore_errors=True)
    corpus = work / "corpus"; corpus.mkdir(parents=True)
    checks, words = {}, set()
    for i, text in items.items():
        toks, chk = [], []
        for t in TOK.findall(text):
            if PINYIN.fullmatch(t):
                ch = PINYIN_EQUIV.get(t)
                if not ch: continue
                chk.append((len(toks), ch, t.lower())); toks.append(T2S.convert(ch))
            else:
                toks.append(T2S.convert(t))
        shutil.copyfile(wavs / f"{i}.wav", corpus / f"{i}.wav")
        (corpus / f"{i}.lab").write_text(" ".join(toks), encoding="utf-8")
        checks[i] = (toks, chk); words |= set(toks)
    src = defaultdict(list)
    for l in open(DICT, encoding="utf-8"):
        p = l.rstrip("\n").split("\t"); src[p[0]].append(p[-1])
    checked_chars = {T2S.convert(c) for _, (_, chk) in checks.items() for _, c, _ in chk}
    skipped = set()
    with open(work / "test.dict", "w", encoding="utf-8") as f:
        for w in sorted(words):
            prons = list(dict.fromkeys(src.get(w, [])))
            if w in checked_chars:  # 最常見的兩個讀音＋稿子指定的讀音，機率相同（冷門讀音如「行」的 héng 會造成誤判）
                cand = pinyin(w, heteronym=True, style=Style.TONE3, neutral_tone_with_five=True)[0][:2]
                cand += [want for _, (_, chk) in checks.items() for _, c, want in chk if T2S.convert(c) == w]
                prons = [syl[s] for s in dict.fromkeys(cand) if s in syl]
            for ph in prons: f.write(f"{w}\t{ph}\n")
    env = dict(os.environ, PATH=f"{R}/env/bin:" + os.environ["PATH"], MFA_ROOT_DIR=str(R / "root"))
    r = subprocess.run(["mfa", "align", "--clean", "--single_speaker", "-j", str(min(8, os.cpu_count() or 4)),
                        str(corpus), str(work / "test.dict"), "mandarin_mfa", str(work / "out"),
                        "--temporary_directory", str(work / "tmp")], env=env, capture_output=True, text=True)
    if r.returncode:
        sys.exit("MFA 對齊失敗：" + (r.stdout + r.stderr)[-2000:])
    res = {}
    for i, (toks, chk) in checks.items():
        tg = work / "out" / f"{i}.TextGrid"
        if not tg.exists():
            res[i] = [{"char": c, "want": w, "got": "對齊失敗", "start": None, "end": None, "ctx": ""} for _, c, w in chk]; continue
        t = tiers(tg)
        ws = [(a, b, x) for a, b, x in t.get("words", []) if x]
        sm = difflib.SequenceMatcher(None, toks, [x for _, _, x in ws], autojunk=False)
        pos = {}
        for a0, b0, n in sm.get_matching_blocks():
            for k in range(n): pos[a0 + k] = b0 + k
        res[i] = []
        for k, ch, want in chk:
            if k not in pos:
                res[i].append({"char": ch, "want": want, "got": "對齊失敗", "start": None, "end": None, "ctx": ""}); continue
            a, b, _ = ws[pos[k]]
            ph = " ".join(p for x, y, p in t.get("phones", []) if x >= a - 1e-6 and y <= b + 1e-6)
            if want not in syl:
                got = "無法檢查"
            elif ph == syl[want]:
                got = want
            else:
                got = "/".join(inv.get(ph, [ph]))
            ctx = "".join(toks[max(0, k - 3):k]) + "▌" + ch + "▌" + "".join(toks[k + 1:k + 3])
            res[i].append({"char": ch, "want": want, "got": got, "start": round(a, 2), "end": round(b, 2), "ctx": ctx})
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    shutil.rmtree(work, ignore_errors=True)
    bad = [(i, x) for i, xs in res.items() for x in xs if x["got"] != x["want"]]
    print(f"檢查 {sum(len(x) for x in res.values())} 個字，讀音不符 {len(bad)} 個")
    for i, x in bad: print(f"  {i} {x['ctx']}：要 {x['want']}，念成 {x['got']}")


if __name__ == "__main__":
    main()
