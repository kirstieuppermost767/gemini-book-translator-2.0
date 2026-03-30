import re
import logging
import fitz
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict

logger = logging.getLogger(__name__)


class PDFExtractor:
    """
    Converts a PDF book into a structured Markdown file.
    Handles header detection, italic formatting, margin filtering,
    and hyphenation cleanup.
    """

    def __init__(self, config) -> None:
        self.cfg = config
        self.doc = None
        self.full_text: List[str] = []

    # ------------------------------------------------------------------ #
    #  Public entry point                                                  #
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        """Execute the full extraction pipeline."""
        logger.info("Starting PDF extraction...")
        self._load_document()
        self._extract_content()
        self._save_markdown()
        if self.doc:
            self.doc.close()
        logger.info("PDF extraction complete.")

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    def _load_document(self) -> None:
        """Load the PDF from disk."""
        input_path = Path(self.cfg.INPUT_PDF)
        if not input_path.exists():
            raise FileNotFoundError(f"PDF not found: {input_path}")

        self.doc = fitz.open(str(input_path))
        logger.info(
            "Loaded '%s' — %d pages total.", self.doc.name, self.doc.page_count
        )

    def _is_italic(self, font_flags: int) -> bool:
        """Return True if bit 1 (value 2) of the font flags is set."""
        return bool(font_flags & 2)

    def _is_header(self, span: Dict) -> bool:
        """A span is a chapter header when its font size meets the threshold."""
        return span["size"] >= self.cfg.HEADER_MIN_SIZE

    def _in_valid_area(self, bbox: List[float]) -> bool:
        """
        Reject text blocks that fall inside the page header/footer margins.
        bbox = [x0, y0, x1, y1]
        """
        y0, y1 = bbox[1], bbox[3]
        return y0 > self.cfg.MARGIN_TOP and y1 < self.cfg.MARGIN_BOTTOM

    def _process_span(self, span: Dict) -> str:
        """
        Render a single text span.
        Wraps italic text in Markdown asterisks; ignores whitespace-only spans.
        """
        text: str = span["text"]
        if not text.strip():
            return ""
        if self._is_italic(span["flags"]):
            text = f"*{text.strip()}*"
        return text

    def _extract_content(self) -> None:
        """Iterate over every page and block, building the Markdown buffer."""
        logger.info("Extracting and converting content...")

        for page_num, page in enumerate(self.doc):
            if page_num in self.cfg.SKIP_PAGES:
                continue

            for block in page.get_text("dict")["blocks"]:
                if block.get("type") != 0:          
                    continue
                if not self._in_valid_area(block["bbox"]):
                    continue

                line_parts: List[str] = []
                is_header_block = False

                for line in block["lines"]:
                    span_parts: List[str] = []
                    for span in line["spans"]:
                        if self._is_header(span):
                            is_header_block = True
                        processed = self._process_span(span)
                        if processed:
                            span_parts.append(processed)

                    line_text = " ".join(span_parts)
                    if line_text:
                        line_parts.append(line_text)

                if not line_parts:
                    continue

                block_text = " ".join(line_parts)

                # Remove soft hyphens introduced by PDF line-breaking
                block_text = re.sub(r"(\w+)-\s+(\w+)", r"\1\2", block_text)

                if is_header_block:
                    self.full_text.append(f"\n\n## {block_text.strip()}\n\n")
                else:
                    self.full_text.append(f"{block_text.strip()}\n\n")

    def _save_markdown(self) -> None:
        """Write the accumulated Markdown buffer to disk."""
        output_path = Path(self.cfg.MARKDOWN_PATH)

        content = "".join(self.full_text)

        # Final cleanup passes
        content = re.sub(r" {2,}", " ", content)   # collapse multiple spaces
        content = re.sub(r" \.", ".", content)       # fix detached full stops
        content = re.sub(r" ,", ",", content)        # fix detached commas

        output_path.write_text(content, encoding="utf-8")
        logger.info("Markdown saved to '%s'.", output_path)