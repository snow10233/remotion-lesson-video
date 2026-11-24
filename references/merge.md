# 4. 合併：接上配音、審核、算圖

## 接上配音

配音子代理回報後：

```bash
uv run -q --with numpy python3 scripts/audio_meta.py <影片 id> tts/<影片>/final [tts/<影片>/fix1/final ...]
```

- 它把音檔複製到 `public/audio/<影片>/<旁白 id>.wav`、讀實際長度，並用 `final/align.json` 把每個「｜」放在後面那個字開口的時間，寫出 `src/videos/<影片>/audio.json`，整支時間軸自動重排。重跑前先把舊的 `audio.json` 存成 `audio.prev.json`，審核時要比對。
- 補做批次放在後面，會覆蓋前面的同一句。
- 印出「旁白改過了，要重配」時：旁白在定稿後被改了字，照「補做」處理，不要把舊音檔配到新句子上。
- 印出「字數對不上，改用停頓猜測」的句子，通常是念法表把符號改寫成好幾個字（例如 n² → n 的平方）；這些句子的動作點比較不準，審核時多看一眼。

## 接上配音後的審核

時間變了，動作點的位置和過渡中的畫面都會跟著變，所以要再審一次，流程同 [`visuals.md`](visuals.md) 的審核迴圈，只是截圖範圍不同：

- 第一次接上配音：`node scripts/review_frames.mjs <composition> --cues-only`（句尾的版面做畫面時審過了）。
- 之後重配或改對時：`node scripts/review_frames.mjs <composition> --moved src/videos/<影片>/audio.prev.json`，只看移動超過 0.3 秒的動作點。

**完成**：子代理列出、經你確認為真的問題都修好，並看過修好後的截圖。

## 算圖和背景音樂

```bash
bash scripts/render.sh <composition> <key 0-11> <seed>
```

- 它先算無聲畫面，再照時間軸拼出配音音軌、合併，最後用 skill 的 `scripts/add_music.py` 加背景音樂，在每個場景開頭加一聲很輕的提示音。成品是 `out/<composition>.mp4`，中間檔留著，之後只想換音樂時直接用 `add_music.py` 處理 `out/<composition>-render.mp4`。
- 不讓 Remotion 自己混音：它會把每個音檔補成整支影片長，句子一多就塞爆 `/tmp`。
- 背景音樂是程式合成的，長度自動等於影片；人聲會標準化，有人聲時音樂自動壓低，畫面不重新編碼。
- `key`、`seed` 每支影片換一組（看專案 README 的影片紀錄，挑沒用過的），整個系列聽起來才不會都一樣。
- 算圖大約要二、三十分鐘，用背景執行。要中途停掉時用 PID 停，不要用 `pkill -f` 比對字串：它會連同自己這條指令一起砍掉。

## 交件檢查

- `render.sh` 最後印出的規格：1920×1080、60 fps、有音軌，長度符合時間軸。
- 每句配音都完整放進影片，沒有被切掉、也沒有和下一句重疊：時間軸保證每句長度至少是「配音長度＋0.45 秒」，`audio_meta.py` 有報錯就不算完成。
- 沒有還在背景跑的工作；`colab sessions` 沒有留著的 VM。
- 專案 README 的影片紀錄補上這支：composition、配音人物、背景音樂 key／seed、資料裡的錯誤或特別採用的慣例。

## 補做（旁白定稿後改字、或使用者回報念錯）

1. 照 [`voice.md`](voice.md) 的「重配某幾句」建補做批次、配音。
2. 回到「接上配音」：`audio_meta.py` 依序給 `final` 和補做批次的 `final`。
3. 審核用 `--moved`，再算圖。
