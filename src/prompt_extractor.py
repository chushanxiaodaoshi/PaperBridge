import ast
import json
from pathlib import Path


SRC_DIR = Path("src")
PROMPT_DIR = Path("prompts/extracted")
MANIFEST_PATH = Path("prompts/prompt_manifest.json")

PROMPT_NAMES = {
    "system_prompt",
    "user_prompt",
    "STYLE_RULES",
    "prompt",
}

PURPOSE_BY_FILE = {
    "agents.py": "论文整体理解：从 paper_text 中提取问题、贡献、方法、实验、初学者解释等结构化信息。",
    "paragraph_indexer.py": "证据索引：把论文文本拆成带页码的段落块，并总结每段用途，供后续 PPT grounding 使用。",
    "grounded_slide_planner.py": "PPT 规划：根据论文分析和证据索引生成带 evidence 的 PPT 页面结构。",
    "term_explainer.py": "术语注释：提取 PPT 中出现的专业术语，并生成统一解释。",
    "narration_generator.py": "讲解稿生成：根据 PPT、论文证据和术语表生成非照读 PPT 的中文讲解稿。",
    "style_refiner.py": "文案风格优化：把 PPT 和讲解稿改得更清晰、准确、克制。",
    "speech_style_refiner.py": "口播优化：把讲解稿改成更适合 TTS 的课堂口播风格。",
}


def clean_source_string(src):
    src = src.strip()

    # 去掉 f / r / u / b 前缀
    while src and src[0] in "fFrRuUbB":
        src = src[1:].strip()

    if src.startswith('"""') and src.endswith('"""'):
        return src[3:-3].strip()
    if src.startswith("'''") and src.endswith("'''"):
        return src[3:-3].strip()
    if src.startswith('"') and src.endswith('"'):
        return src[1:-1].strip()
    if src.startswith("'") and src.endswith("'"):
        return src[1:-1].strip()

    return src.strip()


def extract_from_file(path: Path):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    items = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue

        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue

            name = target.id

            if not (name in PROMPT_NAMES or "prompt" in name.lower()):
                continue

            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                text = node.value.value.strip()
            else:
                segment = ast.get_source_segment(source, node.value)
                text = clean_source_string(segment or "")

            if not text:
                continue

            prompt_id = f"{path.stem}.{name}.L{node.lineno}"
            items.append({
                "id": prompt_id,
                "file": str(path),
                "variable": name,
                "line": node.lineno,
                "purpose": PURPOSE_BY_FILE.get(path.name, "该 prompt 用于对应脚本中的 LLM 调用。"),
                "text": text,
            })

    return items


def main():
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    manifest = []

    for path in sorted(SRC_DIR.glob("*.py")):
        items = extract_from_file(path)

        for item in items:
            safe_id = item["id"].replace("/", "_").replace(":", "_")
            out_path = PROMPT_DIR / f"{safe_id}.txt"

            out_path.write_text(item["text"], encoding="utf-8")

            manifest.append({
                "id": item["id"],
                "file": item["file"],
                "variable": item["variable"],
                "line": item["line"],
                "purpose": item["purpose"],
                "path": str(out_path),
            })

    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"已提取 {len(manifest)} 个 prompt")
    print(f"清单：{MANIFEST_PATH}")
    print(f"文件夹：{PROMPT_DIR}")


if __name__ == "__main__":
    main()
