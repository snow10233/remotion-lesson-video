#!/bin/bash
# 算出成品：無聲算圖 → 照時間軸拼配音音軌 → 合併 → 加背景音樂。
# 用法：bash scripts/render.sh <composition> <key 0-11> <seed> [輸出名稱，預設 composition]
# 輸出：out/<名稱>.mp4（成品）；中間檔 out/<名稱>-muted.mp4、-voice.wav、-render.mp4 留著，之後只換音樂不用重算畫面。
#
# 為什麼不讓 Remotion 自己混音：它會把每個音檔補成整支影片那麼長，句子一多就塞爆 /tmp（tmpfs）。
set -euo pipefail
[ $# -ge 3 ] || { sed -n '2,6p' "$0"; exit 64; }
COMP=$1; KEY=$2; SEED=$3; NAME=${4:-$1}
cd "$(dirname "$0")/.."
SKILL=${LESSON_SKILL:-$HOME/.claude/skills/remotion-lesson-video}
mkdir -p out
cleanup() { find /tmp -maxdepth 1 -name 'remotion-*' -exec rm -rf {} + 2>/dev/null || true; }
trap cleanup EXIT
npx remotion render src/index.ts "$COMP" "out/$NAME-muted.mp4" --muted --concurrency=6 --crf=20 --log=error
node scripts/voice_track.mjs "$COMP" "out/$NAME-voice.wav"
ffmpeg -loglevel error -y -i "out/$NAME-muted.mp4" -i "out/$NAME-voice.wav" -map 0:v -map 1:a \
  -c:v copy -c:a aac -b:a 192k -ar 48000 -shortest "out/$NAME-render.mp4"
CHIMES=$(node scripts/scene_starts.mjs "$COMP" | tail -1)
uv run "$SKILL/scripts/add_music.py" "out/$NAME-render.mp4" "out/$NAME.mp4" --key "$KEY" --seed "$SEED" --chimes "$CHIMES"
ffprobe -v error -show_entries stream=codec_type,width,height,r_frame_rate:format=duration -of compact "out/$NAME.mp4"
echo "RENDER_DONE out/$NAME.mp4"
