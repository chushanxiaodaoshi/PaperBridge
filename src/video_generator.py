import subprocess
from pathlib import Path

import fitz  # PyMuPDF

try:
    from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
except ImportError:
    from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips


PPT_PATH = "outputs/paperbridge_grounded_slides.pptx"
PDF_DIR = "outputs/pdf"
IMAGE_DIR = "outputs/slide_images"
AUDIO_DIR = "outputs/audio"
OUTPUT_VIDEO = "outputs/paperbridge_lecture_video.mp4"


def convert_ppt_to_pdf(ppt_path: str, pdf_dir: str) -> Path:
    """
    使用 LibreOffice 将 PPTX 转成 PDF。
    """
    ppt_path = Path(ppt_path)
    pdf_dir = Path(pdf_dir)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    if not ppt_path.exists():
        raise FileNotFoundError(f"找不到 PPT 文件：{ppt_path}")

    print("正在将 PPTX 转成 PDF...")

    cmd = [
        "libreoffice",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(pdf_dir),
        str(ppt_path)
    ]

    subprocess.run(cmd, check=True)

    pdf_path = pdf_dir / (ppt_path.stem + ".pdf")

    if not pdf_path.exists():
        raise FileNotFoundError(f"PPT 转 PDF 失败，没有找到：{pdf_path}")

    print(f"PDF 已生成：{pdf_path}")
    return pdf_path


def render_pdf_to_images(pdf_path: Path, image_dir: str) -> list[Path]:
    """
    使用 PyMuPDF 将 PDF 每一页渲染成 PNG 图片。
    """
    image_dir = Path(image_dir)
    image_dir.mkdir(parents=True, exist_ok=True)

    print("正在将 PDF 每页转成图片...")

    doc = fitz.open(pdf_path)
    image_paths = []

    for page_index, page in enumerate(doc):
        # 2 倍缩放，保证视频清晰
        matrix = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        image_path = image_dir / f"slide_{page_index + 1:02d}.png"
        pix.save(image_path)

        image_paths.append(image_path)
        print(f"已生成图片：{image_path}")

    return image_paths


def create_video_from_images_and_audio(
    image_paths: list[Path],
    audio_dir: str,
    output_video: str
):
    """
    每页图片 + 对应音频 → 视频片段，再拼接成完整视频。
    """
    audio_dir = Path(audio_dir)
    output_video = Path(output_video)
    output_video.parent.mkdir(parents=True, exist_ok=True)

    clips = []

    print("正在合成视频片段...")

    for image_path in image_paths:
        slide_no = int(image_path.stem.split("_")[-1])
        audio_path = audio_dir / f"slide_{slide_no:02d}.wav"

        if not audio_path.exists():
            print(f"警告：找不到第 {slide_no} 页音频，跳过：{audio_path}")
            continue

        audio_clip = AudioFileClip(str(audio_path))
        duration = audio_clip.duration

        image_clip = ImageClip(str(image_path)).with_duration(duration)
        image_clip = image_clip.with_audio(audio_clip)

        clips.append(image_clip)

        print(f"第 {slide_no} 页已合成，时长 {duration:.2f} 秒")

    if not clips:
        raise RuntimeError("没有可用的视频片段，请检查图片和音频是否生成。")

    final_clip = concatenate_videoclips(clips, method="compose")

    print("正在导出最终视频...")
    final_clip.write_videofile(
        str(output_video),
        fps=24,
        codec="libx264",
        audio_codec="aac"
    )

    for clip in clips:
        clip.close()

    final_clip.close()

    print(f"视频已生成：{output_video}")


def main():
    pdf_path = convert_ppt_to_pdf(PPT_PATH, PDF_DIR)
    image_paths = render_pdf_to_images(pdf_path, IMAGE_DIR)
    create_video_from_images_and_audio(image_paths, AUDIO_DIR, OUTPUT_VIDEO)


if __name__ == "__main__":
    main()
