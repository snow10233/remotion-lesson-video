# 3A. 配音

配音整段交給一個子代理：旁白 → TTS 稿 → 生成 → 辨識品質迴圈，主模型只派工和讀結果。下面的路徑都相對於 `~/.claude/skills/remotion-lesson-video/`。

## 派工

旁白匯出（`tts/<影片>/src.txt`、`map.json`、`narration.json`）之後，用 Agent 工具在背景派：`subagent_type: "general-purpose"`，`model: "sonnet"`，`effort: "high"`，brief 如下（填入角括號）：

> 你負責一支教學影片的配音，從旁白一路做到可以接回影片的音檔，中途不要停下來問問題。批次資料夾：`<專案>/tts/<影片>`。聲音：`<聲音名稱>`。語言：`<zh 或 en>`。
> 1. **改寫成 TTS 稿**：照 `~/.claude/skills/remotion-lesson-video/references/tts-prep.md` 把 `src.txt` 改寫成同一個資料夾的 `tts.txt`，跑它寫的檢查直到通過。念法沒把握的照原文保留，寫進 `tts.txt` 最後的 `## 待確認`，不用問任何人。
> 2. **生成＋品質迴圈**：跑 `python3 ~/.claude/skills/remotion-lesson-video/scripts/voice_qc.py <批次資料夾> --voice <聲音名稱> --lang <zh 或 en> --budget 540`（Bash timeout 設 600000）。結束碼 75 表示還沒做完，重跑同一條指令會接續，一直重跑到結束碼 0。結束碼 1 時讀它印的訊息：Colab 要求登入或授權時停下來回報，不要自己處理；其他錯誤修得了就修，修不了就回報。
> 3. **回報**（不用貼稿子和報告全文）：`final/` 的路徑、`final/REPORT.md` 裡「要請人聽的句子」的數量、`## 待確認` 的條目、過程中遇到的錯誤。

派出去之後就去做畫面（3B）。它通常要 30 分鐘到 1 小時以上（生成時間大約是音檔長度的 1.5 倍，加上重做候選和辨識）。

## voice_qc.py 做了什麼

用法和結束碼寫在腳本開頭的說明。流程：

1. `scripts/tts/run.sh`：在 Colab L4 上用 IndexTTS2 生成，一句一個 wav（22050 Hz 單聲道）→ `wav/`。
2. `scripts/asr/asr.py`：另一台 L4 上用 Qwen3-ASR 辨識、Qwen3-ForcedAligner 逐字對齊。實測中文錯字率約 1.2%（Whisper large-v3-turbo 約 4.8%，而且中文給不出逐字時間），20 分鐘的音檔辨識加對齊大約 1 分鐘。
3. 找問題：
   - **念法不同**：辨識結果和稿子比讀音，同音字（它／他、聯／連）不算。
   - **破音字念錯**：稿子裡寫成拼音的字（念法表的破音字），用本機的 Montreal Forced Aligner 確認實際念的讀音（`scripts/mfa/check_reading.py`）。辨識模型只看得到漢字，「第五行」念成 xíng 它照樣寫「行」，抓不到，所以需要這一步。第一次用會自動安裝 MFA 到 `~/.local/share/lesson-video/mfa/`（約 2.5 GB），之後 90 句大約 30 秒，不用開 Colab。
   - **該停沒停**：數字或字母旁邊的逗號幾乎沒停（「一，二」聽起來像「一百二」、「從 P，和…」黏在一起）。
   - **停太久**：逗號超過 0.65 秒、句號超過 0.95 秒、沒有標點卻停超過 0.4 秒。
4. 前三種問題的句子重新生成 3 個候選，挑念法對、停頓對、要修改最少的版本，最多 2 輪。生成有隨機性，同一句重做常常就好了。
5. 剪短太長的停頓；數字或字母旁還是沒停的逗號硬插 0.15 到 0.22 秒靜音 → `final/wav/`。
6. `final/` 再辨識一次：逐字時間存成 `final/align.json`（合併時對時用）；補了靜音反而辨識變差的句子退回不補。

輸出在 `<批次>/final/`：`wav/`、`align.json`、`changes.json`、`REPORT.md`（改了什麼、要請人聽的句子），以及複製過來的 `map.json`、`narration.json`。原始生成的音檔留在 `<批次>/wav/`，中間結果在 `<批次>/qc/`。

辨識模型也會聽錯（冷門術語、單一英文字母），所以 REPORT.md 的「念法不同」是**請人聽的清單**，不是判決。重做 6 次都一樣的句子（例如 IndexTTS2 固定把某個組合念成同一種怪音），只能靠改 TTS 稿或念法表解決，等使用者回報。

## 聲音

- 可以選的聲音放在 `assets/voices/`，一個音檔就是一個聲音，檔名就是名字；`bash scripts/tts/run.sh --voices` 會列出來。
- **新增聲音**：音檔放進 `assets/voices/` 就好，格式不限。模型只用前 15 秒，生成的語氣和語速也跟著那 15 秒走，所以那段最好是乾淨、連續的說話聲、沒有背景音樂。使用者拿新音檔來時，先量前 15 秒的靜音有多長，偏多就告訴他。
- 一支影片從頭到尾用同一個聲音。`run.sh` 把聲音記在輸出資料夾的 `voice.txt`，不一致時會停下來。

使用者定過的事，照做、不用重新討論：
- 用繁體送進模型，不轉簡體（盲測繁體較好）。
- 一句旁白一個音檔，整句一次生成，不再拆小段。
- 不做補高頻這類音質後處理。剪掉過長的停頓、補上該有的停頓是時間上的修改，不算在內。
- GPU 用 Colab，不租其他機器。
- IndexTTS2 的取樣參數維持官方預設：temperature 0.1 到 0.8 使用者聽不出差別，調溫度也救不了破音字念錯（2026-11-24，見 `tts-models.md`）。

## 重配某幾句（補做批次）

旁白改了字，或使用者回報某句念錯時，另開一個補做批次，舊批次不動（它的 `qc/` 存著舊稿子的辨識結果和候選，混用會出錯）：

1. 念錯的 bug 先把念法補進 `references/tts-glossary.md`（需要時也補 `tts-rules.md`），這是修 bug 的主要產出，之後每支影片都受益。
2. 把目前的旁白匯出到暫存資料夾：`node scripts/export_tts.mjs <composition> tts/<影片>/export-now`。
3. `python3 scripts/fix_batch.py tts/<影片>/export-now tts/<影片>/fix<N> <旁白 id>...`
4. 對 `fix<N>` 照上面的 brief 派配音子代理（句子少的話主模型自己做也可以）。
5. 合併時 `audio_meta.py` 依序給 `final` 和 `fix<N>/final`，見 [`merge.md`](merge.md)。

單獨整理逐字稿（不做影片）時，只做 brief 的第 1 步，用 `tts-prep.md` 的流程。
