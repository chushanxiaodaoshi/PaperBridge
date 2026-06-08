import os
import sys
import re
import json
import time
import asyncio
import subprocess
from pathlib import Path

import edge_tts
from dotenv import load_dotenv

# Windows 控制台默认可能是 GBK，遇到 ∀、α、→ 等符号会 UnicodeEncodeError。
# 这里把标准输出改成 UTF-8，并在极端情况下用 replace 兜底。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


load_dotenv(dotenv_path=Path(".env"))

NARRATION_PATH = "outputs/narration.json"
AUDIO_DIR = Path("outputs/audio")
TMP_DIR = AUDIO_DIR / "_tmp"
SUBTITLE_TIMING_PATH = AUDIO_DIR / "subtitle_timing.json"

EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "zh-CN-YunyangNeural")
EDGE_TTS_RATE = os.getenv("EDGE_TTS_RATE", "+6%")
EDGE_TTS_VOLUME = os.getenv("EDGE_TTS_VOLUME", "+0%")
EDGE_TTS_PROXY = os.getenv("EDGE_TTS_PROXY", "").strip()

SAMPLE_RATE = 48000


def run(cmd):
    subprocess.run(cmd, check=True)



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


def subtitle_text_from_tts_text(text):
    text = str(text).strip()
    restore_map = {
        "P M S M": "PMSM",
        "C M A E S": "CMA-ES",
        "P P O": "PPO",
        "C O T": "CoT",
    }
    for k, v in restore_map.items():
        text = text.replace(k, v)
    return text


def clean_text(text):
    text = str(text).strip()

    replace_map = {
        "PMSM": "P M S M",
        "CMA-ES": "C M A E S",
        "PPO": "P P O",
        "CoT": "C O T",
        "sim-to-real": "sim to real",
        "zero-shot": "zero shot",
    }

    for k, v in replace_map.items():
        text = text.replace(k, v)

    return text


def split_sentences(text):
    text = clean_text(text)

    parts = re.split(r"(?<=[。！？；])", text)
    parts = [p.strip() for p in parts if p.strip()]

    merged = []
    buf = ""

    for p in parts:
        if len(buf) + len(p) < 45:
            buf += p
        else:
            if buf:
                merged.append(buf)
            buf = p

    if buf:
        merged.append(buf)

    return merged


def check_audio(path: Path):
    return path.exists() and path.stat().st_size > 1024


async def synthesize_sentence(text, mp3_path: Path, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            if mp3_path.exists():
                mp3_path.unlink()

            kwargs = {
                "text": text,
                "voice": EDGE_TTS_VOICE,
                "rate": EDGE_TTS_RATE,
                "volume": EDGE_TTS_VOLUME,
            }

            if EDGE_TTS_PROXY:
                kwargs["proxy"] = EDGE_TTS_PROXY

            communicate = edge_tts.Communicate(**kwargs)
            await communicate.save(str(mp3_path))

            if not check_audio(mp3_path):
                raise RuntimeError(f"音频文件无效或过小：{mp3_path}")

            return

        except Exception as e:
            print(f"    第 {attempt}/{max_retries} 次失败：{e}")
            if mp3_path.exists():
                mp3_path.unlink()
            await asyncio.sleep(2)

    raise RuntimeError(f"句子音频生成失败：{text[:40]}")


def convert_to_wav(input_path: Path, output_path: Path):
    run([
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-ar", str(SAMPLE_RATE),
        "-ac", "1",
        "-acodec", "pcm_s16le",
        str(output_path),
    ])


def make_silence(output_path: Path, duration=0.25):
    run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono",
        "-t", str(duration),
        "-acodec", "pcm_s16le",
        str(output_path),
    ])


def concat_wavs(wav_paths, output_path: Path):
    list_path = output_path.with_suffix(".txt")
    raw_path = output_path.with_name(output_path.stem + "_raw.wav")

    with list_path.open("w", encoding="utf-8") as f:
        for p in wav_paths:
            f.write(f"file '{p.resolve()}'\n")

    run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_path),
        "-acodec", "pcm_s16le",
        str(raw_path),
    ])

    # 后处理：降噪感、压缩、限幅，防爆音
    run([
        "ffmpeg", "-y",
        "-i", str(raw_path),
        "-af",
        "highpass=f=80,"
        "lowpass=f=12000,"
        "acompressor=threshold=-18dB:ratio=4:attack=5:release=80,"
        "alimiter=limit=0.82:attack=5:release=50,"
        "volume=0.85",
        "-ar", str(SAMPLE_RATE),
        "-ac", "1",
        "-acodec", "pcm_s16le",
        str(output_path),
    ])

    list_path.unlink()

    if raw_path.exists():
        raw_path.unlink()


async def generate_slide_audio(slide_no, text, output_path: Path):
    sentences = split_sentences(text)

    if not sentences:
        raise ValueError(f"Slide {slide_no} 讲解稿为空。")

    slide_tmp = TMP_DIR / f"slide_{slide_no:02d}"
    slide_tmp.mkdir(parents=True, exist_ok=True)

    wav_parts = []
    subtitle_segments = []
    current_time = 0.0

    print(f"第 {slide_no} 页拆成 {len(sentences)} 段。")

    for i, sent in enumerate(sentences, start=1):
        sent_mp3 = slide_tmp / f"sent_{i:02d}.mp3"
        sent_wav = slide_tmp / f"sent_{i:02d}.wav"
        silence_wav = slide_tmp / f"silence_{i:02d}.wav"

        print(f"  合成句子 {i}/{len(sentences)}：{sent[:34]}...")

        await synthesize_sentence(sent, sent_mp3)
        convert_to_wav(sent_mp3, sent_wav)

        sent_duration = get_duration(sent_wav)
        subtitle_segments.append({
            "slide_no": int(slide_no),
            "index": int(i),
            "text": subtitle_text_from_tts_text(sent),
            "start": round(current_time, 3),
            "end": round(current_time + sent_duration, 3),
            "duration": round(sent_duration, 3),
        })

        wav_parts.append(sent_wav)
        current_time += sent_duration

        if i != len(sentences):
            silence_duration = 0.24
            if sent.endswith("？"):
                silence_duration = 0.36
            elif sent.endswith("！"):
                silence_duration = 0.32
            elif sent.endswith("；"):
                silence_duration = 0.18

            make_silence(silence_wav, silence_duration)
            wav_parts.append(silence_wav)
            current_time += silence_duration

    concat_wavs(wav_parts, output_path)

    if not check_audio(output_path):
        raise RuntimeError(f"最终音频无效：{output_path}")

    # 由于 concat_wavs 会做一次轻微音频后处理，总时长可能有毫秒级误差。
    # 这里把最后一个字幕段的结尾钳到最终音频时长内。
    try:
        final_duration = get_duration(output_path)
        if subtitle_segments:
            subtitle_segments[-1]["end"] = round(min(subtitle_segments[-1]["end"], final_duration), 3)
    except Exception:
        pass

    print(f"生成成功：{output_path}")
    return subtitle_segments


async def main_async():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    data = json.loads(Path(NARRATION_PATH).read_text(encoding="utf-8"))
    slides = data.get("slides", [])

    if not slides:
        raise RuntimeError("narration.json 中没有 slides，请先生成讲解稿。")

    print(f"当前使用 Edge TTS voice={EDGE_TTS_VOICE}, rate={EDGE_TTS_RATE}, volume={EDGE_TTS_VOLUME}")

    if EDGE_TTS_PROXY:
        print(f"当前代理：{EDGE_TTS_PROXY}")

    all_timing = []

    for slide in slides:
        slide_no = int(slide.get("slide_no"))
        text = slide.get("narration", "").strip()

        output_path = AUDIO_DIR / f"slide_{slide_no:02d}.wav"

        print(f"\n正在生成第 {slide_no} 页音频：{output_path}")
        segments = await generate_slide_audio(slide_no, text, output_path)
        all_timing.append({
            "slide_no": slide_no,
            "audio": str(output_path),
            "segments": segments,
        })

        SUBTITLE_TIMING_PATH.write_text(
            json.dumps({"slides": all_timing}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    print(f"\n字幕时间轴已生成：{SUBTITLE_TIMING_PATH}")
    print("\n所有音频生成完成。")


if __name__ == "__main__":
    asyncio.run(main_async())
