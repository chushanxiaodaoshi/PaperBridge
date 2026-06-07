import json
from pathlib import Path

from llm_client import LLMClient
from agents import extract_json_from_text


def generate_narration(
    analysis_path: str = "outputs/paper_analysis.json",
    output_json_path: str = "outputs/narration.json",
    output_md_path: str = "outputs/narration.md",
):
    analysis = json.loads(Path(analysis_path).read_text(encoding="utf-8"))

    llm = LLMClient()

    system_prompt = """
你是一个擅长把论文讲给小白听的中文讲解老师。
你的任务是根据论文结构化分析结果，为每一页 PPT 生成中文讲解稿。
讲解要自然、清晰、适合配音，不要像论文摘要。
请严格输出 JSON，不要输出额外解释。
"""

    user_prompt = f"""
请根据下面的论文分析结果，为 10 页 PPT 生成中文讲解稿。

要求：
1. 每页讲解 100 到 180 个中文字左右。
2. 讲解对象是论文小白。
3. 语气自然，像老师在讲课。
4. 不要堆公式，先讲直觉，再讲结论。
5. 每页都要能独立配音。
6. 严格输出 JSON。

论文分析结果：
{json.dumps(analysis, ensure_ascii=False, indent=2)}

请按照下面格式输出：

{{
  "slides": [
    {{
      "slide_no": 1,
      "title": "标题页",
      "narration": "这一页的中文讲解稿"
    }},
    {{
      "slide_no": 2,
      "title": "这篇论文在做什么",
      "narration": "这一页的中文讲解稿"
    }}
  ]
}}

注意：一共生成 10 页，对应以下页面：
1. 标题页
2. 这篇论文在做什么
3. 前置知识
4. 推荐学习路径
5. 论文结构思维导图
6. 核心方法流程
7. 关键概念解释
8. 小白容易卡住的地方
9. 读完应该记住什么
10. 自测题
"""

    print("正在调用 Qwen 生成中文讲解稿...")
    response = llm.ask(prompt=user_prompt, system_prompt=system_prompt)
    data = extract_json_from_text(response)

    Path(output_json_path).parent.mkdir(parents=True, exist_ok=True)

    Path(output_json_path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    md_lines = ["# PaperBridge 中文讲解稿\n"]
    for slide in data.get("slides", []):
        md_lines.append(f"## Slide {slide.get('slide_no')}: {slide.get('title')}\n")
        md_lines.append(slide.get("narration", ""))
        md_lines.append("\n")

    Path(output_md_path).write_text("\n".join(md_lines), encoding="utf-8")

    print(f"讲解稿 JSON 已保存：{output_json_path}")
    print(f"讲解稿 Markdown 已保存：{output_md_path}")


if __name__ == "__main__":
    generate_narration()
