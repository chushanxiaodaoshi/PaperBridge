import json
from pathlib import Path

from llm_client import LLMClient
from agents import extract_json_from_text


GROUNDED_PATH = "outputs/grounded_slides.json"
NARRATION_PATH = "outputs/narration.json"
NARRATION_MD_PATH = "outputs/narration.md"


STYLE_RULES = """
总体风格要求：
1. 面向初学者，但不要幼稚化。
2. 表达要清晰、准确、克制，像助教在讲课。
3. 可以解释专业概念，但不要使用夸张口号或娱乐化比喻。
4. 不要使用“虚拟狗”“现实劳模”“身体脾气”“体检报告”“健康档案”“高考模拟卷”“平行宇宙”“Auto-Tune”“DNA”“玄学”“骗仿真器”“闪光点”“平民版”等表达。
5. 不要说“初中物理”“小白也能懂”这类降低专业感的句子。
6. 可以用“可以理解为”“其核心作用是”“直观地说”这类解释方式。
7. 保留必要的专业词，并让解释更准确。
8. 不要改变 Pxx 证据编号。
9. 不要编造论文没有的内容。
"""


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(data, path):
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"已保存：{path}")


def backup(path):
    p = Path(path)
    if p.exists():
        backup_path = p.with_suffix(p.suffix + ".bak")
        backup_path.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"已备份：{backup_path}")


def compact_grounded(data):
    slides = []
    for s in data.get("slides", []):
        slides.append({
            "slide_no": s.get("slide_no"),
            "title": s.get("title"),
            "purpose": s.get("purpose"),
            "main_points": s.get("main_points", []),
            "narration_focus": s.get("narration_focus", ""),
            "visual_type": s.get("visual_type", ""),
            "evidence_paragraph_ids": s.get("evidence_paragraph_ids", []),
        })

    return {
        "paper_title": data.get("paper_title", ""),
        "slides": slides,
        "mind_map": data.get("mind_map", {}),
        "method_flow": data.get("method_flow", []),
    }


def refine_grounded_slides():
    data = load_json(GROUNDED_PATH)
    compact = compact_grounded(data)

    llm = LLMClient()

    system_prompt = f"""
你是一个论文课件文案编辑助手。
你的任务是把已有 PPT 文案改得更清晰、准确、克制。
不要改变结构，不要改变证据编号，不要编造新内容。
请严格输出 JSON。
{STYLE_RULES}
"""

    user_prompt = f"""
下面是当前 PPT 的结构化内容。

{json.dumps(compact, ensure_ascii=False, indent=2)}

请重写其中的：
- title
- purpose
- main_points
- narration_focus
- mind_map 中的节点文字
- method_flow 中的 name 和 description

要求：
1. 保留 slide_no。
2. 保留 evidence_paragraph_ids。
3. main_points 仍然保持每页 2 到 4 条。
4. 如果原文中有 P19、P35 这种证据编号，必须保留。
5. 标题不要追求吸引眼球，要准确。
6. 输出 JSON 格式必须与输入一致。

输出格式：
{{
  "paper_title": "...",
  "slides": [
    {{
      "slide_no": 1,
      "title": "...",
      "purpose": "...",
      "main_points": ["...", "..."],
      "narration_focus": "...",
      "visual_type": "...",
      "evidence_paragraph_ids": []
    }}
  ],
  "mind_map": {{...}},
  "method_flow": [...]
}}
"""

    print("正在重写 PPT 文案风格...")
    response = llm.ask(prompt=user_prompt, system_prompt=system_prompt)
    refined = extract_json_from_text(response)

    refined_by_no = {
        int(s.get("slide_no")): s
        for s in refined.get("slides", [])
        if s.get("slide_no") is not None
    }

    for slide in data.get("slides", []):
        no = int(slide.get("slide_no", -1))
        new_slide = refined_by_no.get(no)
        if not new_slide:
            continue

        for key in ["title", "purpose", "main_points", "narration_focus", "visual_type"]:
            if key in new_slide:
                slide[key] = new_slide[key]

        # 删除旧的注释字段，后面重新生成术语注释
        slide.pop("annotated_title", None)
        slide.pop("annotated_main_points", None)
        slide.pop("term_explanations", None)

    if refined.get("mind_map"):
        data["mind_map"] = refined["mind_map"]

    if refined.get("method_flow"):
        data["method_flow"] = refined["method_flow"]

    data.pop("global_glossary", None)

    backup(GROUNDED_PATH)
    save_json(data, GROUNDED_PATH)


def refine_narration():
    if not Path(NARRATION_PATH).exists():
        print("没有找到 narration.json，跳过讲解稿重写。")
        return

    data = load_json(NARRATION_PATH)

    llm = LLMClient()

    system_prompt = f"""
你是一个中文课程讲解稿编辑助手。
你的任务是把讲解稿改得更清晰、自然、专业，但仍然适合初学者听。
不要改变页数，不要添加原文没有的信息。
请严格输出 JSON。
{STYLE_RULES}
"""

    user_prompt = f"""
下面是当前中文讲解稿：

{json.dumps(data, ensure_ascii=False, indent=2)}

请重写每页 narration。

要求：
1. 每页 100 到 180 个中文字。
2. 语言清晰自然，像助教讲课。
3. 不要使用幼稚比喻、网络化表达或夸张口号。
4. 可以解释术语，但用准确简洁的方式。
5. 保留每页 slide_no 和 title。
6. 严格输出 JSON。

输出格式：
{{
  "slides": [
    {{
      "slide_no": 1,
      "title": "标题页",
      "narration": "..."
    }}
  ]
}}
"""

    print("正在重写中文讲解稿风格...")
    response = llm.ask(prompt=user_prompt, system_prompt=system_prompt)
    refined = extract_json_from_text(response)

    backup(NARRATION_PATH)
    save_json(refined, NARRATION_PATH)

    md_lines = ["# PaperBridge 中文讲解稿\n"]
    for slide in refined.get("slides", []):
        md_lines.append(f"## Slide {slide.get('slide_no')}: {slide.get('title')}\n")
        md_lines.append(slide.get("narration", ""))
        md_lines.append("\n")

    Path(NARRATION_MD_PATH).write_text("\n".join(md_lines), encoding="utf-8")
    print(f"已保存：{NARRATION_MD_PATH}")


def main():
    refine_grounded_slides()
    refine_narration()
    print("文案风格优化完成。接下来请重新生成术语注释和 PPT。")


if __name__ == "__main__":
    main()
