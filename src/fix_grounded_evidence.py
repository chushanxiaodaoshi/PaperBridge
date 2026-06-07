import json
import re
from pathlib import Path


GROUNDED_PATH = "outputs/grounded_slides.json"
PARAGRAPH_INDEX_PATH = "outputs/paragraph_index.json"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(data, path):
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"已保存修复后的文件：{path}")


def parse_pid(value):
    if value is None:
        return None

    if isinstance(value, int):
        return value

    m = re.search(r"\d+", str(value))
    if not m:
        return None

    return int(m.group(0))


def build_lookup(paragraph_index):
    lookup = {}
    for p in paragraph_index.get("paragraphs", []):
        pid = parse_pid(p.get("paragraph_id"))
        if pid is not None:
            lookup[pid] = p
    return lookup


def extract_pids_from_slide(slide):
    text_parts = []

    for key in ["title", "purpose", "layout_hint", "narration_focus", "visual_type"]:
        text_parts.append(str(slide.get(key, "")))

    for item in slide.get("main_points", []):
        text_parts.append(str(item))

    full_text = "\n".join(text_parts)

    pids = re.findall(r"[Pp]\s*(\d+)", full_text)

    clean = []
    for pid in pids:
        pid = int(pid)
        if pid not in clean:
            clean.append(pid)

    return clean


def fallback_select(slide, paragraph_index, max_items=3):
    title = str(slide.get("title", "")).lower()
    points = " ".join(str(x) for x in slide.get("main_points", [])).lower()
    text = title + " " + points

    if any(k in text for k in ["问题", "失效", "gap", "problem", "motivation"]):
        preferred = ["Introduction", "Related Work"]
    elif any(k in text for k in ["前置", "知识", "concept", "概念"]):
        preferred = ["Introduction", "Related Work", "Method"]
    elif any(k in text for k in ["方法", "流程", "method", "pace", "参数", "reward"]):
        preferred = ["Method"]
    elif any(k in text for k in ["实验", "结果", "验证", "experiment", "result"]):
        preferred = ["Experiments", "Results"]
    elif any(k in text for k in ["总结", "takeaway", "记住"]):
        preferred = ["Conclusion", "Discussion", "Experiments", "Introduction"]
    else:
        preferred = ["Introduction", "Method", "Experiments", "Results"]

    selected = []
    paragraphs = paragraph_index.get("paragraphs", [])

    for sec in preferred:
        for p in paragraphs:
            if len(selected) >= max_items:
                break

            if p.get("section_guess", "").lower() == sec.lower():
                pid = parse_pid(p.get("paragraph_id"))
                if pid is not None and pid not in selected:
                    selected.append(pid)

        if len(selected) >= max_items:
            break

    if len(selected) < max_items:
        for p in paragraphs:
            if len(selected) >= max_items:
                break

            pid = parse_pid(p.get("paragraph_id"))
            if pid is not None and pid not in selected:
                selected.append(pid)

    return selected


def make_verified_item(pid, p):
    return {
        "paragraph_id": pid,
        "page_start": p.get("page_start", "?"),
        "page_end": p.get("page_end", p.get("page_start", "?")),
        "section_guess": p.get("section_guess", "Other"),
        "summary_sentence": p.get("summary_sentence", ""),
        "keywords": p.get("keywords", []),
        "difficulty_for_beginner": p.get("difficulty_for_beginner", ""),
        "source_excerpt": p.get("source_excerpt", "")
    }


def attach_verified_evidence(slide, pids, lookup):
    verified = []
    clean_ids = []

    for pid in pids:
        pid = parse_pid(pid)
        if pid is None:
            continue

        if pid in lookup and pid not in clean_ids:
            clean_ids.append(pid)
            verified.append(make_verified_item(pid, lookup[pid]))

    slide["evidence_paragraph_ids"] = clean_ids
    slide["verified_evidence"] = verified


def main():
    grounded = load_json(GROUNDED_PATH)
    paragraph_index = load_json(PARAGRAPH_INDEX_PATH)
    lookup = build_lookup(paragraph_index)

    fixed_by_existing_field = 0
    fixed_by_text = 0
    fixed_by_fallback = 0

    for slide in grounded.get("slides", []):
        raw_ids = slide.get("evidence_paragraph_ids", [])
        pids = []

        for x in raw_ids:
            pid = parse_pid(x)
            if pid is not None and pid not in pids:
                pids.append(pid)

        if pids:
            fixed_by_existing_field += 1

        if not pids:
            pids = extract_pids_from_slide(slide)
            if pids:
                fixed_by_text += 1

        if not pids:
            pids = fallback_select(slide, paragraph_index, max_items=3)
            fixed_by_fallback += 1

        attach_verified_evidence(slide, pids, lookup)

    save_json(grounded, GROUNDED_PATH)

    print(f"原字段已有 evidence 的页数：{fixed_by_existing_field}")
    print(f"从页面文字中提取 P 编号修复的页数：{fixed_by_text}")
    print(f"使用兜底逻辑修复的页数：{fixed_by_fallback}")


if __name__ == "__main__":
    main()
