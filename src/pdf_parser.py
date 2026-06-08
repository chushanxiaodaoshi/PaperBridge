import fitz  # PyMuPDF
from pathlib import Path
import shutil

from project_namer import discover_input_pdf, finalize_input_pdf_name, reset_project_meta


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


def copy_named_pdf_to_outputs(named_pdf: Path):
    # 将重命名后的论文 PDF 复制到 outputs 目录。
    # 最终 outputs 中会保留：
    # - <项目名>_paper.pdf
    # - <项目名>_PaperBridge_Slides.pptx
    # - <项目名>_PaperBridge_Video.mp4
    named_pdf = Path(named_pdf)
    if not named_pdf.exists():
        return None

    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    dst_pdf = output_dir / named_pdf.name
    if named_pdf.resolve() != dst_pdf.resolve():
        shutil.copy2(named_pdf, dst_pdf)

    return dst_pdf

if __name__ == "__main__":
    pdf_path = discover_input_pdf()
    print(f"当前解析 PDF：{pdf_path}", flush=True)

    # 每次解析 PDF 都认为是在处理一篇新论文，重新推断项目名。
    reset_project_meta()

    extract_text_from_pdf(
        pdf_path=str(pdf_path),
        output_path="outputs/paper_text.txt"
    )

    named_pdf = finalize_input_pdf_name(pdf_path, remove_old=True, verbose=True)
    if named_pdf:
        print(f"输入 PDF 已重命名为：{named_pdf}", flush=True)

        output_pdf = copy_named_pdf_to_outputs(named_pdf)
        if output_pdf:
            print(f"原论文 PDF 已复制到 outputs：{output_pdf}", flush=True)
