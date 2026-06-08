import json
import re
import subprocess
from pathlib import Path
from project_namer import get_named_slides_path, get_named_video_path

import fitz


PPT_PATH = str(get_named_slides_path())
PDF_DIR = Path("outputs/pdf")
IMAGE_DIR = Path("outputs/slide_images")
AUDIO_DIR = Path("outputs/audio")
SEGMENT_DIR = Path("outputs/video_segments")
SUBTITLE_DIR = Path("outputs/subtitles")

NARRATION_PATH = Path("outputs/narration.json")

OUTPUT_VIDEO = str(get_named_video_path())
RAW_VIDEO = str(Path(OUTPUT_VIDEO).with_name(Path(OUTPUT_VIDEO).stem + "_raw.mp4"))
SRT_PATH = SUBTITLE_DIR / "paperbridge_subtitles.srt"

FPS = 24
WIDTH = 1920
HEIGHT = 1080
DEFAULT_SILENT_DURATION = 3.0


def log(msg):
    print(msg, flush=True)


def progress(percent, msg):
    percent = max(0, min(100, int(percent)))
    print(f"VIDEO_PROGRESS:{percent}:{msg}", flush=True)


def run(cmd):
    subprocess.run(cmd, check=True)


def ensure_dirs():
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    SEGMENT_DIR.mkdir(parents=True, exist_ok=True)
    SUBTITLE_DIR.mkdir(parents=True, exist_ok=True)


def get_duration(path: Path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def convert_pptx_to_pdf():
    progress(5, "正在将 PPTX 转成 PDF")

    ppt_path = Path(PPT_PATH)

    if not ppt_path.exists():
        raise FileNotFoundError(
            f"找不到命名 PPT 文件：{ppt_path}\n"
            "请先运行 python src/ppt_generator.py 生成 PPT。"
        )

    run([
        "libreoffice",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(PDF_DIR),
        str(ppt_path),
    ])

    pdf_path = PDF_DIR / f"{ppt_path.stem}.pdf"

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 转换失败：{pdf_path}")

    log(f"PDF 已生成：{pdf_path}")
    return pdf_path


def pdf_to_images(pdf_path):
    progress(15, "正在将 PDF 每页转成图片")

    for old in IMAGE_DIR.glob("slide_*.png"):
        old.unlink()

    doc = fitz.open(pdf_path)
    total = len(doc)
    image_paths = []

    for i, page in enumerate(doc, start=1):
        zoom = 2.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        image_path = IMAGE_DIR / f"slide_{i:02d}.png"
        pix.save(image_path)
        image_paths.append(image_path)

        p = 15 + 20 * i / total
        progress(p, f"正在渲染第 {i}/{total} 页幻灯片")
        log(f"已生成图片：{image_path}")

    doc.close()
    return image_paths


def get_audio_path(slide_no):
    wav_path = AUDIO_DIR / f"slide_{slide_no:02d}.wav"
    mp3_path = AUDIO_DIR / f"slide_{slide_no:02d}.mp3"

    if wav_path.exists():
        return wav_path
    if mp3_path.exists():
        return mp3_path

    return None


def make_silent_audio(path, duration):
    run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=48000:cl=mono",
        "-t", str(duration),
        "-acodec", "pcm_s16le",
        str(path),
    ])


def make_segment(image_path, audio_path, segment_path):
    run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-framerate", str(FPS),
        "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
               f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
               f"format=yuv420p",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(segment_path),
    ])


def load_narrations():
    if not NARRATION_PATH.exists():
        return {}

    data = json.loads(NARRATION_PATH.read_text(encoding="utf-8"))
    result = {}

    for slide in data.get("slides", []):
        try:
            slide_no = int(slide.get("slide_no"))
        except Exception:
            continue

        result[slide_no] = slide.get("narration", "").strip()

    return result


def clean_subtitle_text(text):
    text = str(text).strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("P M S M", "PMSM")
    text = text.replace("C M A E S", "CMA-ES")
    text = text.replace("P P O", "PPO")
    text = text.replace("C O T", "CoT")
    return text


def split_subtitle_units(text, max_len=30):
    text = clean_subtitle_text(text)

    if not text:
        return []

    # 先按中文标点切
    parts = re.split(r"(?<=[。！？；，])", text)
    parts = [p.strip() for p in parts if p.strip()]

    units = []

    for part in parts:
        if len(part) <= max_len:
            units.append(part)
            continue

        # 太长的句子再按长度硬切，避免字幕太长
        for i in range(0, len(part), max_len):
            chunk = part[i:i + max_len].strip()
            if chunk:
                units.append(chunk)

    # 合并太短的碎片
    merged = []
    buf = ""

    for u in units:
        if len(buf) + len(u) <= max_len:
            buf += u
        else:
            if buf:
                merged.append(buf)
            buf = u

    if buf:
        merged.append(buf)

    return merged


def wrap_subtitle_line(text, line_len=24):
    text = clean_subtitle_text(text)

    if len(text) <= line_len:
        return text

    lines = []
    for i in range(0, len(text), line_len):
        lines.append(text[i:i + line_len])

    return "\n".join(lines[:2])


def format_srt_time(seconds):
    seconds = max(0, seconds)

    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)

    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def create_srt(slide_durations):
    progress(88, "正在生成字幕文件")

    narrations = load_narrations()
    subtitle_index = 1
    current_time = 0.0

    lines = []

    for slide_no, duration in slide_durations:
        text = narrations.get(slide_no, "")
        units = split_subtitle_units(text)

        if not units:
            current_time += duration
            continue

        total_chars = sum(max(len(u), 1) for u in units)
        local_time = current_time

        for i, unit in enumerate(units):
            weight = max(len(unit), 1) / total_chars
            unit_duration = max(1.15, duration * weight)

            # 最后一条不要超过本页结束时间
            if i == len(units) - 1:
                end_time = current_time + duration
            else:
                end_time = min(local_time + unit_duration, current_time + duration)

            if end_time - local_time < 0.5:
                end_time = min(local_time + 0.5, current_time + duration)

            lines.append(str(subtitle_index))
            lines.append(f"{format_srt_time(local_time)} --> {format_srt_time(end_time)}")
            lines.append(wrap_subtitle_line(unit))
            lines.append("")

            subtitle_index += 1
            local_time = end_time

            if local_time >= current_time + duration:
                break

        current_time += duration

    SRT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log(f"字幕文件已生成：{SRT_PATH}")
    return SRT_PATH


def burn_subtitles(input_video, srt_path, output_video):
    progress(95, "正在烧录字幕到视频")

    # 注意：需要系统有中文字体。推荐安装 fonts-noto-cjk。
    subtitle_filter = (
        f"subtitles='{srt_path}':"
        "force_style='FontName=Noto Sans CJK SC,"
        "FontSize=15,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BorderStyle=1,"
        "Outline=1,"
        "Shadow=0,"
        "Alignment=2,"
        "MarginV=16'"
    )

    run([
        "ffmpeg", "-y",
        "-i", str(input_video),
        "-vf", subtitle_filter,
        "-c:a", "copy",
        str(output_video),
    ])

    log(f"带字幕视频已生成：{output_video}")


def concat_segments(segment_paths, output_path):
    list_path = SEGMENT_DIR / "segments.txt"

    with list_path.open("w", encoding="utf-8") as f:
        for p in segment_paths:
            f.write(f"file '{p.resolve()}'\n")

    run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_path),
        "-c", "copy",
        str(output_path),
    ])


def create_video(image_paths):
    progress(40, "正在合成视频片段")

    for old in SEGMENT_DIR.glob("segment_*.mp4"):
        old.unlink()

    for old in SEGMENT_DIR.glob("silent_*.wav"):
        old.unlink()

    segment_paths = []
    slide_durations = []

    # 只保留有音频的 PPT 页面。
    # glossary / evidence appendix 等没有 slide_xx.wav 的页面不会进入视频。
    playable_items = []
    for i, image_path in enumerate(image_paths, start=1):
        audio_path = get_audio_path(i)
        if audio_path is None:
            log(f"第 {i} 页没有对应音频，跳过，不进入视频。")
            continue
        playable_items.append((i, image_path, audio_path))

    if not playable_items:
        raise RuntimeError(
            "没有找到任何可用于视频的音频文件。"
            "请先运行 python src/tts_generator.py 生成 outputs/audio/slide_xx.wav。"
        )

    total = len(playable_items)

    for idx, (slide_no, image_path, audio_path) in enumerate(playable_items, start=1):
        duration = get_duration(audio_path)
        slide_durations.append((slide_no, duration))

        segment_path = SEGMENT_DIR / f"segment_{slide_no:02d}.mp4"

        p = 40 + 42 * (idx - 1) / max(total, 1)
        progress(p, f"正在生成第 {idx}/{total} 个视频片段，对应 PPT 第 {slide_no} 页")

        make_segment(image_path, audio_path, segment_path)
        segment_paths.append(segment_path)

        p = 40 + 42 * idx / max(total, 1)
        progress(p, f"第 {idx}/{total} 个视频片段完成")

    progress(86, "正在拼接所有视频片段")
    concat_segments(segment_paths, RAW_VIDEO)

    srt_path = create_srt(slide_durations)
    burn_subtitles(RAW_VIDEO, srt_path, OUTPUT_VIDEO)

    progress(100, "视频生成完成")
    log(f"视频已生成：{OUTPUT_VIDEO}")

def main():
    ensure_dirs()

    progress(0, "开始生成视频")
    pdf_path = convert_pptx_to_pdf()
    image_paths = pdf_to_images(pdf_path)
    create_video(image_paths)


if __name__ == "__main__":
    main()
