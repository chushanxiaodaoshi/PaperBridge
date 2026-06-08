from pathlib import Path
import json
import textwrap
from PIL import Image, ImageDraw, ImageFont

GROUND_JSON = Path("outputs/grounded_slides.json")
OUT_DIR = Path("outputs/slide_images")

WIDTH = 1920
HEIGHT = 1080

BG = (248, 250, 252)
TITLE_BLUE = (37, 99, 235)
TITLE_BLUE_DARK = (30, 64, 175)
GREEN = (16, 185, 129)
TEXT = (30, 41, 59)
SUBTEXT = (71, 85, 105)
BORDER = (226, 232, 240)
WHITE = (255, 255, 255)


def get_font(size: int, bold: bool = False):
    candidates = []

    if bold:
        candidates += [
            r"C:\Windows\Fonts\msyhbd.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
        ]
    else:
        candidates += [
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simsun.ttc",
            r"C:\Windows\Fonts\arial.ttf",
        ]

    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)

    return ImageFont.load_default()


TITLE_FONT = get_font(42, bold=True)
SECTION_FONT = get_font(26, bold=True)
BODY_FONT = get_font(30, bold=False)
SMALL_FONT = get_font(22, bold=False)
SMALL_BOLD_FONT = get_font(22, bold=True)
FOOTER_FONT = get_font(20, bold=False)


def rounded_box(draw, xy, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def wrap_text(draw, text, font, max_width):
    if not text:
        return []

    lines = []
    for raw_line in str(text).split("\n"):
        if not raw_line.strip():
            lines.append("")
            continue

        current = ""
        for ch in raw_line:
            trial = current + ch
            bbox = draw.textbbox((0, 0), trial, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = ch
        if current:
            lines.append(current)

    return lines


def draw_wrapped_text(draw, x, y, text, font, fill, max_width, line_gap=10):
    lines = wrap_text(draw, text, font, max_width)
    cur_y = y
    for line in lines:
        draw.text((x, cur_y), line, font=font, fill=fill)
        bbox = draw.textbbox((0, 0), line if line else "A", font=font)
        line_h = bbox[3] - bbox[1]
        cur_y += line_h + line_gap
    return cur_y


def draw_bullets(draw, x, y, items, font, fill, max_width, bullet_gap=18, line_gap=10):
    cur_y = y
    for item in items:
        bullet = "• "
        lines = wrap_text(draw, item, font, max_width - 40)

        if not lines:
            continue

        draw.text((x, cur_y), bullet, font=font, fill=fill)
        draw.text((x + 28, cur_y), lines[0], font=font, fill=fill)

        bbox = draw.textbbox((0, 0), lines[0], font=font)
        line_h = bbox[3] - bbox[1]
        cur_y += line_h + line_gap

        for line in lines[1:]:
            draw.text((x + 28, cur_y), line, font=font, fill=fill)
            bbox = draw.textbbox((0, 0), line, font=font)
            line_h = bbox[3] - bbox[1]
            cur_y += line_h + line_gap

        cur_y += bullet_gap

    return cur_y


def render_one_slide(slide: dict, out_path: Path, paper_title: str):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    # 顶部标题栏
    rounded_box(draw, (70, 55, 1850, 165), radius=28, fill=TITLE_BLUE)
    draw.text((105, 88), slide.get("title", f"Slide {slide.get('slide_no', '')}"), font=TITLE_FONT, fill=WHITE)

    # 左上小标签：页码
    rounded_box(draw, (1700, 82, 1815, 134), radius=18, fill=TITLE_BLUE_DARK)
    draw.text((1732, 95), f"P{slide.get('slide_no', '?')}", font=SMALL_BOLD_FONT, fill=WHITE)

    # purpose 卡片
    rounded_box(draw, (90, 205, 1830, 305), radius=22, fill=WHITE, outline=BORDER, width=2)
    draw.text((120, 228), "这一页在讲什么", font=SECTION_FONT, fill=GREEN)
    draw_wrapped_text(
        draw,
        120,
        262,
        slide.get("purpose", ""),
        SMALL_FONT,
        SUBTEXT,
        max_width=1660,
        line_gap=6
    )

    # 左侧主内容
    rounded_box(draw, (90, 340, 1230, 930), radius=24, fill=WHITE, outline=BORDER, width=2)
    draw.text((120, 372), "核心要点", font=SECTION_FONT, fill=TITLE_BLUE_DARK)
    draw_bullets(
        draw,
        125,
        425,
        slide.get("main_points", []),
        BODY_FONT,
        TEXT,
        max_width=1060,
        bullet_gap=20,
        line_gap=8
    )

    # 右侧讲解提示
    rounded_box(draw, (1270, 340, 1830, 930), radius=24, fill=WHITE, outline=BORDER, width=2)
    draw.text((1300, 372), "讲解提示", font=SECTION_FONT, fill=TITLE_BLUE_DARK)
    draw_wrapped_text(
        draw,
        1300,
        425,
        slide.get("narration_focus", "无"),
        SMALL_FONT,
        TEXT,
        max_width=490,
        line_gap=8
    )

    # 右侧底部附加信息
    rounded_box(draw, (1270, 950, 1830, 1025), radius=18, fill=(239, 246, 255), outline=None)
    draw.text((1295, 972), f"视觉类型：{slide.get('visual_type', '')}", font=SMALL_FONT, fill=SUBTEXT)

    # 底部
    draw.line((90, 1040, 1830, 1040), fill=BORDER, width=2)
    draw.text((95, 1048), paper_title[:90], font=FOOTER_FONT, fill=SUBTEXT)
    draw.text((1710, 1048), "Generated by PaperBridge", font=FOOTER_FONT, fill=SUBTEXT)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    print(f"已生成图片：{out_path}")


def generate_slide_images(json_path=GROUND_JSON, out_dir=OUT_DIR):
    json_path = Path(json_path)
    out_dir = Path(out_dir)

    if not json_path.exists():
        raise FileNotFoundError(f"找不到 grounded slides 文件：{json_path}")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    slides = data.get("slides", [])
    paper_title = data.get("paper_title", "PaperBridge Slides")

    out_dir.mkdir(parents=True, exist_ok=True)

    image_paths = []
    for slide in slides:
        slide_no = slide.get("slide_no")
        if slide_no is None:
            continue

        out_path = out_dir / f"slide_{int(slide_no):02d}.png"
        render_one_slide(slide, out_path, paper_title)
        image_paths.append(out_path)

    return image_paths


if __name__ == "__main__":
    generate_slide_images()