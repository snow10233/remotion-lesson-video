"""在 Colab kernel 裡背景啟動 IndexTTS2 生成，立刻返回。由 run.sh 用 `colab exec -f` 執行。
事先要上傳到 /content：ref15.wav、script_tts.txt、gen_script.py、verify_ckpt.py。
狀態寫在 /content/voice_run.log（INSTALL_DONE → VOICE_DONE，失敗是 VOICE_FAIL）；生成的詳細輸出在 /content/gen.log。
"""
import subprocess

# 不透過 shell 執行 pgrep：不然 shell 自己的指令列也含有這個檔名，會永遠判定成「正在跑」
if subprocess.run(["pgrep", "-f", "bash /content/_voice_run.sh"], capture_output=True).stdout.strip():
    print("ALREADY_RUNNING")
else:
    cmd = r"""
export HF_HUB_DISABLE_XET=1
cd /content
fail() { echo "$1"; tail -n 40 /content/gen.log 2>/dev/null; echo VOICE_FAIL; exit 1; }
pip install -q -U uv || fail "uv install failed"
[ -d index-tts ] || git clone -q --depth 1 https://github.com/index-tts/index-tts.git || fail "clone failed"
cd index-tts && uv sync -q || fail "uv sync failed"
ok=0
for t in 1 2 3; do
  uv run python -c "from huggingface_hub import snapshot_download as s; s('IndexTeam/IndexTTS-2', local_dir='checkpoints_2')" 2>&1 | tail -n 1
  if uv run python /content/verify_ckpt.py checkpoints_2 > /content/verify.log 2>&1; then ok=1; break; fi
done
[ $ok = 1 ] || { cat /content/verify.log; fail "checkpoint download failed"; }
echo INSTALL_DONE
uv run python /content/gen_script.py /content/script_tts.txt /content/final > /content/gen.log 2>&1 || fail "generation failed"
echo VOICE_DONE
"""
    open("/content/_voice_run.sh", "w", encoding="utf-8").write(cmd)
    subprocess.Popen("setsid nohup bash /content/_voice_run.sh > /content/voice_run.log 2>&1 < /dev/null &", shell=True)
    print("LAUNCHED")
