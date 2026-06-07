import json
import re
from pathlib import Path

from llm_client import LLMClient
from agents import extract_json_from_text


GROUNDED_PATH = "outputs/grounded_slides.json"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(data, path):
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"已保存：{path}")


def make_marker(index):
    """
    使用 〔1〕 这种编号，数量不限。
    """
    return f"〔{index}〕"


def normalize_key(term):
    return re.sub(r"\s+", " ", str(term).strip().lower())


def collect_slide_texts(grounded):
    slides_text = []

    for slide in grounded.get("slides", []):
        parts = []

        parts.append(f"Slide {slide.get('slide_no')}: {slide.get('title', '')}")
        parts.append(slide.get("purpose", ""))

        for p in slide.get("main_points", []):
            parts.append(str(p))

        for ev in slide.get("verified_evidence", []):
            parts.append(ev.get("summary_sentence", ""))
            parts.append(ev.get("source_excerpt", ""))

        slides_text.append({
            "slide_no": slide.get("slide_no"),
            "text": "\n".join(parts)
        })

    return slides_text


class GlobalGlossaryAgent:
    def __init__(self):
        self.llm = LLMClient()

    def generate_glossary(self, grounded):
        slides_text = collect_slide_texts(grounded)

        system_prompt = """
你是一个严谨的论文课件术语提取助手。
你的任务是从整套 PPT 内容中提取所有会影响小白理解的专业术语，并给出简短解释。
注意：不是挑选少数术语，而是尽可能完整地覆盖 PPT 中出现的专业术语。
请严格输出 JSON，不要输出额外解释。
"""

        user_prompt = f"""
下面是一套论文讲解 PPT 的全部可见内容和相关 evidence。

PPT 内容：
{json.dumps(slides_text, ensure_ascii=False, indent=2)}

请提取这套 PPT 中出现的所有专业术语。

专业术语包括但不限于：
- 机器人、控制、强化学习、仿真、系统辨识、能耗建模相关术语
- 英文缩写，如 RL、PMSM、PPO、CMA-ES、CoT
- 中英文混合术语，如 sim-to-real gap、domain randomization、reward function
- 对小白来说需要解释的论文关键词

要求：
1. 尽可能完整，不要限制为 8 到 12 个。
2. 只提取 PPT 中真实出现或强相关的术语。
3. 全局去重，同义词合并；例如“仿真到现实迁移”和“sim-to-real”可以放同一个术语。
4. explanation 控制在 45 个中文字以内。
5. explanation 要像老师讲课，通俗准确，不要像百科词条。
6. first_slide_no 写这个术语最早出现在哪一页。
7. 严格输出 JSON。

输出格式：
{{
  "glossary": [
    {{
      "term": "sim-to-real gap",
      "aliases": ["仿真到现实鸿沟", "sim-to-real"],
      "explanation": "仿真里表现好，但真机表现变差的差距。",
      "first_slide_no": 2
    }}
  ]
}}
"""

        response = self.llm.ask(prompt=user_prompt, system_prompt=system_prompt)
        data = extract_json_from_text(response)
        return data.get("glossary", [])


def postprocess_glossary(raw_glossary):
    final = []
    seen = set()

    for item in raw_glossary:
        term = str(item.get("term", "")).strip()
        explanation = str(item.get("explanation", "")).strip()

        if not term or not explanation:
            continue

        key = normalize_key(term)
        aliases = item.get("aliases", [])
        alias_keys = [normalize_key(x) for x in aliases]

        # term 或 alias 已经出现过，就跳过
        if key in seen or any(k in seen for k in alias_keys):
            continue

        seen.add(key)
        for k in alias_keys:
            seen.add(k)

        final.append({
            "marker": make_marker(len(final) + 1),
            "term": term,
            "aliases": aliases,
            "explanation": explanation,
            "first_slide_no": item.get("first_slide_no", "?")
        })

    return final


def term_variants(item):
    variants = [item.get("term", "")]
    variants += item.get("aliases", [])

    clean = []
    for v in variants:
        v = str(v).strip()
        if v and v not in clean:
            clean.append(v)

    # 长词优先，避免 sim-to-real 先于 sim-to-real gap 被替换
    clean.sort(key=len, reverse=True)
    return clean


def annotate_once(text, glossary, used_terms):
    """
    对文本中的术语加注释。
    每个术语在整套 PPT 中只标第一次，避免满屏都是编号。
    """
    result = str(text)

    # 长术语优先
    items = sorted(glossary, key=lambda x: len(x.get("term", "")), reverse=True)

    for item in items:
        marker = item.get("marker", "")
        term_key = normalize_key(item.get("term", ""))

        if not marker or not term_key:
            continue

        if term_key in used_terms:
            continue

        for variant in term_variants(item):
            if not variant:
                continue

            if variant in result:
                result = result.replace(variant, f"{variant}{marker}", 1)
                used_terms.add(term_key)
                break

    return result


def annotate_slides(grounded, glossary):
    used_terms = set()

    for slide in grounded.get("slides", []):
        title = slide.get("title", "")
        slide["annotated_title"] = annotate_once(title, glossary, used_terms)

        annotated_points = []
        for point in slide.get("main_points", []):
            annotated_points.append(annotate_once(point, glossary, used_terms))

        slide["annotated_main_points"] = annotated_points

    return grounded


def main():
    grounded = load_json(GROUNDED_PATH)

    print("正在生成全局专业术语表，请稍等...")
    agent = GlobalGlossaryAgent()
    raw_glossary = agent.generate_glossary(grounded)

    glossary = postprocess_glossary(raw_glossary)

    grounded["global_glossary"] = glossary
    grounded = annotate_slides(grounded, glossary)

    save_json(grounded, GROUNDED_PATH)

    print(f"共生成 {len(glossary)} 个专业术语：")
    for item in glossary:
        print(f'{item["marker"]} {item["term"]}: {item["explanation"]}')


if __name__ == "__main__":
    main()
