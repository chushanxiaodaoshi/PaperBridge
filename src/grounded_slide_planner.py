import json
import re
from pathlib import Path

from llm_client import LLMClient
def load_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(data: dict, path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"已保存：{path}")




def extract_json_candidate(text: str) -> str:
    """
    从大模型回复中提取 JSON 候选文本。
    支持：
    1. ```json ... ``` 代码块
    2. 普通文本中夹着一个 JSON 对象
    """
    text = str(text).strip()

    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    if fence:
        text = fence.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("模型回复中没有找到完整的 JSON 对象。")

    return text[start:end + 1]


def remove_invalid_control_chars(text: str) -> str:
    """
    JSON 字符串里不能出现某些不可见控制字符。
    这里保留 \n、\r、\t，去掉其它 ASCII 控制字符。
    """
    return "".join(
        ch for ch in text
        if ch in "\n\r\t" or ord(ch) >= 32
    )


def parse_json_strict(text: str) -> dict:
    candidate = extract_json_candidate(text)
    candidate = remove_invalid_control_chars(candidate)
    return json.loads(candidate)


def parse_json_with_llm_repair(llm: LLMClient, response: str, debug_prefix: str) -> dict:
    """
    第一次严格解析。
    如果失败，把原始回复保存下来，再让大模型只做 JSON 语法修复。
    这样可以避免因为少逗号、非法引号、控制字符等问题导致整个流程中断。
    """
    debug_dir = Path("outputs/debug")
    debug_dir.mkdir(parents=True, exist_ok=True)

    try:
        return parse_json_strict(response)
    except Exception as e:
        raw_path = debug_dir / f"{debug_prefix}_raw_response.txt"
        raw_path.write_text(str(response), encoding="utf-8", errors="replace")
        print(f"第一次 JSON 解析失败，已保存原始回复：{raw_path}")
        print(f"错误信息：{repr(e)}")

        try:
            candidate = extract_json_candidate(response)
        except Exception:
            candidate = str(response)

        candidate = remove_invalid_control_chars(candidate)
        bad_json_path = debug_dir / f"{debug_prefix}_bad_json_candidate.txt"
        bad_json_path.write_text(candidate, encoding="utf-8", errors="replace")

        repair_prompt = f"""
下面这段内容本应是严格合法的 JSON，但现在存在语法错误。

请你只做 JSON 语法修复，不要改变字段含义，不要增删主要内容。
请严格输出一个完整 JSON 对象，不要输出 Markdown，不要输出解释。

要求：
1. 所有 key 必须使用英文双引号。
2. 字符串必须使用英文双引号。
3. 删除非法控制字符。
4. 修复多余逗号、缺失逗号、未转义引号等问题。
5. 保持 paper_title、slides、mind_map、method_flow 等字段结构。
6. 最终回复只能是 JSON。

原始错误 JSON：
{candidate}
"""

        print("正在调用大模型修复 JSON 格式...")
        repaired = llm.ask(
            prompt=repair_prompt,
            system_prompt="你是一个严格的 JSON 修复器。你只能输出合法 JSON，不要输出任何解释。"
        )

        repaired_path = debug_dir / f"{debug_prefix}_repaired_response.txt"
        repaired_path.write_text(str(repaired), encoding="utf-8", errors="replace")
        print(f"已保存修复后的回复：{repaired_path}")

        return parse_json_strict(repaired)

def parse_pid_value(value):
    """
    支持 9、"9"、"P9"、"p9"、"PP9" 等格式。
    模型有时会把 evidence_paragraph_ids 写成 ["P9"]，
    这里统一解析成整数 9。
    """
    m = re.search(r"\d+", str(value))
    return int(m.group(0)) if m else None


def build_compact_paragraph_index(paragraph_index: dict, max_paragraphs: int = 120) -> str:
    """
    只把 paragraph_id、section_guess、summary_sentence、keywords 给模型。
    不直接塞 original_text，避免 prompt 过长。
    """
    paragraphs = paragraph_index.get("paragraphs", [])[:max_paragraphs]

    lines = []
    for p in paragraphs:
        pid = p.get("paragraph_id")
        section = p.get("section_guess", "Other")
        summary = p.get("summary_sentence", "")
        keywords = ", ".join(p.get("keywords", []))

        lines.append(
            f"[P{pid}] section={section}; summary={summary}; keywords={keywords}"
        )

    return "\n".join(lines)


def build_paragraph_lookup(paragraph_index: dict):
    lookup = {}
    for p in paragraph_index.get("paragraphs", []):
        pid = p.get("paragraph_id")
        if pid is not None:
            lookup[int(pid)] = p
    return lookup


def attach_verified_evidence(grounded_data: dict, paragraph_lookup: dict) -> dict:
    """
    模型负责选择 paragraph_id。
    程序负责把真实 paragraph summary 附上去，避免模型自己编 evidence summary。

    兼容 evidence_paragraph_ids 的多种写法：
    [9, 10, 42]
    ["9", "10", "42"]
    ["P9", "P10", "P42"]
    """
    for slide in grounded_data.get("slides", []):
        ids = slide.get("evidence_paragraph_ids", [])
        verified = []

        clean_ids = []
        for raw_pid in ids:
            pid = parse_pid_value(raw_pid)
            if pid is None:
                continue

            if pid in paragraph_lookup and pid not in clean_ids:
                clean_ids.append(pid)
                p = paragraph_lookup[pid]
                verified.append({
                    "paragraph_id": pid,
                    "section_guess": p.get("section_guess", "Other"),
                    "summary_sentence": p.get("summary_sentence", ""),
                    "keywords": p.get("keywords", []),
                    "difficulty_for_beginner": p.get("difficulty_for_beginner", "")
                })

        slide["evidence_paragraph_ids"] = clean_ids
        slide["verified_evidence"] = verified

    return grounded_data


class GroundedSlidePlannerAgent:
    """
    Grounded Slide Planner:
    基于论文段落索引，为每页 PPT 选择真实论文依据。
    """

    def __init__(self):
        self.llm = LLMClient()

    def plan(self, analysis: dict, paragraph_index: dict) -> dict:
        compact_index = build_compact_paragraph_index(paragraph_index)
        paper_title = analysis.get("paper_title", "Unknown Paper")

        system_prompt = """
你是一个严谨的论文讲解课件规划助手。
你的任务不是自由发挥，而是基于给定的论文段落索引，规划一套面向小白的讲解 PPT。
每一页都必须选择相关的 evidence_paragraph_ids。
如果某一页是学习路径或总结页，也要尽量引用最相关的段落作为依据。
请严格输出 JSON，不要输出额外解释。
"""

        user_prompt = f"""
现在要为一篇论文生成“有论文依据”的中文讲解 PPT。

论文标题：
{paper_title}

已有的整篇论文分析：
{json.dumps(analysis, ensure_ascii=False, indent=2)}

论文段落索引：
{compact_index}

请生成一个 grounded slide plan。

要求：
1. 一共 10 页。
2. 每页要有 title、purpose、main_points、evidence_paragraph_ids、visual_type、layout_hint、narration_focus。
3. main_points 必须紧扣 evidence_paragraph_ids 对应段落，不要脱离论文。
4. evidence_paragraph_ids 每页选 2 到 5 个，必须从段落索引中的 [P数字] 选择，但输出时必须写成纯数字数组，例如 [9, 10, 42]，不要写 [P9, P10]，也不要写 [\"P9\", \"P10\"]。
5. 第 5 页必须是真正的层级思维导图，不要只是 Background / Method / Experiments / Conclusion 四个卡片。
6. 思维导图要体现：
   - 前置知识
   - 论文问题
   - 核心方法
   - 实验验证
   - 小白读完应该形成的理解
7. 第 6 页必须是方法流程图。
8. 不要编造论文没有的内容。
9. 输出必须是 JSON。

请严格按照下面格式输出：

{{
  "paper_title": "论文标题",
  "slides": [
    {{
      "slide_no": 1,
      "title": "标题页",
      "purpose": "这一页的教学目的",
      "main_points": [
        "这一页的要点1",
        "这一页的要点2"
      ],
      "evidence_paragraph_ids": [1, 2],
      "visual_type": "title",
      "layout_hint": "标题 + 一句话总结 + 论文来源段落摘要",
      "narration_focus": "讲解稿应重点说明什么"
    }}
  ],
  "mind_map": {{
    "root": "论文标题或核心主题",
    "children": [
      {{
        "name": "Prerequisite Knowledge",
        "children": [
          {{
            "name": "知识点1",
            "children": []
          }}
        ]
      }},
      {{
        "name": "Research Problem",
        "children": []
      }},
      {{
        "name": "Core Method",
        "children": []
      }},
      {{
        "name": "Experiments",
        "children": []
      }},
      {{
        "name": "Takeaways",
        "children": []
      }}
    ]
  }},
  "method_flow": [
    {{
      "step_no": 1,
      "name": "步骤名称",
      "description": "这一步做什么",
      "evidence_paragraph_ids": [3, 4]
    }}
  ]
}}

10 页 PPT 固定对应：
1. 标题页
2. 这篇论文在解决什么问题
3. 读懂它需要哪些前置知识
4. 推荐学习路径
5. 真正的论文理解思维导图
6. 核心方法流程图
7. 关键概念解释
8. 小白容易卡住的地方
9. 读完这篇论文应该记住什么
10. 自测题
"""

        print("正在调用大模型生成 grounded slide plan...")
        response = self.llm.ask(
            prompt=user_prompt,
            system_prompt=system_prompt
        )

        return parse_json_with_llm_repair(self.llm, response, "grounded_slide_planner")


def main():
    analysis = load_json("outputs/paper_analysis.json")
    paragraph_index = load_json("outputs/paragraph_index.json")

    agent = GroundedSlidePlannerAgent()
    grounded = agent.plan(analysis, paragraph_index)

    paragraph_lookup = build_paragraph_lookup(paragraph_index)
    grounded = attach_verified_evidence(grounded, paragraph_lookup)

    save_json(grounded, "outputs/grounded_slides.json")

    print("Grounded slide plan 生成完成。")
    print("建议检查 outputs/grounded_slides.json 中每页的 verified_evidence。")


if __name__ == "__main__":
    main()
