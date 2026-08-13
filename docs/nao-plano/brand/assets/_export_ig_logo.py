from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

out = Path(__file__).resolve().parent
SIZE = 1080

font_candidates = [
    r"C:\Windows\Fonts\Inter-SemiBold.ttf",
    r"C:\Windows\Fonts\Inter.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\seguisb.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
]
font_path = next((p for p in font_candidates if Path(p).exists()), None)
print("font:", font_path)


def make(name: str, bg: str, fg: str, text: str, size_ratio: float) -> None:
    img = Image.new("RGB", (SIZE, SIZE), bg)
    draw = ImageDraw.Draw(img)
    font_size = int(SIZE * size_ratio)
    font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (SIZE - tw) / 2 - bbox[0]
    y = (SIZE - th) / 2 - bbox[1] + (SIZE * 0.015 if text == "R" else 0)
    draw.text((x, y), text, font=font, fill=fg)
    path = out / name
    img.save(path, "PNG", optimize=True)
    print("wrote", path)


for args in [
    ("revy-instagram-word-dark.png", "#0A0A0A", "#FFFFFF", "Revy", 0.20),
    ("revy-instagram-word-light.png", "#FFFFFF", "#0A0A0A", "Revy", 0.20),
    ("revy-instagram-mark-dark.png", "#0A0A0A", "#FFFFFF", "R", 0.46),
    ("revy-instagram-mark-light.png", "#FFFFFF", "#0A0A0A", "R", 0.46),
]:
    make(*args)

print("done")
