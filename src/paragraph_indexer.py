import json
import re
from pathlib import Path

from llm_client import LLMClient
from agents import extract_json_from_text


def split_pages(text: str):
    """
    根据 ===== Page n ===== 标记切分页面。
    """
    parts = re.split(r"===== Page (\d+) =====", text)
    pages = []

    # parts 格式：["", "1", "page1 text", "2", "page2 text", ...]
    for i in range(1, len(parts), 2):
        page_no = int(parts[i])
        page_text = parts[i + 1]
        pages.append({
            "page_no": page_no,
            "text": page_text
        })

    return pages


def clean_paragraph(p: str) -> str:
    p = p.strip()
    p = re.sub(r"\s+", " ", p)
    return p


def split_page_into_blocks(page_text: str):
    """
    将每页文本切成较粗的证据块。
    这里不追求完美自然段，而是生成适合引用的 evidence block。
    """
    lines = [line.strip() for line in page_text.splitlines() if line.strip()]

    blocks = []
    current = []

    for line in lines:
        # 过滤明显无意义行
        if re.fullmatch(r"\d+", line):
            continue
        if line.startswith("Prepared using"):
            continue

        current.append(line)

        joined = " ".join(current)

        # 达到一定长度就切一块
        if len(joined) >= 900:
            blocks.append(clean_paragraph(joined))
            current = []

    if current:
        joined = clean_paragraph(" ".join(current))
        if len(joined) >= 180:
            blocks.append(joined)

    return blocks


def build_located_blocks(paper_text: str):
    pages = split_pages(paper_text)

    blocks = []
    pid = 1

    for page in pages:
        page_no = page["page_no"]
        page_blocks = split_page_into_blocks(page["text"])

        for block in page_blocks:
            # 截断 references 之后内容
            if block.lower().startswith("references"):
                return blocks

            blocks.append({
                "paragraph_id": pid,
                "page_start": page_no,
                "page_end": page_no,
                "original_text": block,
                "source_excerpt": block[:260]
            })
            pid += 1

    return blocks


def chunk_list(items, chunk_size):
    for i in range(0, len(items), chunk_size):
        yield items[i:i + chunk_size]


class ParagraphIndexAgent:
    def __init__(self):
        self.llm = LLMClient()

    def summarize_batch(self, batch):
        system_prompt = """
你是一个严谨的论文阅读助手。
你的任务是为每个 evidence block 生成一句准确中文总结。
不要发挥，不要添加原文没有的信息。
请严格输出 JSON。
"""

        block_text = ""
        for item in batch:
            pid = item["paragraph_id"]
            page = item["page_start"]
            text = item["original_text"]
            block_text += f"\n[P{pid} | Page {page}]\n{text}\n"

        user_prompt = f"""
下面是论文中的若干 evidence block。
请为每个 block 生成结构化信息。

要求：
1. paragraph_id 必须只输出纯数字，例如 49，不要输出 P49，不要输出 Page 信息。
2. section_guess 从 Introduction / Related Work / Method / Experiments / Results / Discussion / Conclusion / Other 中选择。
3. summary_sentence 必须是一句中文总结。
4. keywords 给 3 到 6 个。
5. difficulty_for_beginner 说明小白可能卡在哪里。
6. 不要编造原文没有的信息。
7. 严格输出 JSON。

Evidence blocks:
{block_text}

输出格式：
{{
  "paragraphs": [
    {{
      "paragraph_id": 1,
      "section_guess": "Introduction",
      "summary_sentence": "这一段主要说明……",
      "keywords": ["关键词1", "关键词2"],
      "difficulty_for_beginner": "小白可能不理解……"
    }}
  ]
}}
"""

        response = self.llm.ask(prompt=user_prompt, system_prompt=system_prompt)
        return extract_json_from_text(response)

    def build_index(self, paper_text_path, output_path):
        paper_text = Path(paper_text_path).read_text(encoding="utf-8")
        blocks = build_located_blocks(paper_text)

        print(f"共切分出 {len(blocks)} 个带页码 evidence block。")

        all_items = []

        for batch in chunk_list(blocks, 6):
            start_id = batch[0]["paragraph_id"]
            end_id = batch[-1]["paragraph_id"]
            print(f"正在总结 P{start_id} 到 P{end_id}...")

            result = self.summarize_batch(batch)
            summarized = result.get("paragraphs", [])

            def parse_paragraph_id(value):
                """
                支持 49、"49"、"P49"、"P49 | Page 12" 等格式。
                """
                if value is None:
                    return None

                if isinstance(value, int):
                    return value

                match = re.search(r"\d+", str(value))
                if not match:
                    return None

                return int(match.group(0))

            summary_lookup = {}
            for item in summarized:
                pid = parse_paragraph_id(item.get("paragraph_id"))
                if pid is not None:
                    summary_lookup[pid] = item

            for block in batch:
                pid = block["paragraph_id"]
                item = summary_lookup.get(pid, {})

                all_items.append({
                    "paragraph_id": pid,
                    "page_start": block["page_start"],
                    "page_end": block["page_end"],
                    "section_guess": item.get("section_guess", "Other"),
                    "summary_sentence": item.get("summary_sentence", ""),
                    "keywords": item.get("keywords", []),
                    "difficulty_for_beginner": item.get("difficulty_for_beginner", ""),
                    "source_excerpt": block["source_excerpt"],
                    "original_text": block["original_text"]
                })

        output = {
            "num_paragraphs": len(all_items),
            "paragraphs": all_items
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        print(f"带页码段落索引已保存：{output_path}")


if __name__ == "__main__":
    agent = ParagraphIndexAgent()
    agent.build_index(
        paper_text_path="outputs/paper_text.txt",
        output_path="outputs/paragraph_index.json"
    )
