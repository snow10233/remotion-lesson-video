#!/bin/bash
# 在本機安裝 Montreal Forced Aligner（MFA）和中文模型，給 check_reading.py 用。可以重複執行，裝好的會跳過。
# 位置：~/.local/share/lesson-video/mfa/（micromamba、conda 環境、模型），大約 2.5 GB。
# 用法：bash setup.sh        印出最後一行 MFA_READY 表示可以用
set -euo pipefail
R=${LESSON_MFA_HOME:-$HOME/.local/share/lesson-video/mfa}
mkdir -p "$R/bin"
export MAMBA_ROOT_PREFIX="$R/mamba" MFA_ROOT_DIR="$R/root"
if [ ! -x "$R/bin/micromamba" ]; then
  echo "下載 micromamba"
  curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C "$R" bin/micromamba
fi
if ! "$R/env/bin/mfa" version >/dev/null 2>&1; then
  echo "建立 MFA 環境（第一次大約 3 到 5 分鐘）"
  rm -rf "$R/env"
  "$R/bin/micromamba" create -y -q -p "$R/env" -c conda-forge montreal-forced-aligner pip >/dev/null
fi
if ! "$R/env/bin/python" -c "import spacy_pkuseg, dragonmapper, hanziconv" 2>/dev/null; then
  echo "安裝中文斷詞套件"   # MFA 的中文模型需要；conda-forge 沒有，用 pip 裝
  "$R/env/bin/python" -m pip install -q spacy-pkuseg dragonmapper hanziconv
fi
export PATH="$R/env/bin:$PATH"
[ -f "$MFA_ROOT_DIR/pretrained_models/acoustic/mandarin_mfa.zip" ] || mfa model download acoustic mandarin_mfa >/dev/null
[ -f "$MFA_ROOT_DIR/pretrained_models/dictionary/mandarin_mfa.dict" ] || mfa model download dictionary mandarin_mfa >/dev/null
echo "MFA $(mfa version 2>/dev/null | tail -1) 在 $R"
echo MFA_READY
