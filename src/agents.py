import json
import re
from pathlib import Path
from llm_client import LLMClient


def extract_json_from_text(text: str) -> dict:
    """
    尝试从大模型回复中提取 JSON。
    """
    text = text.strip()

    # 如果模型直接返回纯 JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 如果模型返回 ```json ... ```
    match = re.search(r"```json\s*(.*?)\s*```", text, re.S)
    if match:
        return json.loads(match.group(1))

    # 如果模型前后有解释文字，尝试截取第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start:end + 1])

    raise ValueError("无法从模型回复中提取 JSON。")


class PaperUnderstandingAgent:
    """
    论文理解 Agent：
    负责从论文文本中提取结构化信息。
    """

    def __init__(self):
        self.llm = LLMClient()

    def analyze(self, paper_text: str, learner_level: str, explain_style: str) -> dict:
        # 第一版先限制长度，避免一次塞太多 token。
        # 如果你用 qwen-long，可以适当调大。
        paper_text = paper_text[:60000]

        system_prompt = """
你是一个面向论文小白的论文讲解助手。
你的任务不是简单总结论文，而是帮助学习者理解论文。
你需要识别论文主题、核心问题、前置知识、方法流程、实验结果和小白容易卡住的地方。
请严格输出 JSON，不要输出额外解释。
"""

        user_prompt = f"""
请分析下面这篇论文，并根据学习者水平和讲解风格生成结构化理解结果。

学习者水平：
{learner_level}

讲解风格：
{explain_style}

论文文本：
{paper_text}

请严格按照下面 JSON 格式输出：

{{
  "paper_title": "论文标题",
  "paper_field": "论文所属领域",
  "one_sentence_summary": "用一句话说明这篇论文在做什么",
  "main_problem": "这篇论文主要解决什么问题",
  "why_it_matters": "这个问题为什么重要",
  "prerequisite_knowledge": [
    {{
      "name": "前置知识点名称",
      "beginner_explanation": "给小白的解释",
      "why_needed": "为什么读这篇论文需要它"
    }}
  ],
  "learning_path": [
    "第1步：先理解什么",
    "第2步：再理解什么",
    "第3步：最后理解什么"
  ],
  "paper_structure": {{
    "background": "背景介绍",
    "method": "方法概述",
    "experiments": "实验概述",
    "conclusion": "结论概述"
  }},
  "method_flow": [
    "输入是什么",
    "经过什么模块",
    "如何训练或优化",
    "输出是什么"
  ],
  "key_concepts": [
    {{
      "name": "关键概念",
      "simple_explanation": "小白友好的解释"
    }}
  ],
  "beginner_difficulties": [
    {{
      "difficulty": "小白可能卡住的点",
      "explanation": "如何理解它"
    }}
  ],
  "takeaways": [
    "读完这篇论文最应该记住的点1",
    "读完这篇论文最应该记住的点2",
    "读完这篇论文最应该记住的点3"
  ],
  "quiz": [
    {{
      "question": "自测题",
      "answer": "参考答案"
    }}
  ]
}}
"""

        response = self.llm.ask(
            prompt=user_prompt,
            system_prompt=system_prompt
        )

        return extract_json_from_text(response)


def save_json(data: dict, output_path: str):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"已保存 JSON：{output_path}")
