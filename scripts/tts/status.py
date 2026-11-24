"""印出生成進度。由 run.sh 用 `colab exec -f` 執行。
DONE <段號>：這段已經生成完（gen_script.py 寫完才改名成 <段號>.wav，所以存在就是完整的）。
"""
import glob, os, subprocess
for p in sorted(glob.glob("/content/final/[0-9][0-9][0-9].wav")):
    if os.path.getsize(p) > 0:
        print("DONE " + os.path.basename(p)[:-4])
running = bool(subprocess.run(["pgrep", "-f", "bash /content/_voice_run.sh"], capture_output=True).stdout.strip())
print("RUNNING", int(running))
if os.path.exists("/content/voice_run.log"):
    log = open("/content/voice_run.log", encoding="utf-8", errors="replace").read()
    for k in ("INSTALL_DONE", "VOICE_DONE", "VOICE_FAIL"):
        if k in log:
            print("STATE", k)
    if "VOICE_FAIL" in log:
        print("---- voice_run.log ----")
        print(log[-3000:])
print("STATUS_END")
