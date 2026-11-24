# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scipy"]
# ///
"""替算好的影片加上背景音樂（影片畫面不重新編碼）。

用法：uv run add_music.py <輸入.mp4> <輸出.mp4> --key 0-11 --seed 整數 [--chimes 秒,秒,...]

- 音樂是程式合成的安靜讀書音樂，長度自動等於影片。key 是調性（C 起算的半音數），seed 是亂數種子；
  同一組 key／seed 每次都產生同一段音樂。同一個系列每支影片換一組，聽起來才不會都一樣。
- 輸入影片有人聲：人聲標準化到 -16 LUFS，音樂 -26 LUFS，有人聲時再自動把音樂壓低。
- 輸入影片沒有聲音：只放音樂（-20 LUFS）。
- --chimes：在這些秒數加一聲很輕的提示音，通常放每個場景開始的時間（第一個場景不用）。
- 結束時印出成品的音量。
"""
import argparse, os, re, subprocess, sys, tempfile

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, oaconvolve, sosfilt

SR = 44100
BPM = 74
BEAT = 60 / BPM
BAR = 4 * BEAT


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def env_adsr(n, a, d, s, r, sr=SR):
    A, D, R = int(a * sr), int(d * sr), int(r * sr)
    S = max(0, n - A - D - R)
    e = np.concatenate([np.linspace(0, 1, A, endpoint=False), np.linspace(1, s, D, endpoint=False), np.full(S, s), np.linspace(s, 0, R)])
    return e[:n] if len(e) >= n else np.pad(e, (0, n - len(e)))


def pad_voice(freq, dur, rng):
    n = int(dur * SR); t = np.arange(n) / SR
    det = [0.997, 1.0, 1.003]
    sig = np.zeros(n)
    for d in det:
        f = freq * d; ph = rng.uniform(0, 2 * np.pi)
        sig += np.sin(2 * np.pi * f * t + ph) + 0.35 * np.sin(4 * np.pi * f * t + ph) + 0.12 * np.sin(6 * np.pi * f * t)
    lfo = 1 + 0.15 * np.sin(2 * np.pi * 0.21 * t + rng.uniform(0, 6))
    return sig * lfo * env_adsr(n, 1.2, 0.5, 0.8, 1.4) / len(det)


def epiano(freq, dur, vel):
    n = int(dur * SR); t = np.arange(n) / SR
    decay = np.exp(-t * 3.2)
    sig = np.sin(2 * np.pi * freq * t) + 0.28 * np.sin(4 * np.pi * freq * t) * np.exp(-t * 6) + 0.08 * np.sin(2 * np.pi * 3.01 * freq * t) * np.exp(-t * 9)
    att = np.minimum(1, t / 0.006)
    return sig * decay * att * vel


def bass(freq, dur):
    n = int(dur * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * freq * t) + 0.2 * np.sin(4 * np.pi * freq * t)) * np.exp(-t * 1.6) * np.minimum(1, t / 0.01)


def kick():
    n = int(0.35 * SR); t = np.arange(n) / SR
    f = 95 * np.exp(-t * 18) + 45
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 11)


def shaker(rng):
    n = int(0.09 * SR); t = np.arange(n) / SR
    noise = rng.normal(0, 1, n)
    sos = butter(2, [5000, 11000], btype='band', fs=SR, output='sos')
    return sosfilt(sos, noise) * np.exp(-t * 55)


def chime(freq=1318.5):
    n = int(2.2 * SR); t = np.arange(n) / SR
    parts = [(1, 1.0, 2.2), (2.76, 0.35, 4.0), (5.4, 0.12, 6.5)]
    return sum(a * np.sin(2 * np.pi * freq * r * t) * np.exp(-t * d) for r, a, d in parts) * np.minimum(1, t / 0.004)


def add(buf, sig, start):
    i = int(start * SR)
    if i < 0 or i >= len(buf): return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[:j - i]


def reverb(x, rng, secs=2.2, wet=0.28):
    n = int(secs * SR); t = np.arange(n) / SR
    ir = rng.normal(0, 1, n) * np.exp(-t * 3.0)
    ir[0] = 0; ir /= np.sqrt(np.sum(ir ** 2))
    y = oaconvolve(x, ir)[:len(x)]
    return (1 - wet) * x + wet * y


def make(total, key, seed, chime_times):
    rng = np.random.default_rng(seed)
    n = int((total + 3) * SR)
    pad_l, pad_r, keys, low, perc = (np.zeros(n) for _ in range(5))
    # I - vi - IV - V(sus)，根音以 C 為基準
    prog = [(0, [0, 4, 7, 11]), (9, [0, 3, 7, 10]), (5, [0, 4, 7, 11]), (7, [0, 5, 7, 10])]
    base = 48 + key  # C3 + key
    bars = int(np.ceil(total / BAR)) + 1
    patterns = [[0, 2, 1, 3, 2, 1, 3, 2], [0, 1, 2, 3, 2, 3, 1, 2], [3, 2, 0, 1, 2, 0, 1, 3]]
    for b in range(bars):
        t0 = b * BAR
        root, ivs = prog[(b // 2) % 4]
        section = (b // 16) % 3
        if b % 2 == 0:  # 每兩小節一個長和弦
            for k, iv in enumerate(ivs):
                v = pad_voice(midi_hz(base + 12 + root + iv), 2 * BAR + 1.2, rng)
                add(pad_l if k % 2 == 0 else pad_r, v, t0)
        if b < 2:
            continue  # 前奏只有長和弦
        pat = patterns[section]
        for s8 in range(8):  # 電鋼琴分解和弦
            if section == 2 and s8 % 2 == 1 and rng.random() < 0.5:
                continue
            iv = ivs[pat[s8] % len(ivs)]
            octv = 24 if s8 in (3, 7) else 12
            vel = 0.55 + 0.25 * rng.random() - (0.15 if s8 % 2 else 0)
            add(keys, epiano(midi_hz(base + octv + root + iv), BEAT * 1.6, vel), t0 + s8 * BEAT / 2 + rng.normal(0, 0.006))
        add(low, bass(midi_hz(base - 12 + root), BEAT * 1.9), t0)
        add(low, 0.7 * bass(midi_hz(base - 12 + root + (7 if b % 2 else 0)), BEAT * 1.9), t0 + 2 * BEAT)
        if b >= 4 and (b // 8) % 4 != 3:  # 輕的節奏，每隔一段休息
            add(perc, 0.9 * kick(), t0); add(perc, 0.6 * kick(), t0 + 2.5 * BEAT)
            for q in range(4):
                add(perc, 0.25 * shaker(rng), t0 + q * BEAT + BEAT / 2)
    chimes = np.zeros(n)
    for st in chime_times:
        add(chimes, chime(midi_hz(base + 36 + 7)), st + 0.05)
    mono_keys = reverb(keys, rng, wet=0.32)
    L = 0.55 * pad_l + 0.25 * pad_r + 0.55 * mono_keys + 0.7 * low + 0.35 * perc + 0.22 * reverb(chimes, rng, wet=0.4)
    R = 0.25 * pad_l + 0.55 * pad_r + 0.50 * mono_keys + 0.7 * low + 0.35 * perc + 0.22 * reverb(chimes, rng, wet=0.4)
    st = np.stack([L, R], 1)
    st = sosfilt(butter(2, 6500, btype='low', fs=SR, output='sos'), st, axis=0)  # 壓掉高頻，聽起來比較柔
    fi, fo = int(2.0 * SR), int(3.5 * SR)
    st = st[:int(total * SR) + int(0.5 * SR)]
    st[:fi] *= np.linspace(0, 1, fi)[:, None]
    st[-fo:] *= np.linspace(1, 0, fo)[:, None]
    st /= np.max(np.abs(st)) / 0.8
    return st.astype(np.float32)


def probe(path, entries, stream=None):
    cmd = ['ffprobe', '-v', 'error'] + (['-select_streams', stream] if stream else []) + ['-show_entries', entries, '-of', 'csv=p=0', path]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()


def volume(path, extra=()):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', path, *extra, '-vn', '-af', 'volumedetect', '-f', 'null', '-'], capture_output=True, text=True).stderr
    m = re.search(r'mean_volume: ([-\d.]+) dB', r); x = re.search(r'max_volume: ([-\d.]+) dB', r)
    return (float(m.group(1)), float(x.group(1))) if m and x else (None, None)


def main():
    ap = argparse.ArgumentParser(description='替影片加上背景音樂')
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--key', type=int, required=True, help='調性 0–11')
    ap.add_argument('--seed', type=int, required=True, help='亂數種子')
    ap.add_argument('--chimes', default='', help='提示音的秒數，用逗號分隔')
    a = ap.parse_args()
    if os.path.abspath(a.src) == os.path.abspath(a.dst):
        sys.exit('輸入和輸出不能是同一個檔案')
    if not 0 <= a.key <= 11:
        sys.exit('--key 要在 0 到 11 之間')
    total = float(probe(a.src, 'format=duration') or 0)
    if total <= 0:
        sys.exit(f'讀不到影片長度：{a.src}')
    has_voice = bool(probe(a.src, 'stream=index', 'a'))
    chimes = [float(x) for x in a.chimes.split(',') if x.strip()]
    os.makedirs(os.path.dirname(os.path.abspath(a.dst)), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, 'music.wav')
        wavfile.write(wav, SR, make(total, a.key, a.seed, chimes))
        fmt = 'aformat=sample_rates=48000:channel_layouts=stereo'
        if has_voice:
            # 人聲和音樂各自標準化；有人聲時用 sidechain 把音樂壓低
            fc = (f'[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,{fmt},asplit=2[v][vsc];'
                  f'[1:a]loudnorm=I=-26:TP=-4,{fmt}[m0];'
                  '[m0][vsc]sidechaincompress=threshold=0.03:ratio=3:attack=30:release=500[m];'
                  '[v][m]amix=inputs=2:normalize=0:duration=first[a]')
        else:
            fc = f'[1:a]loudnorm=I=-20:TP=-2:LRA=11,{fmt}[a]'
        subprocess.check_call(['ffmpeg', '-v', 'error', '-y', '-i', a.src, '-i', wav, '-filter_complex', fc,
                               '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k', '-ar', '48000',
                               '-t', f'{total:.3f}', '-movflags', '+faststart', a.dst])
    mean, peak = volume(a.dst)
    print(f'{a.dst}  {total:.1f} 秒  {"人聲＋音樂" if has_voice else "只有音樂"}  key={a.key} seed={a.seed}')
    print(f'成品音量：平均 {mean} dB、最大 {peak} dB')


if __name__ == '__main__':
    main()
