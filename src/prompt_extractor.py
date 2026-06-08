import ast
import json
from pathlib import Path

from prompt_manager import (
    DEFAULT_DIR,
    CUSTOM_DIR,
    MANIFEST_PATH,
    write_default_prompt,
    custom_path,
    safe_prompt_filename,
)


SRC_DIR = Path("src")

PROMPT_NAMES = {
    "STYLE_RULES",
}

PURPOSE_BY_FILE = {
    "lecture_narration_refiner.py": "讲解稿润色风格：控制中文讲解稿的口吻、节奏、专业程度和初学者友好程度。",

    "agents.py": "论文整体理解：从 paper_text 中提取问题、贡献、方法、实验、初学者解释等结构化信息。",
    "paragraph_indexer.py": "证据索引：把论文文本拆成带页码的证据块，并总结每段用途，供后续 PPT grounding 使用。",
    "grounded_slide_planner.py": "PPT 规划：根据论文分析和证据索引生成带 evidence 的 PPT 页面结构。",
    "term_explainer.py": "术语注释：提取 PPT 中出现的专业术语，并生成统一解释。",
    "narration_generator.py": "讲解稿生成：根据 PPT、论文证据和术语表生成非照读 PPT 的中文讲解稿。",
    "style_refiner.py": "PPT 文案风格：控制 PPT 页面文字是否简洁、克制、准确，避免幼稚比喻和过度口语化。",
    "speech_style_refiner.py": "口播稿风格：控制 TTS 朗读稿的句长、停顿、自然度和课堂讲解感。",
}



def is_editable_style_prompt(file_name: str, variable_name: str):
    """
    只允许提取“风格类 prompt”。

    不开放：
    - system_prompt
    - user_prompt
    - 含 JSON schema / JSON 模板的 prompt

    开放：
    - STYLE_RULES
    - 变量名中明确包含 style / rules 的风格规则
    """
    name = variable_name.lower()

    if variable_name == "STYLE_RULES":
        return True

    if "style" in name and "prompt" in name:
        return True

    if "style" in name and "rule" in name:
        return True

    return False



def clean_source_string(src):
    src = str(src).strip()

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


def extract_string_value(source, node):
    """
    只提取真正的字符串 prompt。
    不提取 get_effective_prompt(...) 这种运行时覆盖语句。
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip()

    if isinstance(node, ast.JoinedStr):
        segment = ast.get_source_segment(source, node)
        return clean_source_string(segment or "")

    return ""


def extract_from_file(path: Path):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    items = []
    counter = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue

        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue

            name = target.id

            if not is_editable_style_prompt(path.name, name):
                continue

            text = extract_string_value(source, node.value)

            if not text or len(text) < 20:
                continue

            key = f"{path.stem}.{name}"
            counter[key] = counter.get(key, 0) + 1

            prompt_id = f"{path.stem}.{name}.{counter[key]}"

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
    DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    manifest = []

    for path in sorted(SRC_DIR.glob("*.py")):
        if path.name in {"prompt_manager.py", "prompt_extractor.py"}:
            continue

        items = extract_from_file(path)

        for item in items:
            prompt_id = item["id"]
            default_file = write_default_prompt(prompt_id, item["text"])
            custom_file = custom_path(prompt_id)

            manifest.append({
                "id": prompt_id,
                "file": item["file"],
                "variable": item["variable"],
                "line": item["line"],
                "purpose": item["purpose"],
                "default_path": str(default_file),
                "custom_path": str(custom_file),
                "has_custom": custom_file.exists() and custom_file.read_text(encoding="utf-8").strip() != "",
            })

    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"已提取 {len(manifest)} 个默认 prompt")
    print(f"默认 prompt：{DEFAULT_DIR}")
    print(f"自定义 prompt：{CUSTOM_DIR}")
    print(f"清单：{MANIFEST_PATH}")


if __name__ == "__main__":
    main()
