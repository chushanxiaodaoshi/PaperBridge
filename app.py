import os
import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import gradio as gr
import edge_tts

from src.prompt_manager import (
    load_manifest as pm_load_manifest,
    get_prompt_for_ui,
    save_custom_prompt,
)
from dotenv import load_dotenv
import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer


ROOT = Path(".")
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "outputs"
PROMPT_MANIFEST = ROOT / "prompts/prompt_manifest.json"

INPUT_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

load_dotenv(dotenv_path=Path(".env"))
dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")


VOICE_OPTIONS = {
    "Edge - Yunyang 男声（正式可靠，最适合论文讲解）": "zh-CN-YunyangNeural",
    "Edge - Yunxi 男声（年轻自然，稍微活泼）": "zh-CN-YunxiNeural",
    "Edge - Yunjian 男声（更有力量感）": "zh-CN-YunjianNeural",
    "Edge - Xiaoxiao 女声（自然温和）": "zh-CN-XiaoxiaoNeural",
    "Edge - Xiaoyi 女声（活泼）": "zh-CN-XiaoyiNeural",
}


def ensure_prompt_manifest():
    if not PROMPT_MANIFEST.exists():
        subprocess.run(["python", "src/prompt_extractor.py"], check=True)


def load_manifest():
    ensure_prompt_manifest()
    return pm_load_manifest()


def prompt_choices():
    manifest = load_manifest()
    choices = []

    for item in manifest:
        tag = "自定义" if item.get("has_custom") else "默认"
        choices.append(
            f'{item["id"]} | [{tag}] {item["purpose"]}'
        )

    return choices


def find_prompt(choice):
    if not choice:
        return None

    prompt_id = choice.split(" | ")[0].strip()

    for item in load_manifest():
        if item["id"] == prompt_id:
            return item

    return None


def load_prompt(choice):
    item = find_prompt(choice)

    if not item:
        return "", ""

    prompt_id = item["id"]
    data = get_prompt_for_ui(prompt_id)

    mode_text = "自定义 prompt" if data["mode"] == "custom" else "默认 prompt"

    info = (
        f'Prompt ID：{prompt_id}\n'
        f'当前模式：{mode_text}\n'
        f'文件：{item["file"]}\n'
        f'变量：{item["variable"]}\n'
        f'行号：{item["line"]}\n'
        f'用途：{item["purpose"]}\n'
        f'默认文件：{item["default_path"]}\n'
        f'自定义文件：{item["custom_path"]}\n\n'
        f'说明：文本框为空并保存时，会自动回退默认 prompt。'
    )

    # 关键：如果没有自定义，就自动填充默认 prompt
    return info, data["text"]


def save_prompt(choice, text):
    item = find_prompt(choice)

    if not item:
        return "没有选择 prompt。", gr.update(), ""

    prompt_id = item["id"]
    result = save_custom_prompt(prompt_id, text)

    # 保存后重新生成 manifest，刷新“默认/自定义”状态
    subprocess.run(["python", "src/prompt_extractor.py"], check=True)

    data = get_prompt_for_ui(prompt_id)

    status = (
        f'{result["message"]}\n'
        f'当前模式：{"自定义 prompt" if data["mode"] == "custom" else "默认 prompt"}\n'
        f'当前生效文件：{result["path"]}'
    )

    # 如果用户保存空文本，这里会自动把默认 prompt 填回文本框
    return status, gr.update(choices=prompt_choices(), value=choice), data["text"]


def refresh_prompts():
    subprocess.run(["python", "src/prompt_extractor.py"], check=True)
    return gr.update(choices=prompt_choices())


async def preview_voice_async(voice_label, preview_text):
    if voice_label not in VOICE_OPTIONS:
        raise gr.Error(f"未知音色：{voice_label}")

    voice = VOICE_OPTIONS[voice_label]

    preview_text = preview_text.strip() or "这一页我们先解决一个核心问题：为什么仿真里的控制器，到了真实机器人上就不稳定。"

    out_path = OUTPUT_DIR / f"voice_preview_{voice}.mp3"

    proxy = os.getenv("EDGE_TTS_PROXY", "").strip()

    kwargs = {
        "text": preview_text,
        "voice": voice,
        "rate": os.getenv("EDGE_TTS_RATE", "+6%"),
        "volume": os.getenv("EDGE_TTS_VOLUME", "+0%"),
    }

    if proxy:
        kwargs["proxy"] = proxy

    communicate = edge_tts.Communicate(**kwargs)
    await communicate.save(str(out_path))

    if not out_path.exists() or out_path.stat().st_size < 1024:
        raise gr.Error("试听音频生成失败，文件为空或过小。")

    return str(out_path)


def preview_voice(voice_label, preview_text):
    try:
        return asyncio.run(preview_voice_async(voice_label, preview_text))
    except gr.Error:
        raise
    except Exception as e:
        print("[试听失败]", repr(e))
        raise gr.Error(f"试听失败：{repr(e)}")


def run_cmd(cmd, env):
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        bufsize=1,
    )

    for line in process.stdout:
        yield line

    process.wait()

    if process.returncode != 0:
        raise RuntimeError(f"命令失败：{' '.join(cmd)}")


def build_pipeline_commands(selected_steps):
    step_to_cmd = {
        "1. 解析 PDF": ["python", "-u", "src/pdf_parser.py"],
        "2. 论文结构化分析": ["python", "-u", "src/main.py"],
        "3. 构建段落证据索引": ["python", "-u", "src/paragraph_indexer.py"],
        "4. 规划 Grounded PPT": ["python", "-u", "src/grounded_slide_planner.py"],
        "5. 修复 Evidence 对齐": ["python", "-u", "src/fix_grounded_evidence.py"],
        "6. 优化 PPT 文案风格": ["python", "-u", "src/style_refiner.py"],
        "7. 生成术语注释": ["python", "-u", "src/term_explainer.py"],
        "8. 生成 PPT": ["python", "-u", "src/ppt_generator.py"],
        "9. 生成讲解稿": ["python", "-u", "src/narration_generator.py"],
        "10. 优化口播稿": ["python", "-u", "src/speech_style_refiner.py"],
        "11. 生成音频": ["python", "-u", "src/tts_generator.py"],
        "12. 合成视频": ["python", "-u", "src/video_generator.py"],
    }

    commands = []

    for step in selected_steps:
        cmd = step_to_cmd.get(step)
        if not cmd:
            continue

        # cmd 可能是 ["python", "-u", "src/xxx.py"]
        # 所以不能固定检查 cmd[1]，要找到真正的 .py 文件
        script_path = None
        for part in cmd:
            if isinstance(part, str) and part.endswith(".py"):
                script_path = Path(part)
                break

        if script_path is not None and script_path.exists():
            commands.append((step, cmd))
        else:
            commands.append((step, None))

    return commands



def parse_video_progress_line(line):
    line = line.strip()
    if not line.startswith("VIDEO_PROGRESS:"):
        return None

    parts = line.split(":", 2)
    if len(parts) != 3:
        return None

    try:
        percent = int(parts[1])
    except ValueError:
        return None

    message = parts[2]
    return percent, message


def newest_existing(paths):
    existing = [
        p for p in paths
        if p.exists() and p.stat().st_size > 1024
    ]

    if not existing:
        return None

    existing.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return str(existing[0])


def get_current_outputs():
    named_ppts = list(OUTPUT_DIR.glob("*_PaperBridge_Slides.pptx"))
    named_videos = list(OUTPUT_DIR.glob("*_PaperBridge_Video.mp4"))

    ppt_path = newest_existing(named_ppts)
    video_path = newest_existing(named_videos)

    return ppt_path, video_path



def run_pipeline(pdf_file, voice_label, selected_steps, progress=gr.Progress()):
    log = ""

    if pdf_file is not None:
        target_pdf = INPUT_DIR / "paper.pdf"
        shutil.copy(pdf_file.name, target_pdf)
        log += f"已复制 PDF 到：{target_pdf}\n"

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    voice_value = VOICE_OPTIONS[voice_label]
    if isinstance(voice_value, tuple):
        model, voice = voice_value
        env["TTS_MODEL"] = model
        env["TTS_VOICE"] = voice
    else:
        voice = voice_value
        env["EDGE_TTS_VOICE"] = voice
        env["EDGE_TTS_RATE"] = os.getenv("EDGE_TTS_RATE", "+6%")
        env["EDGE_TTS_VOLUME"] = os.getenv("EDGE_TTS_VOLUME", "+0%")
        if os.getenv("EDGE_TTS_PROXY", "").strip():
            env["EDGE_TTS_PROXY"] = os.getenv("EDGE_TTS_PROXY", "").strip()

    commands = build_pipeline_commands(selected_steps)
    total_steps = max(len(commands), 1)

    progress(0, desc="准备开始")

    current_ppt, current_video = get_current_outputs()
    yield log, current_ppt, current_video

    for idx, (step, cmd) in enumerate(commands, start=1):
        base_progress = (idx - 1) / total_steps
        step_progress_weight = 1 / total_steps

        progress(base_progress, desc=f"正在执行：{step}")

        log += f"\n===== {step} =====\n"

        current_ppt, current_video = get_current_outputs()
        yield log, current_ppt, current_video

        if cmd is None:
            log += "跳过：对应脚本不存在。\n"
            progress(idx / total_steps, desc=f"已跳过：{step}")

            current_ppt, current_video = get_current_outputs()
            yield log, current_ppt, current_video
            continue

        try:
            for line in run_cmd(cmd, env):
                parsed = parse_video_progress_line(line)

                if parsed is not None:
                    video_percent, video_msg = parsed
                    overall = base_progress + step_progress_weight * (video_percent / 100)
                    progress(overall, desc=video_msg)
                    log += f"[视频进度 {video_percent}%] {video_msg}\n"
                else:
                    log += line

                current_ppt, current_video = get_current_outputs()
                yield log, current_ppt, current_video

            progress(idx / total_steps, desc=f"完成：{step}")

            current_ppt, current_video = get_current_outputs()

            if "生成 PPT" in step and current_ppt:
                log += f"\nPPT 已生成，可以在右侧下载：{current_ppt}\n"

            if "合成视频" in step and current_video:
                log += f"\n视频已生成，可以在右侧下载：{current_video}\n"

            yield log, current_ppt, current_video

        except Exception as e:
            log += f"\n失败：{e}\n"

            current_ppt, current_video = get_current_outputs()
            yield log, current_ppt, current_video
            return

    log += "\n全部流程结束。\n"
    progress(1.0, desc="全部完成")

    current_ppt, current_video = get_current_outputs()
    yield log, current_ppt, current_video


DEFAULT_STEPS = [
    "1. 解析 PDF",
    "2. 论文结构化分析",
    "3. 构建段落证据索引",
    "4. 规划 Grounded PPT",
    "5. 修复 Evidence 对齐",
    "6. 优化 PPT 文案风格",
    "7. 生成术语注释",
    "8. 生成 PPT",
    "9. 生成讲解稿",
    "10. 优化口播稿",
    "11. 生成音频",
    "12. 合成视频",
]


with gr.Blocks(title="PaperBridge") as demo:
    gr.Markdown("# PaperBridge\n拖拽论文 PDF，生成 grounded PPT、讲解音频和讲解视频。")

    with gr.Tab("生成"):
        pdf_input = gr.File(
            label="拖拽论文 PDF 到这里",
            file_types=[".pdf"],
        )

        voice_dropdown = gr.Dropdown(
            label="选择音色",
            choices=list(VOICE_OPTIONS.keys()),
            value="Edge - Yunyang 男声（正式可靠，最适合论文讲解）",
        )

        preview_text = gr.Textbox(
            label="试听文本",
            value="这一页我们先解决一个核心问题：为什么仿真里的控制器，到了真实机器人上就不稳定。",
            lines=3,
        )

        preview_btn = gr.Button("试听音色")
        preview_audio = gr.Audio(label="试听结果", type="filepath")

        preview_btn.click(
            fn=preview_voice,
            inputs=[voice_dropdown, preview_text],
            outputs=preview_audio,
        )

        steps = gr.CheckboxGroup(
            label="选择要执行的步骤",
            choices=DEFAULT_STEPS,
            value=DEFAULT_STEPS,
        )

        run_btn = gr.Button("开始生成", variant="primary")
        log_box = gr.Textbox(label="运行日志", lines=22)
        ppt_output = gr.File(label="生成的 PPT")
        video_output = gr.File(label="生成的视频")

        run_btn.click(
            fn=run_pipeline,
            inputs=[pdf_input, voice_dropdown, steps],
            outputs=[log_box, ppt_output, video_output],
        )

    with gr.Tab("Prompt 编辑"):
        gr.Markdown("这里只开放风格类 Prompt，例如 PPT 文案风格、讲解稿风格、口播风格。JSON 模板和字段结构不会出现在这里，避免改坏生成流程。")

        refresh_btn = gr.Button("重新提取 Prompt")
        prompt_select = gr.Dropdown(
            label="选择 Prompt",
            choices=prompt_choices(),
        )

        prompt_info = gr.Textbox(label="用途说明", lines=5)
        prompt_editor = gr.Textbox(label="Prompt 内容", lines=22)

        save_btn = gr.Button("保存 Prompt")
        save_status = gr.Textbox(label="保存状态", lines=2)

        refresh_btn.click(
            fn=refresh_prompts,
            inputs=[],
            outputs=prompt_select,
        )

        prompt_select.change(
            fn=load_prompt,
            inputs=prompt_select,
            outputs=[prompt_info, prompt_editor],
        )

        save_btn.click(
            fn=save_prompt,
            inputs=[prompt_select, prompt_editor],
            outputs=[save_status, prompt_select, prompt_editor],
        )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7862)
