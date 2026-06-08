import os
import re
import json
import time
import subprocess
from pathlib import Path

from dotenv import load_dotenv
import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer


load_dotenv(dotenv_path=Path(".env"))
dashscope.api_key = os.getenv("TTS_API_KEY")

NARRATION_PATH = "outputs/narration.json"
AUDIO_DIR = Path("outputs/audio")
TMP_DIR = AUDIO_DIR / "_tmp"

TTS_MODEL = os.getenv("TTS_MODEL", "cosyvoice-v1")
TTS_VOICE = os.getenv("TTS_VOICE", "longxiang")

SAMPLE_RATE = 48000


def run(cmd):
    subprocess.run(cmd, check=True)


def clean_text(text):
    text = str(text).strip()
    text = text.replace("PMSM", "P M S M")
    text = text.replace("CMA-ES", "C M A E S")
    text = text.replace("PPO", "P P O")
    text = text.replace("CoT", "C O T")
    text = text.replace("sim-to-real", "sim to real")
    text = text.replace("zero-shot", "zero shot")
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


def synthesize_sentence(text, mp3_path: Path, max_retries=3):
    if not dashscope.api_key:
        raise RuntimeError("没有读取到 TTS_API_KEY，请检查 .env 文件。")

    synthesizer = SpeechSynthesizer(
        model=TTS_MODEL,
        voice=TTS_VOICE,
    )

    for attempt in range(1, max_retries + 1):
        try:
            if mp3_path.exists():
                mp3_path.unlink()

            print(f"    使用 tts_v2 合成：{text[:30]}...")
            audio = synthesizer.call(text)

            if not audio:
                raise RuntimeError("DashScope 没有返回音频数据。")

            mp3_path.write_bytes(audio)

            if not check_audio(mp3_path):
                raise RuntimeError(f"音频文件无效或过小：{mp3_path}")

            return

        except Exception as e:
            print(f"    第 {attempt}/{max_retries} 次失败：{e}")
            if mp3_path.exists():
                mp3_path.unlink()
            time.sleep(1.5)

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

    # 先拼接原始音频
    run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_path),
        "-acodec", "pcm_s16le",
        str(raw_path),
    ])

    # 再做防爆音后处理
    run([
        "ffmpeg", "-y",
        "-i", str(raw_path),
        "-af",
        "highpass=f=80,"
        "lowpass=f=12000,"
        "acompressor=threshold=-18dB:ratio=4:attack=5:release=80,"
        "alimiter=limit=0.82:attack=5:release=50,"
        "volume=0.72",
        "-ar", str(SAMPLE_RATE),
        "-ac", "1",
        "-acodec", "pcm_s16le",
        str(output_path),
    ])

    list_path.unlink()

    if raw_path.exists():
        raw_path.unlink()

def generate_slide_audio(slide_no, text, output_path: Path):
    sentences = split_sentences(text)

    if not sentences:
        raise ValueError(f"Slide {slide_no} 讲解稿为空。")

    slide_tmp = TMP_DIR / f"slide_{slide_no:02d}"
    slide_tmp.mkdir(parents=True, exist_ok=True)

    wav_parts = []

    print(f"第 {slide_no} 页拆成 {len(sentences)} 段。")

    for i, sent in enumerate(sentences, start=1):
        sent_mp3 = slide_tmp / f"sent_{i:02d}.mp3"
        sent_wav = slide_tmp / f"sent_{i:02d}.wav"
        silence_wav = slide_tmp / f"silence_{i:02d}.wav"

        print(f"  合成句子 {i}/{len(sentences)}")
        synthesize_sentence(sent, sent_mp3)
        convert_to_wav(sent_mp3, sent_wav)
        wav_parts.append(sent_wav)

        if i != len(sentences):
            duration = 0.24
            if sent.endswith("？"):
                duration = 0.36
            elif sent.endswith("！"):
                duration = 0.32
            elif sent.endswith("；"):
                duration = 0.18

            make_silence(silence_wav, duration)
            wav_parts.append(silence_wav)

    concat_wavs(wav_parts, output_path)

    if not check_audio(output_path):
        raise RuntimeError(f"最终音频无效：{output_path}")

    print(f"生成成功：{output_path}")


def main():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    data = json.loads(Path(NARRATION_PATH).read_text(encoding="utf-8"))
    slides = data.get("slides", [])

    if not slides:
        raise RuntimeError("narration.json 中没有 slides，请先生成讲解稿。")

    print(f"当前使用：TTS_MODEL={TTS_MODEL}, TTS_VOICE={TTS_VOICE}")
    print("当前接口：dashscope.audio.tts_v2")

    for slide in slides:
        slide_no = int(slide.get("slide_no"))
        text = slide.get("narration", "").strip()

        output_path = AUDIO_DIR / f"slide_{slide_no:02d}.wav"

        print(f"\n正在生成第 {slide_no} 页音频：{output_path}")
        generate_slide_audio(slide_no, text, output_path)

    print("\n所有音频生成完成。")


if __name__ == "__main__":
    main()
