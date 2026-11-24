"""檢查 TTS 稿子是否符合 references/tts-rules.md：只允許中文、英文字母、空格與 ，。？！
用法：python3 check_tts_text.py <tts稿.txt> [原稿.txt]
- 列出每段不允許的字元（含殘留的阿拉伯數字、符號）
- 給原稿時，比對段數是否一致，並逐段做兩種檢查：
  忠實度（去掉數字與標點後文字必須相同）、數字（原稿的阿拉伯數字和中文數字，換算成數值後要跟 TTS 稿一樣多、一樣大）
結束碼：0 = 全部通過，1 = 有問題
"""
import re, sys
from pathlib import Path

ALLOWED = re.compile(r"[一-鿿A-Za-z ，。？！]")


def load_tts(path):
    segs = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            break
        if not line.strip():
            continue
        m = re.match(r"^(\d{3})\t(.*)$", line)
        segs.append((m.group(1), m.group(2)) if m else ("???", line))
    return segs


def load_source(path):
    paras = [p.strip() for p in Path(path).read_text(encoding="utf-8").split("\n\n") if p.strip()]
    return paras[1:]  # 第一段是標題


# 忠實度檢查：拿掉數字（含中文數字字）、標點、空格、連字號後，兩邊剩下的字應該完全相同
NUM_CHARS = "零〇一二兩三四五六七八九十百千萬億負點"
STRIP = re.compile(rf"分之|[\d{NUM_CHARS}\s\-−‐，。？！：；、「」『』“”\"'（）()…—｜/／+×÷=<>.]")


# 念法表允許的字形替換：比對時視為同一個字（TTS 稿的字 → 原稿的字）
EQUIV = str.maketrans({"着": "著", "于": "於"})

# 念法表允許的內嵌拼音（大寫拼音＋聲調 1～5，例如 SHU3）：TTS 稿的拼音 → 原稿的字
# 新增拼音條目時要同步加在這裡；沒登記的拼音會被報錯
PINYIN = re.compile(r"[A-Z]+[1-5]")
PINYIN_EQUIV = {"SHU3": "數", "LIANG2": "量", "ZHE5": "著", "HANG2": "行", "XING2": "行"}


def skeleton(s, tts=False):
    if tts:
        s = PINYIN.sub(lambda m: PINYIN_EQUIV.get(m.group(), m.group()), s)
    return STRIP.sub("", s.translate(EQUIV))


def fidelity_diff(src, out):
    """回傳第一個不同之處的前後文，相同則回傳 None"""
    a, b = skeleton(src), skeleton(out, tts=True)
    if a == b:
        return None
    i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
    return f"原稿「…{a[max(0, i-6):i+8]}…」 vs TTS稿「…{b[max(0, i-6):i+8]}…」"


# 破音字檢查（念法表的機器版）：
# MUST：有固定寫法的，TTS 稿裡還留著漢字就報錯。確定某處不是這個讀音時，寫出正確讀音的拼音（例如 XING2），檢查就會放行
#   （IndexTTS2 不一定照拼音念，實際念法由 voice_qc.py 的讀音檢查確認）。
# WATCH：要看語意才知道的，只列出來提醒，不影響通過；逐條判斷，是念法表說的用法就改。
# 念法表新增破音字時，能寫成固定寫法的加進 MUST，不能的加進 WATCH。
MUST = [
    (re.compile(r"(?:第[零〇一二兩三四五六七八九十百]+|[這那每哪整]一?|[上下前後同]一|[一兩三四五六七八九十百幾多])行(?![人為動走程李政業銷星軍])|行(?=號|數)"),
     "HANG2", "表示第幾行、這一行、整行的「行」念 háng"),
    (re.compile(r"於"), "于", "所有的「於」都寫成簡體「于」"),
]
WATCH = [
    (re.compile(r"數(?!字|學|量|值|據|列|目|線|位|理|論|次)(?<!函數)(?<!常數)(?<!次數)(?<!個數)(?<!參數)(?<!變數)(?<!係數)(?<!分數)(?<!多數)(?<!少數)(?<!整數)(?<!實數)(?<!複數)(?<!負數)(?<!正數)(?<!奇數)(?<!偶數)(?<!質數)(?<!指數)(?<!對數)(?<!倍數)(?<!級數)(?<!人數)(?<!總數)(?<!行數)(?<!位數)(?<!步數)(?<!點數)(?<!分數)"),
     "SHU3", "動詞的「數」（數一數、數步驟）念 shǔ"),
    (re.compile(r"量(?!詞|子|級|化|表|產|販)(?<!數量)(?<!容量)(?<!重量)(?<!質量)(?<!能量)(?<!大量)(?<!少量)(?<!變量)(?<!向量)(?<!分量)(?<!流量)(?<!音量)(?<!存量)(?<!計量)(?<!力量)(?<!份量)(?<!產量)(?<!用量)(?<!總量)(?<!限量)(?<!適量)(?<!儘量)(?<!盡量)(?<!考量)(?<!質量)(?<!含量)(?<!雨量)(?<!熱量)"),
     "LIANG2", "動詞的「量」（量時間、量長度）念 liáng"),
    (re.compile(r"著(?!作|名|稱|重|手|陸|眼)(?<!顯著)(?<!卓著)(?<!土著)(?<!原著)(?<!名著)(?<!昭著)"),
     "着", "助詞的「著」（接著、跟著）寫成「着」"),
]


def polyphone_issues(text):
    """回傳 (錯誤, 提醒)：每條是「前後文｜該怎麼寫｜說明」"""
    plain = PINYIN.sub("　", text)  # 已經寫成拼音的地方不檢查
    def hits(rules):
        out = []
        for rx, want, why in rules:
            for m in rx.finditer(plain):
                a, b = max(0, m.start() - 4), m.end() + 4
                out.append(f"「{plain[a:b]}」→ {want}（{why}）")
        return out
    return hits(MUST), hits(WATCH)


# 數字檢查：兩邊的數字換成數值，比對多重集合（順序可以不同，例如 1/2 → 二分之一）
ZH_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
ZH_UNIT = {"十": 10, "百": 100, "千": 1000}
SUPSUB = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉", "01234567890123456789")
NUM_TOKEN = re.compile(r"\d+(?:\.\d+)?|[零〇一二兩三四五六七八九十百千萬億點]+|平方|立方")


def zh_int(t):
    if not any(c in t for c in "十百千萬億"):
        return int("".join(str(ZH_DIGIT[c]) for c in t)) if t else 0  # 逐字念：二零二三
    total, section, num = 0, 0, 0
    for c in t:
        if c in ZH_DIGIT:
            num = ZH_DIGIT[c]
        elif c in ZH_UNIT:
            section += (num or 1) * ZH_UNIT[c]; num = 0
        elif c == "萬":
            total += (section + num) * 10000; section = num = 0
        elif c == "億":
            total += (section + num) * 100000000; section = num = 0
    return total + section + num


def numbers(s):
    out = []
    for t in NUM_TOKEN.findall(PINYIN.sub(" ", s.translate(SUPSUB))):
        if t == "平方": out.append(2.0); continue
        if t == "立方": out.append(3.0); continue
        if t[0].isdigit(): out.append(float(t)); continue
        if t.strip("點") == "": continue
        a, _, b = t.partition("點")
        v = float(zh_int(a))
        if b: v += float("0." + "".join(str(ZH_DIGIT.get(c, 0)) for c in b))
        out.append(v)
    return sorted(out)


def number_diff(src, out):
    a, b = numbers(src), numbers(out)
    if a == b:
        return None
    fmt = lambda xs: "、".join(f"{x:g}" for x in xs) or "（無）"
    return f"原稿 {fmt(a)}；TTS稿 {fmt(b)}"


def main():
    segs = load_tts(sys.argv[1])
    bad = 0
    warnings = []
    for i, (no, text) in enumerate(segs, 1):
        problems = []
        if no != f"{i:03d}":
            problems.append(f"段號應為 {i:03d}")
        unknown = sorted({p for p in PINYIN.findall(text) if p not in PINYIN_EQUIV})
        if unknown:
            problems.append("念法表沒登記的拼音：" + " ".join(unknown))
        illegal = sorted({c for c in PINYIN.sub("", text) if not ALLOWED.match(c)})
        if illegal:
            problems.append("不允許的字元：" + " ".join(f"{c!r}(U+{ord(c):04X})" for c in illegal))
        must, watch = polyphone_issues(text)
        if must:
            problems.append("破音字還沒轉：" + "；".join(must))
        for w in watch:
            warnings.append(f"[{no}] 提醒：{w}")
        if re.search(r"[，。？！]{2,}", text):
            problems.append("連續標點")
        if re.search(r"  ", text):
            problems.append("連續空格")
        if problems:
            bad += 1
            print(f"[{no}] " + "；".join(problems) + f"\n      {text}")
    if len(sys.argv) > 2:
        src = load_source(sys.argv[2])
        if len(src) != len(segs):
            bad += 1
            print(f"段數不一致：原稿 {len(src)} 段，TTS 稿 {len(segs)} 段")
        else:
            for (no, text), s in zip(segs, src):
                d = fidelity_diff(s, text)
                if d:
                    bad += 1
                    print(f"[{no}] 內容可能被改動：{d}")
                d = number_diff(s, text)
                if d:
                    bad += 1
                    print(f"[{no}] 數字對不上：{d}")
    if warnings:
        print("以下是要看語意的破音字（不影響通過）：是念法表說的用法就照改，不是就不用動")
        print("\n".join(warnings))
    print(f"共 {len(segs)} 段，{'全部通過' if not bad else f'{bad} 處有問題'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
