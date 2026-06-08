import json
import os
import re
import subprocess
import shutil
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
SUBTITLE_TIMING_PATH = AUDIO_DIR / "subtitle_timing.json"

FPS = 24
WIDTH = 1920
HEIGHT = 1080
DEFAULT_SILENT_DURATION = 3.0

def find_soffice():
    """
    查找 LibreOffice / soffice。

    优先级：
    1. app.py 打包运行时传入的 SOFFICE_PATH
    2. 系统 PATH 中的 soffice / libreoffice
    3. Windows 常见安装路径
    """
    env_path = os.getenv("SOFFICE_PATH", "").strip()
    if env_path and Path(env_path).exists():
        return env_path

    for name in ["soffice", "libreoffice"]:
        found = shutil.which(name)
        if found:
            return found

    candidates = [
        Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
        Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
    ]

    for p in candidates:
        if p.exists():
            return str(p)

    return "libreoffice"


SOFFICE = find_soffice()



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
        SOFFICE,
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


def split_subtitle_display_chunks(text, max_chars=44):
    # 把一段较长字幕拆成多个显示块。
    # 之前 wrap_subtitle_line 只保留前两行：return "\\n".join(lines[:2])
    # 如果字幕超过两行，后面的字会被直接丢掉。
    # 现在每条字幕最多约两行，超过长度就拆成多条字幕，不再丢字。
    text = clean_subtitle_text(text)

    if not text:
        return []

    parts = re.split(r"(?<=[。！？；，、])", text)
    parts = [p.strip() for p in parts if p.strip()]

    if not parts:
        parts = [text]

    chunks = []
    buf = ""

    for part in parts:
        if len(part) > max_chars:
            if buf:
                chunks.append(buf)
                buf = ""

            for i in range(0, len(part), max_chars):
                piece = part[i:i + max_chars].strip()
                if piece:
                    chunks.append(piece)

            continue

        if not buf:
            buf = part
        elif len(buf) + len(part) <= max_chars:
            buf += part
        else:
            chunks.append(buf)
            buf = part

    if buf:
        chunks.append(buf)

    return chunks


def wrap_subtitle_line(text, line_len=22):
    # 只负责把一条字幕内部换行，不再截断字幕文本。
    text = clean_subtitle_text(text)

    if len(text) <= line_len:
        return text

    lines = []
    for i in range(0, len(text), line_len):
        lines.append(text[i:i + line_len])

    return "\\n".join(lines)


def format_srt_time(seconds):
    seconds = max(0, seconds)

    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)

    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def create_srt_from_timing(slide_durations):
    if not SUBTITLE_TIMING_PATH.exists():
        return None

    try:
        data = json.loads(SUBTITLE_TIMING_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"读取字幕时间轴失败，将使用旧字幕算法：{e}")
        return None

    timing_map = {}
    for slide in data.get("slides", []):
        try:
            slide_no = int(slide.get("slide_no"))
        except Exception:
            continue
        timing_map[slide_no] = slide.get("segments", [])

    subtitle_index = 1
    current_time = 0.0
    lines = []

    for slide_no, duration in slide_durations:
        segments = timing_map.get(int(slide_no), [])

        if not segments:
            current_time += duration
            continue

        for seg in segments:
            text = str(seg.get("text", "")).strip()
            if not text:
                continue

            try:
                local_start = float(seg.get("start", 0.0))
                local_end = float(seg.get("end", local_start + 1.0))
            except Exception:
                continue

            start_time = current_time + max(0.0, min(local_start, duration))
            end_time = current_time + max(0.0, min(local_end, duration))

            if end_time - start_time < 0.35:
                end_time = min(current_time + duration, start_time + 0.8)

            if end_time <= start_time:
                continue

            chunks = split_subtitle_display_chunks(text)
            if not chunks:
                continue

            seg_duration = max(0.35, end_time - start_time)
            total_chars = sum(max(len(c), 1) for c in chunks)
            local_time = start_time

            for chunk_index, chunk in enumerate(chunks):
                if chunk_index == len(chunks) - 1:
                    chunk_end = end_time
                else:
                    weight = max(len(chunk), 1) / total_chars
                    chunk_end = min(end_time, local_time + seg_duration * weight)
                    if chunk_end - local_time < 0.45:
                        chunk_end = min(end_time, local_time + 0.45)

                if chunk_end <= local_time:
                    continue

                lines.append(str(subtitle_index))
                lines.append(f"{format_srt_time(local_time)} --> {format_srt_time(chunk_end)}")
                lines.append(wrap_subtitle_line(chunk))
                lines.append("")

                subtitle_index += 1
                local_time = chunk_end

        current_time += duration

    if not lines:
        return None

    SRT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log(f"字幕文件已根据真实音频时间轴生成：{SRT_PATH}")
    return SRT_PATH



def create_srt(slide_durations):
    progress(88, "正在生成字幕文件")

    timed_srt = create_srt_from_timing(slide_durations)
    if timed_srt is not None:
        return timed_srt

    log("未找到可用的真实字幕时间轴，使用旧的按字数估算算法。")

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



def ffmpeg_subtitle_path(path):
    # ffmpeg subtitles 滤镜在 Windows 下不能直接吃反斜杠路径。
    # outputs\\subtitles\\xxx.srt 会被解析成 outputssubtitlesxxx.srt。
    # 所以这里统一转成 outputs/subtitles/xxx.srt。
    p = Path(path)

    try:
        rel = p.relative_to(Path.cwd())
        s = rel.as_posix()
    except Exception:
        s = p.resolve().as_posix()
        s = s.replace(':', '\\:')

    return s


def burn_subtitles(input_video, srt_path, output_video):
    progress(95, "正在烧录字幕到视频")

    subtitle_file = ffmpeg_subtitle_path(srt_path)
    log(f"字幕文件路径：{subtitle_file}")

    # Windows 下优先使用微软雅黑；没有也不会影响字幕文件读取。
    subtitle_filter = (
        f"subtitles='{subtitle_file}':"
        "force_style='FontName=Microsoft YaHei,"
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
