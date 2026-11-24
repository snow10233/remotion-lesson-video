#!/bin/bash
# 在 Colab L4 上用 IndexTTS2 把 TTS 稿生成語音，完成一段就下載一段，全部到齊後關掉 VM。
#
# 用法：bash run.sh <TTS稿> <輸出資料夾> <聲音> [session 名稱=lessonvoice]
#       bash run.sh --voices        列出可以選的聲音
#   TTS 稿：每行 `段號<TAB>內容`（tts-prep 產生的格式）
#   輸出：<輸出資料夾>/<段號>.wav（22050 Hz 單聲道）
#   聲音：skill 的 assets/voices/ 裡的檔名（不含副檔名），或任何一個音檔的路徑。
#         只會用到音檔的前 15 秒；格式不限，腳本會自己轉成模型要的格式。
#         用哪個聲音由使用者決定，這裡沒有預設值。
#
# 可以中斷後重跑：本機已經有的段落不會重做。電腦睡眠、斷線、VM 被回收都一樣，再跑一次同一條指令就會接續。
# 要重做某幾段：刪掉本機那幾個 wav 再跑一次。
# 同一個輸出資料夾只能用同一個聲音（記在 <輸出資料夾>/voice.txt）；要換聲音就換一個資料夾，或把舊的音檔和 voice.txt 刪掉。
# 結束碼：0 全部完成；1 生成失敗（VM 留著方便查）；2 開不到 VM 或 VM 不見了；3 等太久；4 生成結束但缺段落。1 以外重跑同一條指令即可。
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
VOICES=$(cd "$HERE/../../assets/voices" && pwd)
voices() { ls "$VOICES" | sed 's/\.[^.]*$//' | sed 's/^/  /'; }
if [ "${1:-}" = "--voices" ]; then echo "可以選的聲音（$VOICES）："; voices; exit 0; fi
[ $# -ge 3 ] || { sed -n '2,14p' "$0"; exit 64; }
SCRIPT=$1; OUT=$2; VOICE=$3; S=${4:-lessonvoice}
export PATH="$HOME/.local/bin:$PATH"
[ -s "$SCRIPT" ] || { echo "找不到 TTS 稿：$SCRIPT"; exit 64; }
command -v colab >/dev/null || { echo "找不到 colab 指令（見 colab-cli skill）"; exit 64; }
if [ -f "$VOICE" ]; then SRC=$VOICE; else SRC=$(ls "$VOICES"/"$VOICE".* 2>/dev/null | head -n 1); fi
[ -n "${SRC:-}" ] && [ -s "$SRC" ] || { echo "找不到聲音「$VOICE」。可以選的："; voices; exit 64; }
VNAME=$(basename "$SRC"); VNAME=${VNAME%.*}
mkdir -p "$OUT"
if [ -s "$OUT/voice.txt" ] && [ "$(cat "$OUT/voice.txt")" != "$VNAME" ]; then
  echo "這個資料夾的音檔是用「$(cat "$OUT/voice.txt")」生成的，這次指定的是「$VNAME」。混用會讓同一支影片出現兩種聲音。"
  echo "要換聲音：換一個輸出資料夾，或刪掉這裡的 wav 和 voice.txt。"; exit 64
fi
echo "$VNAME" > "$OUT/voice.txt"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
REF=$TMP/ref15.wav   # 模型只用參考音的前 15 秒
ffmpeg -y -v error -i "$SRC" -t 15 -ac 1 -ar 24000 "$REF" || { echo "無法讀取聲音檔：$SRC"; exit 64; }
echo "聲音：$VNAME"

c() { local t=$1; shift; timeout "$t" colab "$@" 2>&1 | grep -av keyring; }
ids() { awk '/^## /{exit} /^[0-9][0-9][0-9]\t./{print substr($0,1,3)}' "$SCRIPT"; }
missing() { for i in $(ids); do [ -s "$OUT/$i.wav" ] || echo "$i"; done; }
count() { echo $#; }
status() { c 100 exec -s "$S" --timeout 0 -f "$HERE/status.py"; }
pull() {   # 把 VM 上已完成、本機還沒有的段落下載回來
  local id f
  for id in $(echo "$1" | grep -a '^DONE ' | cut -d' ' -f2); do
    f="$OUT/$id.wav"
    [ -s "$f" ] && continue
    echo " $(ids) " | tr '\n' ' ' | grep -q " $id " || continue
    timeout 100 colab download -s "$S" "/content/final/$id.wav" "$f" >/dev/null 2>&1
    ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" >/dev/null 2>&1 || rm -f "$f"
  done
}
finish() {
  echo "全部 $(count $(ids)) 段都在 $OUT"
  c 100 stop -s "$S" | tail -n 1
  c 60 sessions | tail -n 3
  exit 0
}

TOTAL=$(count $(ids))
[ "$TOTAL" -gt 0 ] || { echo "TTS 稿裡沒有 段號<TAB>內容 的行"; exit 64; }
if [ -z "$(missing)" ]; then echo "全部 $TOTAL 段本機都已經有了，不需要生成"; exit 0; fi

if c 60 sessions | grep -qw -- "$S"; then
  echo "沿用現有的 session $S"
  st=$(status); pull "$st"
else
  echo "開新的 Colab session $S（L4）"
  c 300 new -s "$S" --gpu L4 | tail -n 2
  if ! c 60 sessions | grep -qw -- "$S"; then
    echo "開不到 VM（多半是 L4 暫時沒有空位），等幾分鐘重跑同一條指令"; exit 2
  fi
  st=$(status)
fi
[ -z "$(missing)" ] && finish

if ! echo "$st" | grep -q '^RUNNING 1'; then
  # 只送本機還缺的段落
  awk -v need=" $(missing | tr '\n' ' ')" '/^## /{exit} /^[0-9][0-9][0-9]\t./{ if (index(need, " " substr($0,1,3) " ")) print }' "$SCRIPT" > "$TMP/script_tts.txt"
  echo "要生成 $(wc -l < "$TMP/script_tts.txt") 段（共 $TOTAL 段）"
  up() { c 180 upload -s "$S" "$1" "/content/$2" | tail -n 1; }
  up "$REF" ref15.wav; up "$TMP/script_tts.txt" script_tts.txt; up "$HERE/gen_script.py" gen_script.py; up "$HERE/verify_ckpt.py" verify_ckpt.py
  ok=0
  for try in 1 2 3 4; do
    r=$(c 150 exec -s "$S" --timeout 0 -f "$HERE/launch.py")
    if echo "$r" | grep -q 'LAUNCHED\|ALREADY_RUNNING'; then ok=1; break; fi
    sleep 5
    status | grep -q '^RUNNING 1' && { ok=1; break; }
    echo "啟動沒有成功（第 $try 次）：$(echo "$r" | tail -n 1)"
  done
  [ $ok = 1 ] || { echo "無法啟動生成"; exit 1; }
  echo "已在 VM 背景開始生成"
fi

quiet=0
for i in $(seq 1 360); do
  sleep 20
  st=$(status); pull "$st"
  left=$(count $(missing))
  echo "$(date +%H:%M:%S) 本機 $((TOTAL - left))/$TOTAL $(echo "$st" | grep -a '^STATE' | tr '\n' ' ')"
  [ "$left" = 0 ] && finish
  if echo "$st" | grep -qi 'session .* not found\|No active sessions'; then echo "VM 不見了，重跑同一條指令會開新的並接續"; exit 2; fi
  if echo "$st" | grep -q 'STATE VOICE_FAIL'; then echo "$st" | tail -n 45; echo "生成失敗，VM 還開著（session $S），查完記得 colab stop -s $S"; exit 1; fi
  if echo "$st" | grep -q 'STATE VOICE_DONE'; then
    quiet=$((quiet + 1))
    [ $quiet -ge 3 ] && { echo "生成已結束，但還缺：$(missing | tr '\n' ' ')"; exit 4; }
  fi
done
echo "等了兩小時還沒完成，重跑同一條指令可以接續"; exit 3
