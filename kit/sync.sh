#!/bin/bash
# 把共用工具包（kit）同步到影片專案。kit 是這些檔案唯一的正本：共用工具要改，先改 kit 再同步。
# 用法：bash sync.sh <專案資料夾> [--force]
#   新專案：template/ 的設定檔只在專案裡沒有時才複製，接著照常裝套件（npm install）。
#   專案裡的共用檔跟 kit 不同時會列出來並停下來：先判斷差異該不該搬回 kit；確定要用 kit 的版本覆蓋就加 --force。
set -euo pipefail
[ $# -ge 1 ] || { sed -n '2,5p' "$0"; exit 64; }
KIT=$(cd "$(dirname "$0")" && pwd); FORCE=${2:-}
mkdir -p "$1"; P=$(cd "$1" && pwd)
cd "$KIT/template"
for f in $(find . -type f | sed 's|^\./||'); do
  [ -e "$P/$f" ] || { mkdir -p "$P/$(dirname "$f")"; cp "$f" "$P/$f"; echo "新增設定 $f"; }
done
cd "$KIT"
diff_list=()
for f in $(find src scripts -type f); do
  if [ -e "$P/$f" ] && ! cmp -s "$f" "$P/$f"; then diff_list+=("$f"); fi
done
if [ ${#diff_list[@]} -gt 0 ] && [ "$FORCE" != "--force" ]; then
  echo "專案裡這些共用檔跟 kit 不一樣（diff -u $KIT/<檔> $P/<檔> 看差異）："
  printf '  %s\n' "${diff_list[@]}"
  echo "沒有覆蓋任何檔案。確定用 kit 的版本：bash $0 $P --force"
  exit 1
fi
n=0
for f in $(find src scripts -type f); do
  cmp -s "$f" "$P/$f" 2>/dev/null && continue
  mkdir -p "$P/$(dirname "$f")"; cp "$f" "$P/$f"; echo "同步 $f"; n=$((n + 1))
done
echo "完成，更新了 $n 個檔案"
