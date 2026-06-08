import json
import os
import re
import shutil
from pathlib import Path
from collections import Counter


OUTPUT_DIR = Path("outputs")
INPUT_DIR = Path("input")
META_PATH = OUTPUT_DIR / "project_meta.json"

BAD_ACRONYMS = {
    "PDF", "PPT", "PPTX", "JSON", "API", "URL", "HTML",
    "LLM", "GPT", "AI", "ML", "RL",
    "CPU", "GPU", "USB", "CAN",
    "IEEE", "ICRA", "RSS", "CVPR", "ECCV", "ICLR", "NEURIPS",
}


def load_json(path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_text(obj):
    if obj is None:
        return ""
    if isinstance(obj, dict):
        return "\n".join(flatten_text(v) for v in obj.values())
    if isinstance(obj, list):
        return "\n".join(flatten_text(v) for v in obj)
    return str(obj)


def find_title_from_analysis(obj):
    if not isinstance(obj, dict):
        return ""

    for key in ["paper_title", "title", "论文标题", "original_title", "paperTitle", "paper_name"]:
        value = obj.get(key)
        if isinstance(value, str) and len(value.strip()) > 5:
            return value.strip()

    for value in obj.values():
        if isinstance(value, dict):
            title = find_title_from_analysis(value)
            if title:
                return title

    return ""


def find_title_from_text():
    path = OUTPUT_DIR / "paper_text.txt"
    if not path.exists():
        return ""

    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()

    candidates = []
    for line in lines[:100]:
        line = line.strip()
        if not line:
            continue
        if line.startswith("====="):
            continue
        if len(line) < 8 or len(line) > 180:
            continue
        if line.lower().startswith(("abstract", "introduction", "keywords", "related work")):
            continue

        candidates.append(line)

    return candidates[0] if candidates else ""


def collect_acronyms(text):
    raw = re.findall(r"\b[A-Z][A-Z0-9-]{1,12}\b", text)
    result = []

    for item in raw:
        compact = item.strip("-_").replace("-", "")

        if len(compact) < 3 or len(compact) > 12:
            continue
        if compact.upper() in BAD_ACRONYMS:
            continue
        if compact.isdigit():
            continue

        result.append(compact.upper())

    return result


def make_acronym_from_title(title):
    words = re.findall(r"[A-Za-z]+", title)

    stopwords = {
        "a", "an", "the", "of", "for", "and", "or", "to", "in", "on",
        "with", "through", "towards", "toward", "from", "by", "using",
        "systematic", "approach", "method", "framework", "paper",
    }

    useful = [
        w for w in words
        if w.lower() not in stopwords and len(w) >= 3
    ]

    if not useful:
        useful = words[:5]

    acronym = "".join(w[0].upper() for w in useful[:6])
    return acronym or "Paper"


def safe_filename_part(name):
    name = re.sub(r"[^A-Za-z0-9]+", "_", str(name))
    name = name.strip("_")
    return name[:40] or "Paper"


def infer_project_slug():
    analysis = load_json(OUTPUT_DIR / "paper_analysis.json")
    title = find_title_from_analysis(analysis) or find_title_from_text()
    all_text = title + "\n" + flatten_text(analysis)

    # 1. 标题括号内简称，例如 xxx (RLAC)
    for item in re.findall(r"\(([A-Z][A-Z0-9-]{1,12})\)", title):
        compact = item.replace("-", "").upper()
        if len(compact) >= 3 and compact not in BAD_ACRONYMS:
            return compact, title

    # 2. 标题内已有大写简称，例如 RLAC: xxx
    title_acros = collect_acronyms(title)
    if title_acros:
        return title_acros[0], title

    # 3. 分析文本里高频简称
    acros = collect_acronyms(all_text)
    if acros:
        counter = Counter(acros)
        return counter.most_common(1)[0][0], title

    # 4. 从标题首字母生成
    return make_acronym_from_title(title), title


def clear_named_outputs():
    for pattern in [
        "*_PaperBridge_Slides.pptx",
        "*_PaperBridge_Video.mp4",
    ]:
        for p in OUTPUT_DIR.glob(pattern):
            try:
                p.unlink()
            except Exception:
                pass


def copy_if_exists(src, dst):
    if not src.exists():
        return None

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def get_or_create_meta():
    if META_PATH.exists():
        meta = load_json(META_PATH)
        if meta and meta.get("project_slug"):
            if not meta.get("pdf_filename"):
                slug = safe_filename_part(meta["project_slug"])
                meta["pdf_filename"] = f"{slug}_paper.pdf"
                meta["input_pdf_path"] = str(INPUT_DIR / meta["pdf_filename"])
                META_PATH.write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
            return meta

    slug, title = infer_project_slug()
    slug = safe_filename_part(slug)

    meta = {
        "project_slug": slug,
        "paper_title": title,
        "slides_filename": f"{slug}_PaperBridge_Slides.pptx",
        "video_filename": f"{slug}_PaperBridge_Video.mp4",
        "pdf_filename": f"{slug}_paper.pdf",
        "input_pdf_path": str(INPUT_DIR / f"{slug}_paper.pdf"),
    }

    META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return meta



def clear_named_slides():
    for p in OUTPUT_DIR.glob("*_PaperBridge_Slides.pptx"):
        try:
            p.unlink()
        except Exception:
            pass


def clear_named_videos():
    for p in OUTPUT_DIR.glob("*_PaperBridge_Video.mp4"):
        try:
            p.unlink()
        except Exception:
            pass


def sync_named_slides(verbose=True):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    meta = get_or_create_meta()
    clear_named_slides()

    static_slides = OUTPUT_DIR / "paperbridge_grounded_slides.pptx"
    if not static_slides.exists():
        static_slides = OUTPUT_DIR / "paperbridge_slides.pptx"

    named_slides = OUTPUT_DIR / meta["slides_filename"]
    slide_out = copy_if_exists(static_slides, named_slides)

    if verbose:
        print(f'PROJECT_SLUG:{meta["project_slug"]}', flush=True)
        print(f'PAPER_TITLE:{meta.get("paper_title", "")}', flush=True)
        if slide_out:
            print(f"NAMED_SLIDES:{slide_out}", flush=True)

    return slide_out


def sync_named_video(verbose=True):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    meta = get_or_create_meta()
    clear_named_videos()

    static_video = OUTPUT_DIR / "paperbridge_grounded_lecture_video.mp4"
    if not static_video.exists():
        static_video = OUTPUT_DIR / "paperbridge_lecture_video.mp4"

    named_video = OUTPUT_DIR / meta["video_filename"]
    video_out = copy_if_exists(static_video, named_video)

    if verbose:
        print(f'PROJECT_SLUG:{meta["project_slug"]}', flush=True)
        print(f'PAPER_TITLE:{meta.get("paper_title", "")}', flush=True)
        if video_out:
            print(f"NAMED_VIDEO:{video_out}", flush=True)

    return video_out


def sync_named_outputs(verbose=True):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 关键：优先读取同一个 project_meta.json
    meta = get_or_create_meta()

    # 这里只清理命名后的输出文件，不删除 project_meta.json
    clear_named_outputs()

    static_slides = OUTPUT_DIR / "paperbridge_grounded_slides.pptx"
    if not static_slides.exists():
        static_slides = OUTPUT_DIR / "paperbridge_slides.pptx"

    static_video = OUTPUT_DIR / "paperbridge_grounded_lecture_video.mp4"
    if not static_video.exists():
        static_video = OUTPUT_DIR / "paperbridge_lecture_video.mp4"

    named_slides = OUTPUT_DIR / meta["slides_filename"]
    named_video = OUTPUT_DIR / meta["video_filename"]

    slide_out = copy_if_exists(static_slides, named_slides)
    video_out = copy_if_exists(static_video, named_video)

    if verbose:
        print(f'PROJECT_SLUG:{meta["project_slug"]}', flush=True)
        print(f'PAPER_TITLE:{meta.get("paper_title", "")}', flush=True)

        if slide_out:
            print(f"NAMED_SLIDES:{slide_out}", flush=True)

        if video_out:
            print(f"NAMED_VIDEO:{video_out}", flush=True)

    return meta



def reset_project_meta():
    # 开始处理一篇新论文前调用，避免沿用上一篇论文的项目名。
    if META_PATH.exists():
        try:
            META_PATH.unlink()
        except Exception:
            pass


def discover_input_pdf():
    # 优先使用 GUI 传入的 PAPERBRIDGE_INPUT_PDF；
    # 否则从 input 目录下选择修改时间最新的 PDF。
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    env_path = os.getenv("PAPERBRIDGE_INPUT_PDF", "").strip()
    if env_path:
        p = Path(env_path)
        if p.exists() and p.suffix.lower() == ".pdf":
            return p

    pdfs = [
        p for p in INPUT_DIR.glob("*.pdf")
        if p.is_file()
    ]

    if not pdfs:
        raise FileNotFoundError(
            "input 目录下没有找到 PDF。请在界面上传论文，"
            "或手动放入一个 .pdf 文件。"
        )

    pdfs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return pdfs[0]


def get_named_pdf_path():
    meta = get_or_create_meta()
    filename = meta.get("pdf_filename")
    if not filename:
        slug = safe_filename_part(meta.get("project_slug", "Paper"))
        filename = f"{slug}_paper.pdf"
    return INPUT_DIR / filename


def finalize_input_pdf_name(src_pdf=None, remove_old=True, verbose=True):
    # 解析完成、项目名推断出来后，把输入 PDF 改成：
    # input/<项目名>_paper.pdf
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    src_pdf = Path(src_pdf) if src_pdf is not None else discover_input_pdf()
    if not src_pdf.exists():
        return None

    meta = get_or_create_meta()
    slug = safe_filename_part(meta.get("project_slug", "Paper"))
    filename = f"{slug}_paper.pdf"
    dst_pdf = INPUT_DIR / filename

    if src_pdf.resolve() != dst_pdf.resolve():
        shutil.copy2(src_pdf, dst_pdf)

        if remove_old:
            try:
                if src_pdf.parent.resolve() == INPUT_DIR.resolve():
                    src_pdf.unlink()
            except Exception:
                pass

    meta["pdf_filename"] = filename
    meta["input_pdf_path"] = str(dst_pdf)
    meta["source_pdf_filename"] = src_pdf.name

    META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    if verbose:
        print(f"NAMED_PDF:{dst_pdf}", flush=True)

    return dst_pdf


# 兼容旧函数名。如果之前代码里还有 sync_named_pdf 调用，也会走新逻辑。
def sync_named_pdf(src_pdf=None, verbose=True):
    return finalize_input_pdf_name(src_pdf=src_pdf, remove_old=True, verbose=verbose)

def main():
    sync_named_outputs(verbose=True)


if __name__ == "__main__":
    main()


def get_named_slides_path():
    meta = get_or_create_meta()
    return OUTPUT_DIR / meta["slides_filename"]


def get_named_video_path():
    meta = get_or_create_meta()
    return OUTPUT_DIR / meta["video_filename"]


def get_project_meta():
    return get_or_create_meta()
