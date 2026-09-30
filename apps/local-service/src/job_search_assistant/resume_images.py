from __future__ import annotations

import hashlib
from pathlib import Path


def render_pdf_first_page(content: bytes, output_dir: Path) -> Path:
    """Render a PDF first page as a local PNG suitable for chat attachment."""
    try:
        import fitz
    except ImportError as error:  # pragma: no cover - deployment dependency guard
        raise RuntimeError("PDF 图片渲染组件未安装") from error

    output_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(content).hexdigest()
    output_path = output_dir / f"{digest}-page-1.png"
    if output_path.exists():
        return output_path
    try:
        document = fitz.open(stream=content, filetype="pdf")
        if document.page_count < 1:
            raise RuntimeError("PDF 没有可渲染页面")
        page = document.load_page(0)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        pixmap.save(output_path)
        document.close()
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError("PDF 第一页图片生成失败") from error
    return output_path
