import json
import asyncio
from pathlib import Path

import edge_tts


VOICE = "zh-CN-XiaoxiaoNeural"


async def generate_one_audio(text: str, output_path: str):
    communicate = edge_tts.Communicate(
        text=text,
        voice=VOICE,
        rate="+0%",
        volume="+0%"
    )
    await communicate.save(output_path)


async def generate_all_audio(
    narration_path: str = "outputs/narration.json",
    output_dir: str = "outputs/audio"
):
    narration_data = json.loads(Path(narration_path).read_text(encoding="utf-8"))

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    slides = narration_data.get("slides", [])

    for slide in slides:
        slide_no = slide.get("slide_no")
        text = slide.get("narration", "").strip()

        if not text:
            print(f"Slide {slide_no} 没有讲解稿，跳过。")
            continue

        output_path = output_dir / f"slide_{slide_no:02d}.mp3"

        print(f"正在生成第 {slide_no} 页音频：{output_path}")
        await generate_one_audio(text, str(output_path))

    print("所有音频生成完成。")


if __name__ == "__main__":
    asyncio.run(generate_all_audio())
