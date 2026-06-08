import fitz  # PyMuPDF
from pathlib import Path


def clear_old_named_outputs():
    try:
        output_dir = Path("outputs")
        for pattern in ["*_PaperBridge_Slides.pptx", "*_PaperBridge_Video.mp4"]:
            for p in output_dir.glob(pattern):
                p.unlink()
        meta = output_dir / "project_meta.json"
        if meta.exists():
            meta.unlink()
        print("已清理旧的命名输出文件。", flush=True)
    except Exception as e:
        print(f"清理旧命名文件失败，但不影响解析：{e}", flush=True)


def extract_text_from_pdf(pdf_path: str, output_path: str) -> str:
    """
    从 PDF 中提取文字，并保存到 txt 文件。
    """
    pdf_path = Path(pdf_path)
    output_path = Path(output_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"找不到 PDF 文件：{pdf_path}")

    doc = fitz.open(pdf_path)
    all_text = []

    for page_index, page in enumerate(doc):
        text = page.get_text("text")
        all_text.append(f"\n\n===== Page {page_index + 1} =====\n\n")
        all_text.append(text)

    full_text = "".join(all_text)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(full_text, encoding="utf-8")

    print(f"PDF 解析完成，共 {len(doc)} 页")
    print(f"文字已保存到：{output_path}")

    return full_text


if __name__ == "__main__":
    clear_old_named_outputs()
    extract_text_from_pdf(
        pdf_path="input/paper.pdf",
        output_path="outputs/paper_text.txt"
    )