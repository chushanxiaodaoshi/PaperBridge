from pathlib import Path
from agents import PaperUnderstandingAgent, save_json


def main():
    paper_text_path = Path("outputs/paper_text.txt")

    if not paper_text_path.exists():
        raise FileNotFoundError("找不到 outputs/paper_text.txt，请先完成 PDF 解析。")

    paper_text = paper_text_path.read_text(encoding="utf-8")

    learner_level = "beginner, has little background in reinforcement learning and robotics"
    explain_style = explain_style = "中文讲解，面向初学者，要求清晰、准确、克制；先讲问题和直觉，再讲方法；不要使用幼稚比喻或夸张口号"

    agent = PaperUnderstandingAgent()

    print("正在调用 Qwen 分析论文，请稍等...")
    analysis = agent.analyze(
        paper_text=paper_text,
        learner_level=learner_level,
        explain_style=explain_style
    )

    save_json(analysis, "outputs/paper_analysis.json")

    print("论文结构化分析完成。")
    print("标题：", analysis.get("paper_title", "未知"))
    print("一句话总结：", analysis.get("one_sentence_summary", "未知"))


if __name__ == "__main__":
    main()