from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import fitz


logger = logging.getLogger(__name__)


class DocumentLoader:
    """Load text-layer PDF pages without changing the original extraction method."""

    def __init__(self, knowledge_dir: str | Path):
        self.knowledge_dir = Path(knowledge_dir).resolve()

    def scan_pdf_files(self) -> list[Path]:
        if not self.knowledge_dir.exists():
            return []
        return sorted(
            path
            for path in self.knowledge_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".pdf"
        )

    def extract_text_from_pdf(self, file_path: str | Path) -> list[dict[str, Any]]:
        pages_data: list[dict[str, Any]] = []
        path = Path(file_path)
        try:
            with fitz.open(path) as document:
                for page_num, page in enumerate(document):
                    text = page.get_text()
                    if text.strip():
                        pages_data.append(
                            {
                                "filename": path.name,
                                "page_number": page_num + 1,
                                "text": text.strip(),
                            }
                        )
        except Exception:
            logger.exception("PDF 解析失败: %s", path.name)
        return pages_data

    def load_all_documents(self) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        for pdf_file in self.scan_pdf_files():
            documents.extend(self.extract_text_from_pdf(pdf_file))
        return documents
