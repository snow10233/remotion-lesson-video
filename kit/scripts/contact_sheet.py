"""把多張截圖拼成縮圖總表。用法：contact_sheet.py <清單檔> <輸出.jpg> <欄數>
清單檔每行：圖片路徑<TAB>標籤"""
import sys
from PIL import Image, ImageDraw, ImageFont

lst, out, cols = sys.argv[1], sys.argv[2], int(sys.argv[3])
items = [l.split("\t") for l in open(lst, encoding="utf-8").read().splitlines() if l.strip()]
TW, TH, LH = 640, 360, 30
rows = (len(items) + cols - 1) // cols
sheet = Image.new("RGB", (cols * TW, rows * (TH + LH)), (20, 20, 20))
draw = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
except OSError:
    font = ImageFont.load_default()
for i, (p, label) in enumerate(items):
    im = Image.open(p).convert("RGB").resize((TW, TH))
    x, y = (i % cols) * TW, (i // cols) * (TH + LH)
    sheet.paste(im, (x, y + LH))
    draw.text((x + 8, y + 4), label, fill=(255, 230, 120), font=font)
sheet.save(out, quality=85)
