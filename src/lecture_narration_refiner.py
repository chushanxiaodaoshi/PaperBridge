import json
from pathlib import Path

from llm_client import LLMClient
from agents import extract_json_from_text


NARRATION_PATH = "outputs/narration.json"
OUTPUT_JSON_PATH = "outputs/narration.json"
OUTPUT_MD_PATH = "outputs/narration.md"


STYLE_RULES = """
你要把讲解稿改成“清晰有节奏的课堂口播”。

要求：
1. 不要照读 PPT。
2. 每页先指出这页要解决的核心问题。
3. 语言要直接、清楚、有节奏。
4. 允许使用问题句，例如“那问题来了……”
5. 允许短句和停顿，让 TTS 更像讲课。
6. 不要使用幼稚比喻。
7. 不要模仿任何真实老师、主播或具体人物。
8. 不要使用网络化表达、夸张口号。
9. 不要说“虚拟狗”“现实劳模”“体检报告”“高考模拟卷”“平行宇宙”“DNA”“玄学”“骗仿真器”等表达。
10. 可以用“注意”“关键是”“换句话说”“这一页你只要抓住一点”这类课堂连接语。
11. 每页 140 到 230 个中文字。
12. 内容要比 PPT 更丰富，但不能跑题。
13. 不要编造论文没有的信息。
"""


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(data, path):
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"已保存：{path}")


def save_md(data, path):
    lines = ["# PaperBridge 中文讲解稿\n"]

    for slide in data.get("slides", []):
        lines.append(f"## Slide {slide.get('slide_no')}: {slide.get('title')}\n")
        lines.append(slide.get("narration", ""))
        lines.append("\n")

    Path(path).write_text("\n".join(lines), encoding="utf-8")
    print(f"已保存：{path}")


def main():
    data = load_json(NARRATION_PATH)

    llm = LLMClient()

    system_prompt = f"""
你是一个中文课程讲解稿编辑助手。
你负责把普通讲解稿改成适合 TTS 配音的课堂口播稿。
请严格输出 JSON。
{STYLE_RULES}
"""

    user_prompt = f"""
下面是当前讲解稿：

{json.dumps(data, ensure_ascii=False, indent=2)}

请重写每一页 narration。

输出格式：
{{
  "slides": [
    {{
      "slide_no": 1,
      "title": "标题",
      "narration": "重写后的讲解稿"
    }}
  ]
}}
"""

    print("正在重写讲解稿为课堂口播风格...")
    response = llm.ask(prompt=user_prompt, system_prompt=system_prompt)
    refined = extract_json_from_text(response)

    backup_path = Path(NARRATION_PATH).with_suffix(".json.bak")
    backup_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"已备份：{backup_path}")

    save_json(refined, OUTPUT_JSON_PATH)
    save_md(refined, OUTPUT_MD_PATH)

    print("课堂口播稿优化完成。")


if __name__ == "__main__":
    main()
