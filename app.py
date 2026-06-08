import os
import sys
import runpy
import time
import threading
import asyncio
import json
import re
import shutil
import subprocess
import socket
from pathlib import Path

import gradio as gr
import edge_tts

from src.prompt_manager import (
    load_manifest as pm_load_manifest,
    get_prompt_for_ui,
    save_custom_prompt,
)
from dotenv import load_dotenv

# ---------- Runtime / packaging helpers ----------

APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))

os.chdir(APP_DIR)

SRC_DIR = RESOURCE_DIR / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def ensure_runtime_dirs():
    """
    打包后，input / outputs / prompts 应该出现在 exe 所在目录下，
    这样用户可以直接看到输入输出文件，也可以编辑 prompt。
    """
    Path("input").mkdir(exist_ok=True)
    Path("outputs").mkdir(exist_ok=True)

    src_prompts = RESOURCE_DIR / "prompts"
    dst_prompts = APP_DIR / "prompts"

    if src_prompts.exists() and not dst_prompts.exists():
        shutil.copytree(src_prompts, dst_prompts)


def make_step_cmd(script_path: str):
    """
    开发环境：
        python src/xxx.py

    打包环境：
        PaperBridge.exe --run-script src/xxx.py

    这样用户电脑上即使没有安装 Python，也能运行每个子步骤。
    """
    if getattr(sys, "frozen", False):
        return [str(sys.executable), "--run-script", script_path]
    return [sys.executable, "-u", script_path]


def make_prompt_extractor_cmd():
    return make_step_cmd("src/prompt_extractor.py")


def get_script_real_path(script_path: str) -> Path:
    packaged_path = RESOURCE_DIR / script_path
    if packaged_path.exists():
        return packaged_path

    normal_path = APP_DIR / script_path
    if normal_path.exists():
        return normal_path

    return normal_path


if "--run-script" in sys.argv:
    ensure_runtime_dirs()

    idx = sys.argv.index("--run-script")
    if idx + 1 >= len(sys.argv):
        raise RuntimeError("缺少 --run-script 后面的脚本路径。")

    script = sys.argv[idx + 1]
    script_full_path = get_script_real_path(script)

    if not script_full_path.exists():
        raise FileNotFoundError(f"找不到脚本：{script_full_path}")

    runpy.run_path(str(script_full_path), run_name="__main__")
    sys.exit(0)


ensure_runtime_dirs()

DESKTOP_HOST = "127.0.0.1"
DESKTOP_HOST = "127.0.0.1"


def is_port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def parse_candidate_ports():
    """
    支持两种环境变量写法：

    PAPERBRIDGE_PORTS=7861,7862,7863
    PAPERBRIDGE_PORTS=7861-7870

    如果没设置，就默认尝试 7861 到 7870。
    """
    raw = os.getenv("PAPERBRIDGE_PORTS", "7861-7870").strip()

    if "-" in raw:
        start, end = raw.split("-", 1)
        return list(range(int(start), int(end) + 1))

    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def choose_free_port(host: str) -> int:
    for port in parse_candidate_ports():
        if is_port_free(host, port):
            return port

    raise RuntimeError(
        "没有找到可用端口。请关闭占用 PaperBridge 端口的程序，"
        "或设置环境变量 PAPERBRIDGE_PORTS=7861-7890。"
    )


DESKTOP_PORT = choose_free_port(DESKTOP_HOST)
DESKTOP_URL = f"http://{DESKTOP_HOST}:{DESKTOP_PORT}"





ROOT = APP_DIR
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "outputs"
PROMPT_MANIFEST = ROOT / "prompts/prompt_manifest.json"

INPUT_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

load_dotenv(dotenv_path=Path(".env"))


VOICE_OPTIONS = {
    "Edge - Yunyang 男声（正式可靠，最适合论文讲解）": "zh-CN-YunyangNeural",
    "Edge - Yunxi 男声（年轻自然，稍微活泼）": "zh-CN-YunxiNeural",
    "Edge - Yunjian 男声（更有力量感）": "zh-CN-YunjianNeural",
    "Edge - Xiaoxiao 女声（自然温和）": "zh-CN-XiaoxiaoNeural",
    "Edge - Xiaoyi 女声（活泼）": "zh-CN-XiaoyiNeural",
}



# ---------- Runtime dependency check ----------

LIBREOFFICE_DOWNLOAD_URL = "https://www.libreoffice.org/download/"
FFMPEG_DOWNLOAD_URL = "https://ffmpeg.org/download.html"


def build_runtime_tool_env():
    # 和 run_pipeline 保持一致：
    # 1. 优先使用 app 同级目录下 tools/ffmpeg/bin
    # 2. 优先使用 app 同级目录下 tools/LibreOffice
    env = os.environ.copy()

    ffmpeg_bin = APP_DIR / "tools" / "ffmpeg" / "bin"
    if ffmpeg_bin.exists():
        env["PATH"] = str(ffmpeg_bin) + os.pathsep + env.get("PATH", "")

    soffice_candidates = [
        APP_DIR / "tools" / "LibreOffice" / "program" / "soffice.exe",
        APP_DIR / "tools" / "LibreOffice" / "program" / "soffice",
        APP_DIR / "tools" / "LibreOffice" / "App" / "libreoffice" / "program" / "soffice.exe",
        Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
        Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
    ]

    for soffice in soffice_candidates:
        if soffice.exists():
            env["SOFFICE_PATH"] = str(soffice)
            break

    return env


def find_runtime_exe(name):
    env = build_runtime_tool_env()
    return shutil.which(name, path=env.get("PATH", ""))


def find_soffice_runtime():
    env = build_runtime_tool_env()

    env_path = env.get("SOFFICE_PATH", "").strip()
    if env_path and Path(env_path).exists():
        return env_path

    for name in ["soffice", "libreoffice"]:
        found = shutil.which(name, path=env.get("PATH", ""))
        if found:
            return found

    return None


def check_runtime_dependencies():
    return {
        "ffmpeg": find_runtime_exe("ffmpeg"),
        "ffprobe": find_runtime_exe("ffprobe"),
        "soffice": find_soffice_runtime(),
    }


def dependency_status_markdown():
    deps = check_runtime_dependencies()

    def item(label, value, required_for):
        if value:
            return f"- ✅ **{label}**：已找到 `{value}`  \n  用途：{required_for}"
        return f"- ❌ **{label}**：未找到  \n  用途：{required_for}"

    return "\n".join([
        "### 运行环境检查",
        "",
        item("ffmpeg", deps["ffmpeg"], "生成音频、合成视频、烧录字幕"),
        item("ffprobe", deps["ffprobe"], "读取音频/视频时长"),
        item("LibreOffice / soffice", deps["soffice"], "把 PPT 转成 PDF，再渲染成视频画面"),
        "",
        "如果缺少依赖：",
        f"- LibreOffice 官方下载页：{LIBREOFFICE_DOWNLOAD_URL}",
        f"- FFmpeg 官方下载页：{FFMPEG_DOWNLOAD_URL}",
        "",
        "说明：如果你把工具放到软件目录，请使用以下结构：",
        "",
        "```text",
        "tools/ffmpeg/bin/ffmpeg.exe",
        "tools/ffmpeg/bin/ffprobe.exe",
        "tools/LibreOffice/program/soffice.exe",
        "```",
        "",
        "安装或复制工具后，需要重新启动 PaperBridge，环境检查结果才会刷新。",
    ])


def validate_selected_steps_dependencies(selected_steps):
    selected_steps = selected_steps or []
    deps = check_runtime_dependencies()

    missing = []

    if "11. 生成音频" in selected_steps:
        if not deps["ffmpeg"]:
            missing.append(
                "生成音频需要 ffmpeg。\n"
                "请安装 FFmpeg，或把 ffmpeg.exe 放到 tools/ffmpeg/bin/ffmpeg.exe。"
            )

    if "12. 合成视频" in selected_steps:
        if not deps["ffmpeg"]:
            missing.append(
                "合成视频需要 ffmpeg。\n"
                "请安装 FFmpeg，或把 ffmpeg.exe 放到 tools/ffmpeg/bin/ffmpeg.exe。"
            )
        if not deps["ffprobe"]:
            missing.append(
                "合成视频需要 ffprobe。\n"
                "请安装 FFmpeg，或把 ffprobe.exe 放到 tools/ffmpeg/bin/ffprobe.exe。"
            )
        if not deps["soffice"]:
            missing.append(
                "合成视频需要 LibreOffice / soffice 来把 PPT 转成 PDF。\n"
                "请安装 LibreOffice，或把 LibreOffice 放到 tools/LibreOffice/program/soffice.exe。"
            )

    if missing:
        raise gr.Error(
            "运行环境缺少必要依赖：\n\n"
            + "\n\n".join(f"{i + 1}. {msg}" for i, msg in enumerate(missing))
            + f"\n\nLibreOffice 下载：{LIBREOFFICE_DOWNLOAD_URL}"
            + f"\nFFmpeg 下载：{FFMPEG_DOWNLOAD_URL}"
        )


def ensure_prompt_manifest():
    if not PROMPT_MANIFEST.exists():
        subprocess.run(make_prompt_extractor_cmd(), check=True)


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
    subprocess.run(make_prompt_extractor_cmd(), check=True)

    data = get_prompt_for_ui(prompt_id)

    status = (
        f'{result["message"]}\n'
        f'当前模式：{"自定义 prompt" if data["mode"] == "custom" else "默认 prompt"}\n'
        f'当前生效文件：{result["path"]}'
    )

    # 如果用户保存空文本，这里会自动把默认 prompt 填回文本框
    return status, gr.update(choices=prompt_choices(), value=choice), data["text"]


def refresh_prompts():
    subprocess.run(make_prompt_extractor_cmd(), check=True)
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


def open_outputs_folder():
    OUTPUT_DIR.mkdir(exist_ok=True)

    try:
        if os.name == "nt":
            os.startfile(str(OUTPUT_DIR.resolve()))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(OUTPUT_DIR.resolve())])
        else:
            subprocess.Popen(["xdg-open", str(OUTPUT_DIR.resolve())])

        return f"已打开输出文件夹：{OUTPUT_DIR.resolve()}"

    except Exception as e:
        return f"打开输出文件夹失败：{e}\n请手动打开：{OUTPUT_DIR.resolve()}"



def run_cmd(cmd, env):
    env = env.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,          # 关键：不要让系统默认 GBK 自动解码
        env=env,
        bufsize=0,
    )

    buffer = b""

    while True:
        chunk = process.stdout.read(1)
        if not chunk:
            break

        buffer += chunk

        if chunk in (b"\n", b"\r"):
            raw = buffer
            buffer = b""

            try:
                line = raw.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    line = raw.decode("gbk")
                except UnicodeDecodeError:
                    line = raw.decode("utf-8", errors="replace")

            yield line

    if buffer:
        try:
            line = buffer.decode("utf-8")
        except UnicodeDecodeError:
            try:
                line = buffer.decode("gbk")
            except UnicodeDecodeError:
                line = buffer.decode("utf-8", errors="replace")
        yield line

    process.wait()

    if process.returncode != 0:
        raise RuntimeError(f"命令失败：{' '.join(cmd)}")



def build_pipeline_commands(selected_steps):
    step_to_script = {
        "1. 解析 PDF": "src/pdf_parser.py",
        "2. 论文结构化分析": "src/main.py",
        "3. 构建段落证据索引": "src/paragraph_indexer.py",
        "4. 规划 Grounded PPT": "src/grounded_slide_planner.py",
        "5. 修复 Evidence 对齐": "src/fix_grounded_evidence.py",
        "6. 优化 PPT 文案风格": "src/style_refiner.py",
        "7. 生成术语注释": "src/term_explainer.py",
        "8. 生成 PPT": "src/ppt_generator.py",
        "9. 生成讲解稿": "src/narration_generator.py",
        "10. 优化口播稿": "src/speech_style_refiner.py",
        "11. 生成音频": "src/tts_generator.py",
        "12. 合成视频": "src/video_generator.py",
    }

    commands = []
    selected_set = set(selected_steps or [])

    # 关键：不要按 Gradio 返回的 selected_steps 顺序跑。
    # CheckboxGroup 返回值可能带有历史点击顺序，导致明明全选却先跑第 9 步。
    # 这里强制按 DEFAULT_STEPS 的标准顺序执行。
    for step in DEFAULT_STEPS:
        if step not in selected_set:
            continue

        script = step_to_script.get(step)
        if not script:
            continue

        if get_script_real_path(script).exists():
            commands.append((step, make_step_cmd(script)))
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


def load_current_project_meta():
    meta_path = OUTPUT_DIR / "project_meta.json"

    if not meta_path.exists():
        return None

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(meta, dict):
        return None

    return meta


def get_current_project_slug():
    meta = load_current_project_meta()
    if not meta:
        return None

    slug = (
        meta.get("project_slug")
        or meta.get("project_name")
        or meta.get("name")
        or ""
    )

    slug = str(slug).strip()
    return slug or None


def get_current_outputs():
    """
    只显示当前论文对应的 PPT / 视频。

    判断依据：
    outputs/project_meta.json 里的 project_slug / slides_filename / video_filename。

    没有 project_meta，或者文件名和当前 project_slug 对不上时，
    不显示 outputs 里残留的旧 PPT / 旧视频。
    """
    meta = load_current_project_meta()

    if not meta:
        return None, None

    project_slug = get_current_project_slug()

    slides_filename = meta.get("slides_filename")
    video_filename = meta.get("video_filename")

    if not slides_filename and project_slug:
        slides_filename = f"{project_slug}_PaperBridge_Slides.pptx"

    if not video_filename and project_slug:
        video_filename = f"{project_slug}_PaperBridge_Video.mp4"

    ppt_path = None
    video_path = None

    if slides_filename:
        candidate = OUTPUT_DIR / str(slides_filename)
        if candidate.exists() and candidate.stat().st_size > 1024:
            ppt_path = str(candidate)

    if video_filename:
        candidate = OUTPUT_DIR / str(video_filename)
        if candidate.exists() and candidate.stat().st_size > 1024:
            video_path = str(candidate)

    return ppt_path, video_path



LLM_REQUIRED_STEPS = {
    "2. 论文结构化分析",
    "3. 构建段落证据索引",
    "4. 规划 Grounded PPT",
    "5. 修复 Evidence 对齐",
    "6. 优化 PPT 文案风格",
    "7. 生成术语注释",
    "9. 生成讲解稿",
    "10. 优化口播稿",
}


def selected_steps_need_llm(selected_steps):
    selected_steps = selected_steps or []
    return any(step in LLM_REQUIRED_STEPS for step in selected_steps)




def make_safe_input_pdf_path(original_name):
    INPUT_DIR.mkdir(exist_ok=True)

    stem = Path(original_name).stem
    stem = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", stem)
    stem = stem.strip("_") or "uploaded_paper"

    candidate = INPUT_DIR / f"{stem}.pdf"
    if not candidate.exists():
        return candidate

    index = 2
    while True:
        candidate = INPUT_DIR / f"{stem}_{index}.pdf"
        if not candidate.exists():
            return candidate
        index += 1

def run_pipeline(
    pdf_file,
    api_key,
    base_url,
    model_name,
    voice_label,
    selected_steps,
    progress=gr.Progress()
):
    log = ""
    api_key = (api_key or "").strip()
    base_url = (base_url or "").strip() or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_name = (model_name or "").strip() or "qwen-plus"

    selected_set = set(selected_steps or [])
    selected_steps = [step for step in DEFAULT_STEPS if step in selected_set]

    if not selected_steps:
        raise gr.Error("请至少选择一个要执行的步骤。")

    log += "本次实际执行步骤：" + "、".join(selected_steps) + "\n"

    if selected_steps_need_llm(selected_steps) and not api_key:
        raise gr.Error(
            "需要填写 API Key：你选择的步骤中包含需要调用大模型的任务。"
            "请先在页面顶部的“大模型 API 设置”中填写自己的 大模型 API Key。"
            "只运行生成 PPT、生成音频、合成视频等非大模型步骤时，可以不填写 API Key。"
        )

    current_input_pdf = None

    if pdf_file is not None:
        # 新上传论文时，清除旧项目名缓存，避免沿用上一篇论文的 RLAC / PACE 等名称。
        stale_meta = OUTPUT_DIR / "project_meta.json"
        if stale_meta.exists():
            try:
                stale_meta.unlink()
            except Exception as e:
                log += f"清理旧项目命名信息失败：{e}\n"

        target_pdf = make_safe_input_pdf_path(Path(pdf_file.name).name)
        shutil.copy(pdf_file.name, target_pdf)
        current_input_pdf = target_pdf

        log += f"已复制 PDF 到：{target_pdf}\n"
        log += "解析完成后会自动重命名为 项目名_paper.pdf，例如 RLAC_paper.pdf。\n"
    else:
        if "1. 解析 PDF" in (selected_steps or []):
            log += "未上传新 PDF：将自动从 input 目录选择最新的 PDF 进行解析。\n"

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    if current_input_pdf is not None:
        env["PAPERBRIDGE_INPUT_PDF"] = str(current_input_pdf)

    # 打包版可把 ffmpeg / ffprobe 放在 tools/ffmpeg/bin 下。
    ffmpeg_bin = APP_DIR / "tools" / "ffmpeg" / "bin"
    if ffmpeg_bin.exists():
        env["PATH"] = str(ffmpeg_bin) + os.pathsep + env.get("PATH", "")

    # 打包版可把 LibreOffice 放在 tools/LibreOffice 下。
    soffice_candidates = [
        APP_DIR / "tools" / "LibreOffice" / "program" / "soffice.exe",
        APP_DIR / "tools" / "LibreOffice" / "program" / "soffice",
        APP_DIR / "tools" / "LibreOffice" / "App" / "libreoffice" / "program" / "soffice.exe",
    ]
    for soffice in soffice_candidates:
        if soffice.exists():
            env["SOFFICE_PATH"] = str(soffice)
            break


    # 关键：把网页里输入的 API 配置传给后续所有 Python 脚本
    if api_key:
        env["LLM_API_KEY"] = api_key
        env["LLM_BASE_URL"] = base_url
        env["LLM_MODEL"] = model_name

        log += "已读取用户输入的 API Key，并传入生成流程。不会在日志中显示 Key 内容。\n"
        log += f"模型：{model_name}\n"
        log += f"Base URL：{base_url}\n"
    else:
        log += "未输入 API Key：本次只能运行不需要大模型的步骤。\n"

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

                # 视频生成成功后立即清理中间文件。
                # 注意：必须在这里调用；只定义 cleanup_output_intermediates 不会自动执行。
                removed_items = cleanup_output_intermediates(
                    keep_paths=[current_ppt, current_video]
                )
                if removed_items:
                    log += "\n已清理以下中间文件/目录：\n"
                    for item in removed_items:
                        log += f"- {item}\n"

                current_ppt, current_video = get_current_outputs()

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



def cleanup_output_intermediates(keep_paths=None):
    # 清理 outputs 里的中间文件，保留最终命名后的 PPT / 视频。
    # 目标：最终 outputs 里尽量只剩 <项目名>_PaperBridge_Slides.pptx
    # 和 <项目名>_PaperBridge_Video.mp4。
    keep = set()
    for p in keep_paths or []:
        if not p:
            continue
        try:
            keep.add(Path(p).resolve())
        except Exception:
            pass

    removed = []

    def should_keep(p: Path):
        try:
            return p.resolve() in keep
        except Exception:
            return False

    def remove_file(p: Path):
        try:
            if p.exists() and p.is_file() and not should_keep(p):
                p.unlink()
                removed.append(str(p))
        except Exception:
            pass

    def remove_dir(p: Path):
        try:
            if p.exists() and p.is_dir():
                shutil.rmtree(p)
                removed.append(str(p))
        except Exception:
            pass

    # 体积最大的中间目录
    for name in [
        "audio",
        "pdf",
        "slide_images",
        "video_segments",
        "subtitles",
    ]:
        remove_dir(OUTPUT_DIR / name)

    # 中间 JSON / TXT / MD / 备份文件
    for name in [
        "paper_text.txt",
        "paper_analysis.json",
        "paragraph_index.json",
        "grounded_slides.json",
        "grounded_slides.json.bak",
        "narration.json",
        "narration.json.bak",
        "narration.md",
        "term_explanations.json",
        "term_explanations.md",
    ]:
        remove_file(OUTPUT_DIR / name)

    # 临时视频、Office 锁文件、试听音频、旧固定名副本
    for pattern in [
        "*_raw.mp4",
        "~$*.pptx",
        "voice_preview_*.mp3",
        "paperbridge_grounded_slides.pptx",
        "paperbridge_slides.pptx",
        "paperbridge_lecture_video.mp4",
        "paperbridge_grounded_lecture_video.mp4",
        "paperbridge_lecture_video_raw.mp4",
        "paperbridge_grounded_lecture_video_raw.mp4",
    ]:
        for p in OUTPUT_DIR.glob(pattern):
            remove_file(p)

    # 保留 .gitkeep；如果还有空目录，顺手删掉
    for p in sorted(OUTPUT_DIR.iterdir(), key=lambda x: len(str(x)), reverse=True):
        try:
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
                removed.append(str(p))
        except Exception:
            pass

    return removed

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
    gr.Markdown("# PaperBridge\n拖拽论文 PDF，生成 grounded PPT、讲解音频和讲解视频。\n\n[项目 GitHub 地址](https://github.com/chushanxiaodaoshi/PaperBridge.git)")

    with gr.Accordion("运行环境检查", open=True):
        gr.Markdown(dependency_status_markdown())

    with gr.Accordion("❓ 使用说明", open=False):
        gr.Markdown("""
### PaperBridge 使用说明

PaperBridge 可以把论文 PDF 转换为 grounded PPT、中文讲解稿、讲解音频和带字幕讲解视频。

#### 1. 填写大模型 API 设置

在页面顶部的 **大模型 API 设置** 中填写自己的 API Key、Base URL 和模型名称。

默认配置：

- Base URL：`https://dashscope.aliyuncs.com/compatible-mode/v1`
- 模型名称：`qwen-plus`

默认使用 DashScope / 通义千问接口。

同时，PaperBridge 的推理部分也支持 **OpenAI-compatible API**。也就是说，只要某个模型服务兼容 OpenAI Chat Completions 调用方式，就可以通过修改：

- API Key
- Base URL
- 模型名称

来切换模型。

例如：

| 服务 | Base URL 示例 | 模型名示例 |
|---|---|---|
| DashScope / Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| OpenAI | `https://api.openai.com/v1` | 填写你的账号可用模型名 |
| DeepSeek / OpenRouter / 本地 vLLM | 填写对应 OpenAI-compatible Base URL | 填写对应模型名 |

注意：这里不是支持所有任意格式的 API，而是支持 **OpenAI-compatible** 的大模型接口。

如果选择了需要调用大模型的步骤但没有填写 API Key，页面会弹出报错提示。

#### 2. 上传论文 PDF

在上传区域拖入论文 PDF。

建议上传可复制文本的英文论文 PDF，不建议上传纯扫描版 PDF。

#### 3. 选择音色

当前 TTS 主要使用 **Edge TTS**。

你可以选择不同中文音色，例如：

- Yunyang 男声：正式可靠，适合论文讲解
- Yunxi 男声：年轻自然
- Yunjian 男声：更有力量感
- Xiaoxiao 女声：自然温和
- Xiaoyi 女声：较活泼

注意：当前支持的是 **TTS 音色选择**，不是任意 TTS 服务商 / TTS 模型选择。

可以点击 **试听音色** 先听效果。

#### 4. 选择执行步骤

第一次使用建议保持默认全选。

如果已经生成过中间文件，可以只运行部分步骤：

- 只重新生成 PPT：选择“生成 PPT”
- 只重新生成音频：选择“生成音频”
- 只重新合成视频：选择“合成视频”
- 修改口播风格后：运行“优化口播稿 → 生成音频 → 合成视频”

#### 5. 下载结果

生成完成后，右侧会出现：

- 生成的 PPT
- 生成的视频

文件名会根据论文自动命名，例如：

- `RLAC_PaperBridge_Slides.pptx`
- `RLAC_PaperBridge_Video.mp4`

#### 6. Prompt 编辑说明

Prompt 编辑页只开放风格类 Prompt，例如：

- PPT 文案风格
- 讲解稿风格
- 口播稿风格

JSON 模板和字段结构不会开放修改，避免破坏生成流程。

如果清空文本框并保存，会自动回退默认 Prompt。

#### 7. Evidence 超链接说明

生成的 PPT 中，Evidence 区域可以点击。

点击后会跳转到 Evidence Appendix 页面，查看对应段落的原文摘录、页码、段落编号和初学者解释。

在放映模式下，可以点击返回按钮回到原页面。
        """)

    with gr.Tab("生成"):
        with gr.Accordion("大模型 API 设置", open=True):
            api_key_input = gr.Textbox(
                label="大模型 API Key",
                placeholder="请输入你自己的 大模型 API Key，例如 sk-xxxx",
                type="password",
                lines=1,
            )

            base_url_input = gr.Textbox(
                label="Base URL",
                value="https://dashscope.aliyuncs.com/compatible-mode/v1",
                lines=1,
            )

            model_input = gr.Textbox(
                label="模型名称",
                value="qwen-plus",
                lines=1,
            )

            gr.Markdown(
                "说明：API Key 只会传给本次生成流程，不会显示在日志中。"
            )

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

        open_outputs_btn = gr.Button("打开 outputs 输出文件夹")
        open_outputs_status = gr.Textbox(label="输出文件夹状态", lines=2)

        open_outputs_btn.click(
            fn=open_outputs_folder,
            inputs=[],
            outputs=open_outputs_status,
        )

        run_btn.click(
            fn=run_pipeline,
            inputs=[
                pdf_input,
                api_key_input,
                base_url_input,
                model_input,
                voice_dropdown,
                steps,
            ],
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


def launch_gradio_server():
    demo.launch(
        server_name=DESKTOP_HOST,
        server_port=DESKTOP_PORT,
        inbrowser=False,
        prevent_thread_lock=True,
        show_error=True,
    )


def launch_desktop_window():
    import webview

    server_thread = threading.Thread(
        target=launch_gradio_server,
        daemon=True,
    )
    server_thread.start()

    # 等待 Gradio 服务启动
    time.sleep(2.5)

    webview.create_window(
        title="PaperBridge",
        url=DESKTOP_URL,
        width=1280,
        height=820,
        resizable=True,
        min_size=(1000, 700),
    )

    webview.start()

    # 用户关闭窗口后，直接结束整个程序。
    # 否则 Gradio 后台服务还会继续占用端口。
    os._exit(0)


if __name__ == "__main__":
    if "--browser" in sys.argv:
        demo.launch(
            server_name=DESKTOP_HOST,
            server_port=DESKTOP_PORT,
            inbrowser=True,
            show_error=True,
        )
    else:
        launch_desktop_window()
