import json
from pathlib import Path

from llm_client import LLMClient
from agents import extract_json_from_text


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(data, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"已保存：{path}")


def compact_slide_for_narration(slide):
    evidence = []

    for ev in slide.get("verified_evidence", [])[:4]:
        evidence.append({
            "paragraph_id": ev.get("paragraph_id"),
            "page": ev.get("page_start"),
            "section": ev.get("section_guess"),
            "summary": ev.get("summary_sentence"),
            "source_excerpt": ev.get("source_excerpt", "")
        })

    return {
        "slide_no": slide.get("slide_no"),
        "title": slide.get("title"),
        "purpose": slide.get("purpose"),
        "main_points": slide.get("main_points", []),
        "evidence": evidence,
        "visual_type": slide.get("visual_type", ""),
        "narration_focus": slide.get("narration_focus", "")
    }


def generate_narration(
    analysis_path: str = "outputs/paper_analysis.json",
    grounded_path: str = "outputs/grounded_slides.json",
    output_json_path: str = "outputs/narration.json",
    output_md_path: str = "outputs/narration.md",
):
    analysis = load_json(analysis_path)
    grounded = load_json(grounded_path)

    slides = grounded.get("slides", [])
    compact_slides = [compact_slide_for_narration(s) for s in slides]

    glossary = grounded.get("global_glossary", [])

    llm = LLMClient()

    system_prompt = """
你是一个认真、清晰、克制的中文课程讲解老师。
你的任务是根据 PPT 页面和论文证据，生成适合配音的讲解稿。

核心原则：
1. PPT 只是提纲，不要照读 PPT。
2. 讲解稿要补充 PPT 背后的逻辑、原因、论文依据和理解路径。
3. 面向初学者，但不要幼稚化。
4. 不要使用夸张比喻、网络化表达、口号式表达。
5. 不要使用“虚拟狗”“现实劳模”“体检报告”“健康档案”“高考模拟卷”“平行宇宙”“DNA”“玄学”“骗仿真器”等表达。
6. 语言要简洁直白，直击痛点。
7. 每一页都要围绕“这页到底帮听众解决什么理解问题”来讲。
8. 可以解释术语，但要准确克制。
9. 不要编造论文没有的信息。
10. 请严格输出 JSON，不要输出额外解释。
"""

    user_prompt = f"""
下面是论文分析结果、PPT 页面内容、论文证据和术语表。

论文整体分析：
{json.dumps(analysis, ensure_ascii=False, indent=2)}

PPT 页面内容和证据：
{json.dumps(compact_slides, ensure_ascii=False, indent=2)}

术语表：
{json.dumps(glossary, ensure_ascii=False, indent=2)}

请为每一页生成中文讲解稿。

要求：
1. 一共生成和 PPT slides 数量一致的讲解稿。
2. 每页 130 到 220 个中文字。
3. 不要逐条复述 main_points。
4. 每页讲解结构建议：
   - 先说明这一页要解决的理解问题；
   - 再展开 PPT 上没有写全的背景或逻辑；
   - 然后结合 evidence 说明论文依据；
   - 最后给出一句本页 takeaway。
5. 如果 PPT 上有专业术语，可以自然解释，但不要把术语表逐条念一遍。
6. 讲解稿要比 PPT 信息量更丰富，但不能跑题。
7. 语言风格：清晰、直接、克制、像助教讲课。
8. 保留 slide_no 和 title。
9. 严格输出 JSON。

输出格式：
{{
  "slides": [
    {{
      "slide_no": 1,
      "title": "标题",
      "narration": "这一页的讲解稿"
    }}
  ]
}}
"""

    print("正在调用 Qwen 生成非念稿式中文讲解稿...")
    response = llm.ask(prompt=user_prompt, system_prompt=system_prompt)
    data = extract_json_from_text(response)

    save_json(data, output_json_path)

    md_lines = ["# PaperBridge 中文讲解稿\n"]
    for slide in data.get("slides", []):
        md_lines.append(f"## Slide {slide.get('slide_no')}: {slide.get('title')}\n")
        md_lines.append(slide.get("narration", ""))
        md_lines.append("\n")

    Path(output_md_path).write_text("\n".join(md_lines), encoding="utf-8")
    print(f"讲解稿 Markdown 已保存：{output_md_path}")


if __name__ == "__main__":
    generate_narration()
