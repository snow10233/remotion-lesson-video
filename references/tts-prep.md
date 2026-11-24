# TTS 稿準備

把給人看的逐字稿，變成給 TTS 照念的 **TTS 稿**：標點只剩 ，。？！、數字與符號都寫成要念的字、已知的破音字寫成拼音、內容一字不改。

- **做影片時**：配音子代理照這份做（brief 在 [`voice.md`](voice.md)）。
- **單獨整理逐字稿時**：主模型派一個子代理照這份做（`subagent_type: "general-purpose"`，`model: "sonnet"`，`effort: "high"`），brief 寫明原稿路徑、輸出路徑，以及「照 `references/tts-prep.md` 做，回報檢查結果和待確認清單」。輸出預設放在原稿旁的 `tts/<原稿檔名>_tts.txt`。

用到的檔案（都在 `~/.claude/skills/remotion-lesson-video/`）：
- `references/tts-rules.md`：改寫規則。
- `references/tts-glossary.md`：念法表，使用者已決定的念法，跨影片累積。
- `scripts/check_tts_text.py`：驗證腳本。
- `references/tts-models.md`：各 TTS 模型的設定與限制（換模型時才需要）。

## 步驟

### 1. 讀規則和原稿

完整讀 `tts-rules.md`、`tts-glossary.md` 和原稿。原稿是 UTF-8 文字檔：段落之間空一行，第一段是標題（不念）。
**完成**：知道要念的段數（原稿段數減一）和輸出路徑。

### 2. 改寫

照規則一段一段改寫，寫到輸出檔：每段一行 `段號<TAB>內容`，最後接 `## 待確認`。念法表有的照念法表；規則沒涵蓋或沒把握的照原文保留，列進 `## 待確認`，不用問任何人。成品有念錯的地方，使用者會當 bug 回報，再補進念法表。
**完成**：輸出檔的段數等於要念的段數。

### 3. 檢查

```bash
python3 ~/.claude/skills/remotion-lesson-video/scripts/check_tts_text.py <輸出檔> <原稿>
```

它檢查字元、段號、內容有沒有被改動、**破音字**（念法表裡有固定寫法的還留著漢字就報錯；要看語意的列在「提醒」，逐條判斷，是念法表說的用法就改），以及**數字**：原稿的每個數字換算成數值，要在 TTS 稿裡出現一樣多次、一樣大（「4.1」→「四點一」、「1/2」→「二分之一」都算對）。報錯就修到通過。
**完成**：印出「全部通過」、結束碼 0。

### 4. 繁體或簡體

預設用繁體送 TTS（2026-11 盲測：四個模型裡三個繁體分數較高）。使用者要簡體時才跑：
`cd <輸出資料夾> && uv run -q --with opencc python3 ~/.claude/skills/remotion-lesson-video/scripts/to_simplified.py <TTS稿檔名>`
產生 `<檔名>_簡.txt`，再用檢查腳本驗一次（不帶原稿參數）。
