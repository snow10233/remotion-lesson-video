"""在 Colab L4 上對一批音檔做辨識＋逐字對齊（Qwen3-ASR、Qwen3-ForcedAligner），結果下載回本機。
用法：python3 asr.py <輸入資料夾> <輸出.json> [--lang Chinese|English] [--session lessonasr] [--keep] [--budget 秒]
  輸入資料夾：tts.txt（每行 `編號<TAB>要念的文字`，拼音標記要先換回漢字）和 wav/<編號>.wav
  --keep：做完不關 VM（同一個流程還要再跑時用；最後一定要有一次不加 --keep，或自己 colab stop）
可以中斷後重跑：VM 上的工作在背景跑，重跑會接著等；輸出檔已經在就直接結束。
結束碼：0 完成；75 時間（--budget）到了還沒做完，重跑同一條指令會接續；2 開不到 VM，等幾分鐘重跑；1 失敗（印出原因）。
"""
import argparse, hashlib, os, re, subprocess, sys, tarfile, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("inp"); ap.add_argument("out")
ap.add_argument("--lang", default="Chinese"); ap.add_argument("--session", default="lessonasr")
ap.add_argument("--keep", action="store_true"); ap.add_argument("--budget", type=float, default=0)
a = ap.parse_args()
T0 = time.time()
INP, OUT, S = Path(a.inp).resolve(), Path(a.out).resolve(), a.session
JOB = hashlib.sha1(str(OUT).encode()).hexdigest()[:10]
RJ = f"/content/asrjobs/{JOB}"
os.environ["PATH"] = os.path.expanduser("~/.local/bin") + ":" + os.environ["PATH"]


def over():
    return a.budget and time.time() - T0 > a.budget


def colab(*args, timeout=180):
    try:
        r = subprocess.run(["colab", *args], capture_output=True, text=True, timeout=timeout)
        return r.returncode, "\n".join(l for l in (r.stdout + r.stderr).splitlines() if "keyring" not in l)
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def rexec(code, timeout=150, tries=4):
    """在 VM 上跑一段 Python，連線斷掉就重試；回傳輸出"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code); fn = f.name
    try:
        for _ in range(tries):
            rc, o = colab("exec", "-s", S, "--timeout", "0", "-f", fn, timeout=timeout)
            if "Connection was lost" in o or "Read timed out" in o or rc == 124:
                time.sleep(5); continue
            return o
        return "EXEC_FAILED"
    finally:
        os.unlink(fn)


def stop():
    if not a.keep:
        print(colab("stop", "-s", S)[1].splitlines()[-1:])


if OUT.exists():
    print("已經有結果：", OUT); sys.exit(0)
if not (INP / "tts.txt").exists():
    print("找不到", INP / "tts.txt"); sys.exit(1)

if S not in colab("sessions", timeout=60)[1]:
    print(f"開新的 Colab session {S}（L4）", flush=True)
    rc, o = colab("new", "-s", S, "--gpu", "L4", timeout=400)
    if S not in colab("sessions", timeout=60)[1]:
        print(o[-500:]); print("開不到 VM（多半是 L4 暫時沒有空位），等幾分鐘重跑同一條指令"); sys.exit(2)

st = rexec(f"""import os, subprocess
ready = os.path.exists('/content/.asr_ready')
print('READY' if ready else 'NOTREADY')
d = '{RJ}'
if os.path.exists(d + '/out.json'): print('JOB DONE')
elif os.path.exists(d + '/FAILED'): print('JOB FAILED'); print(open(d + '/FAILED').read()[-3000:])
elif subprocess.run(['pgrep', '-f', 'asr_job.py ' + d], capture_output=True).stdout.strip(): print('JOB RUNNING')
else: print('JOB NONE')
""")
if "NOTREADY" in st:
    print("在 VM 上安裝 qwen-asr…", flush=True)
    o = rexec("""import subprocess
r = subprocess.run('pip install -q -U qwen-asr && touch /content/.asr_ready', shell=True, capture_output=True, text=True)
print(r.returncode, r.stderr[-1500:])""", timeout=900)
    if "READY_OK" not in rexec("import os; print('READY_OK' if os.path.exists('/content/.asr_ready') else 'NO')"):
        print("安裝失敗：", o[-1500:]); sys.exit(1)
if "JOB FAILED" in st:
    print(st); sys.exit(1)
if "JOB NONE" in st:
    with tempfile.TemporaryDirectory() as td:
        tgz = Path(td) / "in.tgz"
        with tarfile.open(tgz, "w:gz") as tf:
            tf.add(INP / "tts.txt", "tts.txt"); tf.add(INP / "wav", "wav")
        rexec(f"import os; os.makedirs('{RJ}', exist_ok=True)")
        for _ in range(3):
            rc, o = colab("upload", "-s", S, str(tgz), f"{RJ}/in.tgz", timeout=600)
            if rc == 0: break
        rc2, o2 = colab("upload", "-s", S, str(HERE / "asr_job.py"), "/content/asr_job.py")
        if rc or rc2: print("上傳失敗：", o, o2); sys.exit(1)
    o = rexec(f"""import subprocess
subprocess.run('cd {RJ} && tar xzf in.tgz && setsid nohup python3 /content/asr_job.py {RJ} {a.lang} > {RJ}/log 2>&1 < /dev/null &', shell=True)
print('LAUNCHED')""", timeout=120)
    print("已在 VM 背景開始辨識", flush=True)

while True:
    st = rexec(f"""import os
d = '{RJ}'
print('JOB DONE' if os.path.exists(d + '/out.json') else 'JOB FAILED' if os.path.exists(d + '/FAILED') else 'JOB WAIT')
if os.path.exists(d + '/FAILED'): print(open(d + '/FAILED').read()[-3000:])
if os.path.exists(d + '/log'): print('LOG', open(d + '/log').read().strip().splitlines()[-1:])
""")
    if "JOB DONE" in st: break
    if "JOB FAILED" in st:
        print(st); stop(); sys.exit(1)
    print(time.strftime("%H:%M:%S"), (re.findall(r"LOG .*", st) or [""])[0], flush=True)
    if over():
        print("時間到了，還沒做完；重跑同一條指令會接續"); sys.exit(75)
    time.sleep(15)

OUT.parent.mkdir(parents=True, exist_ok=True)
tmp = OUT.with_suffix(".part")
for _ in range(3):
    rc, o = colab("download", "-s", S, f"{RJ}/out.json", str(tmp), timeout=300)
    if rc == 0 and tmp.exists(): break
else:
    print("下載失敗：", o); sys.exit(1)
tmp.rename(OUT)
print("完成：", OUT)
stop()
